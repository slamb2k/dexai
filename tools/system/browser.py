"""
Tool: Browser Automation
Purpose: Web automation with domain controls, screenshot, PDF, and form filling

Security Model:
- Domain allowlist/blocklist for navigation
- Isolated browser profile (no access to user's data)
- Resource limits (timeout, page count)
- No file downloads to host filesystem (except screenshots/PDFs to sandbox)
- All operations logged to audit trail

Usage:
    python tools/system/browser.py --screenshot https://example.com --output screenshot.png
    python tools/system/browser.py --pdf https://example.com --output page.pdf
    python tools/system/browser.py --extract https://example.com --selector "article"
    python tools/system/browser.py --navigate https://example.com
    python tools/system/browser.py --allowlist

Dependencies:
    - playwright (pip install playwright && playwright install chromium)

Output:
    JSON result with success status and operation result

Note:
    First-time setup: pip install playwright && playwright install chromium
"""

import os
import sys
import json
import argparse
import asyncio
import fnmatch
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Config path
CONFIG_PATH = PROJECT_ROOT / "args" / "system_access.yaml"

# Default domain allowlist
DEFAULT_ALLOWED_DOMAINS = [
    "*.google.com",
    "*.github.com",
    "*.stackoverflow.com",
    "*.wikipedia.org",
    "*.python.org",
    "*.mozilla.org",
    "*.w3.org",
    "*.readthedocs.io",
    "*.pypi.org",
    "*.npmjs.com",
    "example.com",
]

# Default blocked domains
DEFAULT_BLOCKED_DOMAINS = [
    "*.onion",
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "*.local",
    "*.internal",
]

# Default settings
DEFAULT_TIMEOUT = 30000  # 30 seconds
DEFAULT_VIEWPORT = {"width": 1280, "height": 720}


def load_config() -> Dict:
    """Load browser configuration from YAML file."""
    default_config = {
        'enabled': True,
        'headless': True,
        'timeout': DEFAULT_TIMEOUT,
        'viewport': DEFAULT_VIEWPORT,
        'allowed_domains': DEFAULT_ALLOWED_DOMAINS,
        'blocked_domains': DEFAULT_BLOCKED_DOMAINS,
        'user_agent': 'AddultingBot/1.0 (Browser Automation)',
        'permissions': {
            'navigate': 'browser:navigate',
            'screenshot': 'browser:screenshot',
            'pdf': 'browser:pdf',
            'extract': 'browser:extract',
        }
    }

    if not CONFIG_PATH.exists():
        return default_config

    try:
        import yaml
        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f)
        if config and 'browser' in config:
            browser_config = config['browser']
            for key, value in browser_config.items():
                default_config[key] = value
    except ImportError:
        pass
    except Exception:
        pass

    return default_config


def is_domain_allowed(url: str) -> tuple[bool, str]:
    """
    Check if a URL's domain is allowed.

    Args:
        url: URL to check

    Returns:
        Tuple of (is_allowed, reason)
    """
    config = load_config()

    try:
        parsed = urlparse(url)
        domain = parsed.hostname
        if not domain:
            return False, "Invalid URL: no hostname"
    except Exception as e:
        return False, f"Invalid URL: {e}"

    # Check blocked domains first
    blocked = config.get('blocked_domains', DEFAULT_BLOCKED_DOMAINS)
    for pattern in blocked:
        if fnmatch.fnmatch(domain, pattern):
            return False, f"Domain blocked: {domain} matches {pattern}"

    # Check allowed domains
    allowed = config.get('allowed_domains', DEFAULT_ALLOWED_DOMAINS)

    # If allowed list is empty or contains '*', allow all (except blocked)
    if not allowed or '*' in allowed:
        return True, "Allowed (no restrictions)"

    for pattern in allowed:
        if fnmatch.fnmatch(domain, pattern):
            return True, f"Allowed: {domain} matches {pattern}"

    return False, f"Domain not in allowlist: {domain}"


def validate_output_path(path: str) -> tuple[bool, str, str]:
    """
    Validate that output path is within sandbox.

    Args:
        path: Path to validate

    Returns:
        Tuple of (is_valid, resolved_path, error)
    """
    try:
        # Use fileops validation if available
        from tools.system import fileops
        return fileops.validate_path(path, check_exists=False)
    except Exception:
        pass

    # Fallback: basic validation
    try:
        resolved = Path(path).expanduser().resolve()
        # Require .tmp or /tmp in path
        if '.tmp' not in str(resolved) and '/tmp/' not in str(resolved):
            return False, "", "Output path must be in .tmp or /tmp directory"
        return True, str(resolved), ""
    except Exception as e:
        return False, "", str(e)


