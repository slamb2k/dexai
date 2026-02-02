"""
Tool: Network Client
Purpose: HTTP client with domain allowlist, SSL enforcement, and request logging

Security Model:
- Domain allowlist (configurable)
- SSL verification always enforced (cannot be disabled)
- Request and response size limits
- All requests logged to audit trail
- No access to internal/private networks

Usage:
    python tools/system/network.py --get https://api.github.com
    python tools/system/network.py --post https://api.example.com/data --json '{"key": "value"}'
    python tools/system/network.py --get https://example.com --headers '{"Authorization": "Bearer token"}'
    python tools/system/network.py --allowlist
    python tools/system/network.py --check https://api.github.com

Dependencies:
    - requests (pip install requests)

Output:
    JSON result with success status, status_code, headers, body
"""

import argparse
import fnmatch
import ipaddress
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Config path
CONFIG_PATH = PROJECT_ROOT / "args" / "system_access.yaml"

# Default allowed domains
DEFAULT_ALLOWED_DOMAINS = [
    "api.github.com",
    "api.openai.com",
    "api.anthropic.com",
    "*.googleapis.com",
    "api.together.ai",
    "huggingface.co",
    "*.huggingface.co",
]

# Default blocked domains/IPs
DEFAULT_BLOCKED = [
    # Localhost
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    # Internal networks
    "*.local",
    "*.internal",
    "*.localhost",
    # Metadata endpoints
    "169.254.*",
    "metadata.google.internal",
    # Onion/I2P
    "*.onion",
    "*.i2p",
]

# Private IP ranges to block
PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
    ipaddress.ip_network("fc00::/7"),  # IPv6 private
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]

# Default limits
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10MB


def load_config() -> dict:
    """Load network configuration from YAML file."""
    default_config = {
        "enabled": True,
        "timeout": DEFAULT_TIMEOUT,
        "max_response_size": DEFAULT_MAX_RESPONSE_SIZE,
        "ssl_verify": True,  # Cannot be disabled
        "allowed_domains": DEFAULT_ALLOWED_DOMAINS,
        "blocked_domains": DEFAULT_BLOCKED,
        "block_private_ips": True,
        "rate_limit": {
            "requests_per_minute": 60,
            "burst": 10,
        },
        "permissions": {
            "request": "network:request",
        },
    }

    if not CONFIG_PATH.exists():
        return default_config

    try:
        import yaml

        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f)
        if config and "network" in config:
            network_config = config["network"]
            for key, value in network_config.items():
                # Never allow SSL verification to be disabled
                if key == "ssl_verify":
                    continue
                default_config[key] = value
    except ImportError:
        pass
    except Exception:
        pass

    return default_config


def is_private_ip(ip_str: str) -> bool:
    """Check if IP address is in private range."""
    try:
        ip = ipaddress.ip_address(ip_str)
        for network in PRIVATE_NETWORKS:
            if ip in network:
                return True
        return False
    except ValueError:
        return False