def check_permission(user_id: str, permission: str) -> bool:
    """Check if user has permission for operation."""
    try:
        from tools.security import permissions
        result = permissions.check_permission(user_id or 'anonymous', permission)
        return result.get('allowed', False)
    except Exception:
        return True  # If permissions unavailable, allow


def log_operation(action: str, url: str, user_id: Optional[str], status: str, details: Optional[Dict] = None):
    """Log browser operation to audit trail."""
    try:
        from tools.security import audit
        audit.log_event(
            event_type='command',
            action=f'browser:{action}',
            user_id=user_id,
            resource=url,
            status=status,
            details=details
        )
    except Exception:
        pass


async def get_browser():
    """Get a browser instance."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise ImportError(
            "Playwright not installed. Run: pip install playwright && playwright install chromium"
        )

    config = load_config()
    playwright = await async_playwright().start()

    browser = await playwright.chromium.launch(
        headless=config.get('headless', True),
    )

    return playwright, browser


async def navigate(
    url: str,
    wait_for: str = 'load',
    timeout: int = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Navigate to URL and return page info.

    Args:
        url: URL to navigate to
        wait_for: Wait condition ('load', 'domcontentloaded', 'networkidle')
        timeout: Navigation timeout in ms
        user_id: User requesting navigation

    Returns:
        dict with success status, title, url, status code
    """
    config = load_config()

    if not config.get('enabled', True):
        return {"success": False, "error": "Browser automation disabled"}

    # Check permission
    perm = config.get('permissions', {}).get('navigate', 'browser:navigate')
    if not check_permission(user_id, perm):
        return {"success": False, "error": f"Permission denied: {perm} required"}

    # Check domain
    is_allowed, reason = is_domain_allowed(url)
    if not is_allowed:
        log_operation('navigate', url, user_id, 'blocked', {'reason': reason})
        return {"success": False, "error": reason}

    timeout = timeout or config.get('timeout', DEFAULT_TIMEOUT)
    viewport = config.get('viewport', DEFAULT_VIEWPORT)

    playwright = None
    browser = None

    try:
        playwright, browser = await get_browser()
        context = await browser.new_context(
            viewport=viewport,
            user_agent=config.get('user_agent', 'AddultingBot/1.0')
        )
        page = await context.new_page()

        response = await page.goto(url, wait_until=wait_for, timeout=timeout)

        result = {
            "success": True,
            "title": await page.title(),
            "url": page.url,
            "status": response.status if response else None,
            "headers": dict(response.headers) if response else {}
        }

        log_operation('navigate', url, user_id, 'success', {'status': response.status if response else None})

        await browser.close()
        await playwright.stop()

        return result

    except Exception as e:
        log_operation('navigate', url, user_id, 'failure', {'error': str(e)})
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()
        return {"success": False, "error": str(e)}


async def screenshot(
    url: str,
    output_path: str,
    full_page: bool = False,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Take screenshot of page.

    Args:
        url: URL to screenshot
        output_path: Path to save screenshot
        full_page: Capture full page (not just viewport)
        user_id: User requesting screenshot

    Returns:
        dict with success status and path
    """
    config = load_config()

    if not config.get('enabled', True):
        return {"success": False, "error": "Browser automation disabled"}

    # Check permission
    perm = config.get('permissions', {}).get('screenshot', 'browser:screenshot')
    if not check_permission(user_id, perm):
        return {"success": False, "error": f"Permission denied: {perm} required"}

    # Check domain
    is_allowed, reason = is_domain_allowed(url)
    if not is_allowed:
        log_operation('screenshot', url, user_id, 'blocked', {'reason': reason})
        return {"success": False, "error": reason}

    # Validate output path
    is_valid, resolved_path, error = validate_output_path(output_path)
    if not is_valid:
        return {"success": False, "error": f"Invalid output path: {error}"}

    timeout = config.get('timeout', DEFAULT_TIMEOUT)
    viewport = config.get('viewport', DEFAULT_VIEWPORT)

    playwright = None
    browser = None

    try:
        playwright, browser = await get_browser()
        context = await browser.new_context(
            viewport=viewport,
            user_agent=config.get('user_agent', 'AddultingBot/1.0')
        )
        page = await context.new_page()

        await page.goto(url, wait_until='networkidle', timeout=timeout)

        # Ensure parent directory exists
        output = Path(resolved_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        await page.screenshot(path=str(output), full_page=full_page)

        file_size = output.stat().st_size

        result = {
            "success": True,
            "path": resolved_path,
            "url": url,
            "full_page": full_page,
            "size": file_size,
            "message": f"Screenshot saved to {resolved_path}"
        }

        log_operation('screenshot', url, user_id, 'success', {'output': resolved_path, 'size': file_size})

        await browser.close()
        await playwright.stop()

        return result

    except Exception as e:
        log_operation('screenshot', url, user_id, 'failure', {'error': str(e)})
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()
        return {"success": False, "error": str(e)}


async def pdf(
    url: str,
    output_path: str,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate PDF from page.

    Args:
        url: URL to convert to PDF
        output_path: Path to save PDF
        user_id: User requesting PDF

    Returns:
        dict with success status and path
    """
    config = load_config()

    if not config.get('enabled', True):
        return {"success": False, "error": "Browser automation disabled"}

    # Check permission
    perm = config.get('permissions', {}).get('pdf', 'browser:pdf')
    if not check_permission(user_id, perm):
        return {"success": False, "error": f"Permission denied: {perm} required"}

    # Check domain
    is_allowed, reason = is_domain_allowed(url)
    if not is_allowed:
        log_operation('pdf', url, user_id, 'blocked', {'reason': reason})
        return {"success": False, "error": reason}

    # Validate output path
    is_valid, resolved_path, error = validate_output_path(output_path)
    if not is_valid:
        return {"success": False, "error": f"Invalid output path: {error}"}

    timeout = config.get('timeout', DEFAULT_TIMEOUT)

    playwright = None
    browser = None

    try:
        playwright, browser = await get_browser()
        # PDF requires non-headless context for some operations
        context = await browser.new_context(
            user_agent=config.get('user_agent', 'AddultingBot/1.0')
        )
        page = await context.new_page()

        await page.goto(url, wait_until='networkidle', timeout=timeout)

        # Ensure parent directory exists
        output = Path(resolved_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        await page.pdf(path=str(output), format='A4', print_background=True)

        file_size = output.stat().st_size

        result = {
            "success": True,
            "path": resolved_path,
            "url": url,
            "size": file_size,
            "message": f"PDF saved to {resolved_path}"
        }

        log_operation('pdf', url, user_id, 'success', {'output': resolved_path, 'size': file_size})

        await browser.close()
        await playwright.stop()

        return result

    except Exception as e:
        log_operation('pdf', url, user_id, 'failure', {'error': str(e)})
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()
        return {"success": False, "error": str(e)}


async def extract_text(
    url: str,
    selector: Optional[str] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Extract text content from page.

    Args:
        url: URL to extract from
        selector: CSS selector to extract from (optional)
        user_id: User requesting extraction

    Returns:
        dict with success status and text content
    """
    config = load_config()

    if not config.get('enabled', True):
        return {"success": False, "error": "Browser automation disabled"}

    # Check permission
    perm = config.get('permissions', {}).get('extract', 'browser:extract')
    if not check_permission(user_id, perm):
        return {"success": False, "error": f"Permission denied: {perm} required"}

    # Check domain
    is_allowed, reason = is_domain_allowed(url)
    if not is_allowed:
        log_operation('extract', url, user_id, 'blocked', {'reason': reason})
        return {"success": False, "error": reason}

    timeout = config.get('timeout', DEFAULT_TIMEOUT)
    viewport = config.get('viewport', DEFAULT_VIEWPORT)

    playwright = None
    browser = None

    try:
        playwright, browser = await get_browser()
        context = await browser.new_context(
            viewport=viewport,
            user_agent=config.get('user_agent', 'AddultingBot/1.0')
        )
        page = await context.new_page()

        await page.goto(url, wait_until='domcontentloaded', timeout=timeout)

        if selector:
            # Extract from specific element
            elements = await page.query_selector_all(selector)
            texts = []
            for el in elements:
                text = await el.inner_text()
                texts.append(text.strip())
            content = '\n\n'.join(texts)
        else:
            # Extract all text from body
            content = await page.inner_text('body')

        result = {
            "success": True,
            "url": url,
            "selector": selector,
            "content": content,
            "length": len(content),
            "title": await page.title()
        }

        log_operation('extract', url, user_id, 'success', {'selector': selector, 'length': len(content)})

        await browser.close()
        await playwright.stop()

        return result

    except Exception as e:
        log_operation('extract', url, user_id, 'failure', {'error': str(e)})
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()
        return {"success": False, "error": str(e)}


async def fill_form(
    url: str,
    fields: Dict[str, str],
    submit_selector: Optional[str] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fill form fields and optionally submit.

    Args:
        url: URL with form
        fields: Dictionary of selector -> value pairs
        submit_selector: Selector for submit button (optional)
        user_id: User requesting form fill

    Returns:
        dict with success status
    """
    config = load_config()

    if not config.get('enabled', True):
        return {"success": False, "error": "Browser automation disabled"}

    # Check permission (use navigate permission for forms)
    perm = config.get('permissions', {}).get('navigate', 'browser:navigate')
    if not check_permission(user_id, perm):
        return {"success": False, "error": f"Permission denied: {perm} required"}

    # Check domain
    is_allowed, reason = is_domain_allowed(url)
    if not is_allowed:
        log_operation('form', url, user_id, 'blocked', {'reason': reason})
        return {"success": False, "error": reason}

    timeout = config.get('timeout', DEFAULT_TIMEOUT)
    viewport = config.get('viewport', DEFAULT_VIEWPORT)

    playwright = None
    browser = None

    try:
        playwright, browser = await get_browser()
        context = await browser.new_context(
            viewport=viewport,
            user_agent=config.get('user_agent', 'AddultingBot/1.0')
        )
        page = await context.new_page()

        await page.goto(url, wait_until='domcontentloaded', timeout=timeout)

        # Fill each field
        for selector, value in fields.items():
            await page.fill(selector, value)

        # Submit if requested
        if submit_selector:
            await page.click(submit_selector)
            await page.wait_for_load_state('domcontentloaded')

        result = {
            "success": True,
            "url": page.url,
            "fields_filled": len(fields),
            "submitted": submit_selector is not None,
            "title": await page.title()
        }

        log_operation('form', url, user_id, 'success', {'fields': len(fields), 'submitted': submit_selector is not None})

        await browser.close()
        await playwright.stop()

        return result

    except Exception as e:
        log_operation('form', url, user_id, 'failure', {'error': str(e)})
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()
        return {"success": False, "error": str(e)}


def get_allowlist() -> Dict[str, Any]:
    """Get current domain allowlist and blocklist."""
    config = load_config()

    return {
        "success": True,
        "allowed_domains": config.get('allowed_domains', DEFAULT_ALLOWED_DOMAINS),
        "blocked_domains": config.get('blocked_domains', DEFAULT_BLOCKED_DOMAINS),
        "timeout_ms": config.get('timeout', DEFAULT_TIMEOUT),
        "headless": config.get('headless', True)
    }


def main():
    parser = argparse.ArgumentParser(description='Browser Automation')

    # Actions
    parser.add_argument('--navigate', help='Navigate to URL')
    parser.add_argument('--screenshot', help='Screenshot URL')
    parser.add_argument('--pdf', help='Generate PDF from URL')
    parser.add_argument('--extract', help='Extract text from URL')
    parser.add_argument('--allowlist', action='store_true', help='Show domain allowlist')
    parser.add_argument('--check-domain', help='Check if domain is allowed')

    # Options
    parser.add_argument('--output', '-o', help='Output path for screenshot/pdf')
    parser.add_argument('--selector', '-s', help='CSS selector for extraction')
    parser.add_argument('--full-page', action='store_true', help='Full page screenshot')
    parser.add_argument('--wait-for', choices=['load', 'domcontentloaded', 'networkidle'],
                       default='load', help='Wait condition')
    parser.add_argument('--timeout', type=int, help='Timeout in ms')
    parser.add_argument('--user', help='User ID')

    args = parser.parse_args()
    result = None

    if args.navigate:
        result = asyncio.run(navigate(
            args.navigate,
            wait_for=args.wait_for,
            timeout=args.timeout,
            user_id=args.user
        ))

    elif args.screenshot:
        if not args.output:
            print("Error: --output required for screenshot")
            sys.exit(1)
        result = asyncio.run(screenshot(
            args.screenshot,
            args.output,
            full_page=args.full_page,
            user_id=args.user
        ))

    elif args.pdf:
        if not args.output:
            print("Error: --output required for pdf")
            sys.exit(1)
        result = asyncio.run(pdf(
            args.pdf,
            args.output,
            user_id=args.user
        ))

    elif args.extract:
        result = asyncio.run(extract_text(
            args.extract,
            selector=args.selector,
            user_id=args.user
        ))

    elif args.check_domain:
        is_allowed, reason = is_domain_allowed(args.check_domain)
        result = {
            "success": True,
            "url": args.check_domain,
            "allowed": is_allowed,
            "reason": reason
        }

    elif args.allowlist:
        result = get_allowlist()

    else:
        print("Error: Must specify an action")
        sys.exit(1)

    if result:
        if result.get('success'):
            print(f"OK {result.get('message', 'Success')}")
        else:
            print(f"ERROR {result.get('error')}")
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