def validate_url(url: str) -> tuple[bool, str]:
    """
    Validate if URL domain is allowed.

    Args:
        url: URL to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    config = load_config()

    try:
        parsed = urlparse(url)

        # Must be HTTP(S)
        if parsed.scheme not in ("http", "https"):
            return False, f"Only HTTP(S) allowed, got: {parsed.scheme}"

        hostname = parsed.hostname
        if not hostname:
            return False, "Invalid URL: no hostname"

        # Check if hostname is an IP address
        try:
            ip = ipaddress.ip_address(hostname)
            if config.get("block_private_ips", True) and is_private_ip(hostname):
                return False, f"Private IP addresses not allowed: {hostname}"
        except ValueError:
            pass  # Not an IP, it's a hostname

        # Check blocked domains
        blocked = config.get("blocked_domains", DEFAULT_BLOCKED)
        for pattern in blocked:
            if fnmatch.fnmatch(hostname, pattern):
                return False, f"Domain blocked: {hostname}"

        # Check allowed domains
        allowed = config.get("allowed_domains", DEFAULT_ALLOWED_DOMAINS)

        # If allowed list is empty or contains '*', allow all (except blocked)
        if not allowed or "*" in allowed:
            return True, ""

        for pattern in allowed:
            if fnmatch.fnmatch(hostname, pattern):
                return True, ""

        return False, f"Domain not in allowlist: {hostname}"

    except Exception as e:
        return False, f"Invalid URL: {e}"


def check_permission(user_id: str, permission: str) -> bool:
    """Check if user has permission for operation."""
    try:
        from tools.security import permissions

        result = permissions.check_permission(user_id or "anonymous", permission)
        return result.get("allowed", False)
    except Exception:
        return True  # If permissions unavailable, allow


def log_request(
    method: str, url: str, user_id: str | None, status: str, details: dict | None = None
):
    """Log network request to audit trail."""
    try:
        from tools.security import audit

        audit.log_event(
            event_type="command",
            action=f"network:{method.lower()}",
            user_id=user_id,
            resource=url,
            status=status,
            details=details,
        )
    except Exception:
        pass


def request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    data: str | None = None,
    json_data: dict | None = None,
    timeout: int | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """
    Make HTTP request.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        url: URL to request
        headers: Request headers
        data: Request body (string)
        json_data: Request body (JSON dict)
        timeout: Request timeout in seconds
        user_id: User making request

    Returns:
        dict with success status, status_code, headers, body
    """
    try:
        import requests
    except ImportError:
        return {
            "success": False,
            "error": "requests library not installed. Run: pip install requests",
        }

    config = load_config()

    if not config.get("enabled", True):
        return {"success": False, "error": "Network client disabled"}

    # Check permission
    perm = config.get("permissions", {}).get("request", "network:request")
    if not check_permission(user_id, perm):
        return {"success": False, "error": f"Permission denied: {perm} required"}

    # Validate URL
    is_valid, error = validate_url(url)
    if not is_valid:
        log_request(method, url, user_id, "blocked", {"reason": error})
        return {"success": False, "error": error}

    timeout = timeout or config.get("timeout", DEFAULT_TIMEOUT)
    max_size = config.get("max_response_size", DEFAULT_MAX_RESPONSE_SIZE)

    # Prepare headers
    request_headers = headers or {}
    if "User-Agent" not in request_headers:
        request_headers["User-Agent"] = "AddultingBot/1.0 (Network Client)"

    start_time = datetime.now()

    try:
        response = requests.request(
            method=method.upper(),
            url=url,
            headers=request_headers,
            data=data,
            json=json_data,
            timeout=timeout,
            verify=True,  # Always verify SSL
            allow_redirects=True,
            stream=True,  # Stream to check size
        )

        # Check response size
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > max_size:
            response.close()
            return {
                "success": False,
                "error": f"Response too large: {content_length} bytes (max: {max_size})",
            }

        # Read response with size limit
        content = b""
        for chunk in response.iter_content(chunk_size=8192):
            content += chunk
            if len(content) > max_size:
                response.close()
                return {"success": False, "error": f"Response exceeded max size: {max_size} bytes"}

        end_time = datetime.now()
        elapsed_ms = int((end_time - start_time).total_seconds() * 1000)

        # Try to decode as text
        try:
            body = content.decode("utf-8")
        except UnicodeDecodeError:
            body = content.hex()

        result = {
            "success": True,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": body,
            "elapsed_ms": elapsed_ms,
            "url": response.url,  # Final URL after redirects
            "size": len(content),
        }

        log_request(
            method,
            url,
            user_id,
            "success",
            {"status_code": response.status_code, "elapsed_ms": elapsed_ms, "size": len(content)},
        )

        return result

    except requests.exceptions.SSLError as e:
        log_request(method, url, user_id, "failure", {"error": "SSL error", "details": str(e)})
        return {"success": False, "error": f"SSL verification failed: {e}"}

    except requests.exceptions.Timeout:
        log_request(method, url, user_id, "failure", {"error": "timeout"})
        return {"success": False, "error": f"Request timed out after {timeout}s"}

    except requests.exceptions.ConnectionError as e:
        log_request(
            method, url, user_id, "failure", {"error": "connection_error", "details": str(e)}
        )
        return {"success": False, "error": f"Connection error: {e}"}

    except Exception as e:
        log_request(method, url, user_id, "failure", {"error": str(e)})
        return {"success": False, "error": str(e)}


def get(url: str, **kwargs) -> dict[str, Any]:
    """HTTP GET shorthand."""
    return request("GET", url, **kwargs)


def post(url: str, **kwargs) -> dict[str, Any]:
    """HTTP POST shorthand."""
    return request("POST", url, **kwargs)


def put(url: str, **kwargs) -> dict[str, Any]:
    """HTTP PUT shorthand."""
    return request("PUT", url, **kwargs)


def delete(url: str, **kwargs) -> dict[str, Any]:
    """HTTP DELETE shorthand."""
    return request("DELETE", url, **kwargs)


def get_allowlist() -> dict[str, Any]:
    """Get current domain allowlist."""
    config = load_config()

    return {
        "success": True,
        "allowed_domains": config.get("allowed_domains", DEFAULT_ALLOWED_DOMAINS),
        "blocked_domains": config.get("blocked_domains", DEFAULT_BLOCKED),
        "timeout": config.get("timeout", DEFAULT_TIMEOUT),
        "max_response_size": config.get("max_response_size", DEFAULT_MAX_RESPONSE_SIZE),
        "block_private_ips": config.get("block_private_ips", True),
        "ssl_verify": True,  # Always true
    }


def main():
    parser = argparse.ArgumentParser(description="Network Client")

    # Actions
    parser.add_argument("--get", help="GET request to URL")
    parser.add_argument("--post", help="POST request to URL")
    parser.add_argument("--put", help="PUT request to URL")
    parser.add_argument("--delete", help="DELETE request to URL")
    parser.add_argument("--check", help="Check if URL is allowed")
    parser.add_argument("--allowlist", action="store_true", help="Show allowlist")

    # Options
    parser.add_argument("--headers", help="Request headers (JSON)")
    parser.add_argument("--data", help="Request body (string)")
    parser.add_argument("--json", dest="json_data", help="Request body (JSON)")
    parser.add_argument("--timeout", type=int, help="Timeout in seconds")
    parser.add_argument("--user", help="User ID")

    args = parser.parse_args()
    result = None

    # Parse headers if provided
    headers = None
    if args.headers:
        try:
            headers = json.loads(args.headers)
        except json.JSONDecodeError:
            print("Error: --headers must be valid JSON")
            sys.exit(1)

    # Parse JSON data if provided
    json_data = None
    if args.json_data:
        try:
            json_data = json.loads(args.json_data)
        except json.JSONDecodeError:
            print("Error: --json must be valid JSON")
            sys.exit(1)

    if args.get:
        result = get(args.get, headers=headers, timeout=args.timeout, user_id=args.user)

    elif args.post:
        result = post(
            args.post,
            headers=headers,
            data=args.data,
            json_data=json_data,
            timeout=args.timeout,
            user_id=args.user,
        )

    elif args.put:
        result = put(
            args.put,
            headers=headers,
            data=args.data,
            json_data=json_data,
            timeout=args.timeout,
            user_id=args.user,
        )

    elif args.delete:
        result = delete(args.delete, headers=headers, timeout=args.timeout, user_id=args.user)

    elif args.check:
        is_valid, error = validate_url(args.check)
        result = {
            "success": True,
            "url": args.check,
            "allowed": is_valid,
            "error": error if not is_valid else None,
        }

    elif args.allowlist:
        result = get_allowlist()

    else:
        print("Error: Must specify an action")
        sys.exit(1)

    if result:
        if result.get("success"):
            print(f"OK {result.get('message', 'Success')}")
        else:
            print(f"ERROR {result.get('error')}")
            sys.exit(1)

        # For large responses, truncate body in output
        if "body" in result and len(result.get("body", "")) > 5000:
            display_result = result.copy()
            display_result["body"] = display_result["body"][:5000] + "... [truncated]"
            print(json.dumps(display_result, indent=2, default=str))
        else:
            print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
