"""
Package Security Verification

Provides security checks before installing Python packages for skills.

Security Checks:
1. Package exists on PyPI
2. Not in known malicious packages blocklist
3. Typosquatting detection (similar to popular packages)
4. Download count validation (>1000 monthly downloads)
5. Risk assessment based on multiple factors

Usage:
    from tools.security.package_security import verify_package_security

    result = await verify_package_security("requests")
    if result["safe"]:
        # OK to install
    else:
        print(f"Risk: {result['risk_level']}, warnings: {result['warnings']}")
"""

import asyncio
import difflib
import hashlib
import json as _json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
HASH_CACHE_PATH = PROJECT_ROOT / "data" / "package_hashes.json"


# =============================================================================
# Known Malicious Packages Blocklist
# =============================================================================

# These are known typosquatting or malicious packages that should never be installed.
# This list should be updated periodically from security advisories.
MALICIOUS_PACKAGES = {
    # Typosquats of popular packages
    "colourama": "Typosquat of colorama",
    "python-sqlite": "Typosquat of sqlite3",
    "python-mysql": "Typosquat of mysql-connector-python",
    "python-mongo": "Typosquat of pymongo",
    "python-openssl": "Typosquat of pyOpenSSL",
    "nmap-python": "Typosquat of python-nmap",
    "python-nmap": "Legitimate package, but often confused",
    "request": "Typosquat of requests",
    "urlib": "Typosquat of urllib",
    "urllib-request": "Typosquat of urllib",
    "beuatifulsoup": "Typosquat of beautifulsoup4",
    "djanga": "Typosquat of django",
    "flaskk": "Typosquat of flask",
    "numpyy": "Typosquat of numpy",
    "pandass": "Typosquat of pandas",
    "scikitlearn": "Typosquat of scikit-learn",
    "tensorfloww": "Typosquat of tensorflow",
    "pytorchh": "Typosquat of torch",
    # Known malicious packages (historical)
    "ctx": "Removed - contained malware",
    "colourama": "Typosquat with info stealer",
    "python3-dateutil": "Typosquat of python-dateutil",
    "jeIlyfish": "Typosquat of jellyfish (with capital I)",
    "libpeshnern": "Malicious package",
    "libpeshka": "Malicious package",
    "importantpackage": "Malicious test package",
}

# Popular packages to check typosquatting against
POPULAR_PACKAGES = {
    "requests",
    "numpy",
    "pandas",
    "flask",
    "django",
    "tensorflow",
    "torch",
    "pytorch",
    "scikit-learn",
    "beautifulsoup4",
    "pillow",
    "matplotlib",
    "scipy",
    "selenium",
    "boto3",
    "colorama",
    "pyyaml",
    "sqlalchemy",
    "aiohttp",
    "httpx",
    "fastapi",
    "uvicorn",
    "pydantic",
    "pytest",
    "black",
    "mypy",
    "ruff",
    "cryptography",
    "paramiko",
    "fabric",
    "celery",
    "redis",
    "psycopg2",
    "pymongo",
    "anthropic",
    "openai",
    "langchain",
    "transformers",
}

# Minimum download count to consider a package established
MIN_DOWNLOAD_COUNT = 1000


# =============================================================================
# Security Verification
# =============================================================================


async def verify_package_security(
    package_name: str,
    skip_pypi_check: bool = False,
) -> dict[str, Any]:
    """
    Verify a package is safe to install.

    Performs multiple security checks:
    1. Package exists on PyPI (unless skip_pypi_check=True)
    2. Not in known malicious packages blocklist
    3. Not a typosquat of a popular package
    4. Has reasonable download count (if available)

    Args:
        package_name: Name of the package to verify
        skip_pypi_check: Skip PyPI API check (for offline testing)

    Returns:
        {
            "safe": bool,
            "risk_level": "low" | "medium" | "high" | "blocked",
            "warnings": list[str],
            "recommendation": "install" | "ask_user" | "skip",
            "package_info": {
                "name": str,
                "version": str,
                "summary": str,
                "downloads": int | None,
                "verified_maintainer": bool,
            } | None,
            "blocked_reason": str | None,
        }
    """
    normalized_name = _normalize_package_name(package_name)
    warnings: list[str] = []
    package_info = None
    risk_score = 0

    # Check 1: Known malicious packages blocklist
    if normalized_name in MALICIOUS_PACKAGES:
        return {
            "safe": False,
            "risk_level": "blocked",
            "warnings": [f"BLOCKED: {MALICIOUS_PACKAGES[normalized_name]}"],
            "recommendation": "skip",
            "package_info": None,
            "blocked_reason": MALICIOUS_PACKAGES[normalized_name],
        }

    # Check 2: Typosquatting detection
    typosquat_target = _detect_typosquatting(normalized_name)
    if typosquat_target:
        warnings.append(
            f"Potential typosquat: '{package_name}' is very similar to '{typosquat_target}'"
        )
        risk_score += 30  # Significant risk increase

    # Check 3: PyPI existence and metadata
    if not skip_pypi_check:
        pypi_result = await _check_pypi(package_name)
        if not pypi_result["exists"]:
            return {
                "safe": False,
                "risk_level": "high",
                "warnings": ["Package not found on PyPI"],
                "recommendation": "skip",
                "package_info": None,
                "blocked_reason": "Package does not exist on PyPI",
            }

        package_info = pypi_result["info"]

        # Check 4: OSV advisory feed using version already fetched from PyPI
        version_for_osv = package_info.get("version")
        if version_for_osv:
            try:
                from tools.security.advisory_feed import is_package_vulnerable

                vuln_result = is_package_vulnerable(package_name, version_for_osv)
                if vuln_result.get("vulnerable"):
                    advisory_ids = [a.get("id", "unknown") for a in vuln_result.get("advisories", [])]
                    return {
                        "safe": False,
                        "risk_level": "blocked",
                        "warnings": [
                            f"BLOCKED: Known vulnerabilities found: {', '.join(advisory_ids)}"
                        ],
                        "recommendation": "skip",
                        "package_info": None,
                        "blocked_reason": f"OSV advisories: {', '.join(advisory_ids)}",
                        "advisories": vuln_result.get("advisories", []),
                    }
            except ImportError:
                logger.debug("advisory_feed module not available, skipping OSV check")
            except Exception as e:
                logger.warning(f"OSV advisory check failed for {package_name}: {e}")

        # Check download count
        if package_info.get("downloads"):
            downloads = package_info["downloads"]
            if downloads < MIN_DOWNLOAD_COUNT:
                warnings.append(
                    f"Low download count ({downloads:,}). Package may be new or unused."
                )
                risk_score += 20
            elif downloads < 10000:
                risk_score += 5  # Minor concern

        # Check if summary/description is suspicious
        summary = package_info.get("summary", "").lower()
        suspicious_terms = ["test", "poc", "proof of concept", "malware", "backdoor"]
        if any(term in summary for term in suspicious_terms):
            warnings.append("Package summary contains suspicious terms")
            risk_score += 15

    # Calculate final risk level
    if risk_score >= 40:
        risk_level = "high"
        recommendation = "skip"
        safe = False
    elif risk_score >= 20:
        risk_level = "medium"
        recommendation = "ask_user"
        safe = True  # Allow with warning
    else:
        risk_level = "low"
        recommendation = "install"
        safe = True

    return {
        "safe": safe,
        "risk_level": risk_level,
        "warnings": warnings,
        "recommendation": recommendation,
        "package_info": package_info,
        "blocked_reason": None,
    }


def _normalize_package_name(name: str) -> str:
    """
    Normalize package name for comparison.

    PyPI normalizes names: lowercase, hyphens/underscores are equivalent.
    """
    return name.lower().replace("-", "_").replace(".", "_")


def _detect_typosquatting(package_name: str) -> str | None:
    """
    Detect if a package name is suspiciously similar to a popular package.

    Uses string similarity (Levenshtein distance via difflib) to find
    potential typosquats.

    Returns:
        Name of the similar popular package, or None if no match.
    """
    normalized = _normalize_package_name(package_name)

    for popular in POPULAR_PACKAGES:
        popular_normalized = _normalize_package_name(popular)

        # Skip if it's exactly the same (legitimate)
        if normalized == popular_normalized:
            return None

        # Check similarity ratio
        ratio = difflib.SequenceMatcher(None, normalized, popular_normalized).ratio()

        # High similarity (>0.85) is suspicious for different packages
        if ratio > 0.85:
            return popular

        # Check for common typosquatting patterns
        # Adding/removing single character
        if abs(len(normalized) - len(popular_normalized)) == 1:
            if ratio > 0.8:
                return popular

        # Character substitution (homoglyphs like l/1, 0/O)
        if len(normalized) == len(popular_normalized):
            differences = sum(
                1 for a, b in zip(normalized, popular_normalized) if a != b
            )
            if differences == 1:
                return popular

    return None


async def _check_pypi(package_name: str) -> dict[str, Any]:
    """
    Check package existence and metadata on PyPI.

    Returns:
        {
            "exists": bool,
            "info": {
                "name": str,
                "version": str,
                "summary": str,
                "downloads": int | None,
                "verified_maintainer": bool,
            } | None
        }
    """
    url = f"https://pypi.org/pypi/{package_name}/json"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)

            if response.status_code == 404:
                return {"exists": False, "info": None}

            if response.status_code != 200:
                logger.warning(f"PyPI API returned {response.status_code} for {package_name}")
                return {"exists": False, "info": None}

            data = response.json()
            info = data.get("info", {})

            # Try to get download stats from pypistats.org (optional)
            downloads = await _get_download_count(package_name)

            return {
                "exists": True,
                "info": {
                    "name": info.get("name", package_name),
                    "version": info.get("version", "unknown"),
                    "summary": info.get("summary", ""),
                    "author": info.get("author", ""),
                    "author_email": info.get("author_email", ""),
                    "home_page": info.get("home_page", ""),
                    "downloads": downloads,
                    "verified_maintainer": bool(info.get("author_email")),
                },
            }

    except httpx.TimeoutException:
        logger.warning(f"PyPI API timeout for {package_name}")
        return {"exists": False, "info": None}
    except Exception as e:
        logger.error(f"PyPI API error for {package_name}: {e}")
        return {"exists": False, "info": None}


async def _get_download_count(package_name: str) -> int | None:
    """
    Get monthly download count from pypistats.org.

    Returns None if unavailable.
    """
    url = f"https://pypistats.org/api/packages/{package_name}/recent"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)

            if response.status_code != 200:
                return None

            data = response.json()
            # pypistats returns {"data": {"last_month": N, ...}}
            return data.get("data", {}).get("last_month")

    except Exception:
        return None


# =============================================================================
# Package Hash Pinning
# =============================================================================


def _load_hash_cache() -> dict[str, str]:
    """Load pinned hashes from the local cache file."""
    try:
        if HASH_CACHE_PATH.exists():
            return _json.loads(HASH_CACHE_PATH.read_text())
    except Exception as e:
        logger.warning(f"Failed to load hash cache: {e}")
    return {}


def _save_hash_cache(cache: dict[str, str]) -> None:
    """Save pinned hashes to the local cache file."""
    try:
        HASH_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        HASH_CACHE_PATH.write_text(_json.dumps(cache, indent=2))
    except Exception as e:
        logger.warning(f"Failed to save hash cache: {e}")


def get_pypi_hash(package_name: str, version: str) -> str | None:
    """Fetch the expected SHA-256 hash for a package version from PyPI.

    Queries the PyPI JSON API and returns the sha256 digest of the first
    available wheel or sdist distribution file.

    Args:
        package_name: PyPI package name.
        version: Exact version string.

    Returns:
        SHA-256 hex digest string, or None if unavailable.
    """
    url = f"https://pypi.org/pypi/{package_name}/{version}/json"
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url)
            if response.status_code != 200:
                return None
            data = response.json()

        # Prefer wheel, fall back to sdist
        urls = data.get("urls", [])
        for dist in urls:
            digests = dist.get("digests", {})
            sha256 = digests.get("sha256")
            if sha256:
                return sha256

        return None
    except Exception as e:
        logger.warning(f"Failed to fetch PyPI hash for {package_name}=={version}: {e}")
        return None


def verify_package_hash(
    package_name: str,
    version: str,
    expected_hash: str | None = None,
    mode: str = "warn",
) -> dict[str, Any]:
    """Verify package integrity by comparing SHA-256 hashes.

    After a package is installed, this function computes the SHA-256 of the
    installed distribution and compares it against a pinned hash from the local
    cache, an explicitly provided hash, or stores the hash for future comparison.

    The PyPI distribution hash is also fetched and stored alongside the installed
    hash for audit purposes.

    Args:
        package_name: Name of the installed package.
        version: Installed version string.
        expected_hash: Pre-known hash to verify against. If None, fetched from
            local cache or PyPI.
        mode: "warn" (log mismatch, allow) or "strict" (block on mismatch).

    Returns:
        {"verified": True} on match, or
        {"verified": False, "warning": ...} in warn mode, or
        {"verified": False, "error": ..., "blocked": True} in strict mode.
    """
    cache = _load_hash_cache()
    cache_key = f"{package_name}=={version}"
    pypi_key = f"{package_name}=={version}:pypi"

    # Compute hash of installed package
    actual_hash = _compute_installed_hash(package_name)
    if actual_hash is None:
        logger.warning(f"Could not compute hash for installed {cache_key}")
        if mode == "strict":
            return {"verified": False, "error": "Package not found or unreadable", "blocked": True}
        else:
            return {"verified": False, "warning": "Package not found, cannot verify hash"}

    # Resolve expected hash: explicit arg > pinned cache > first-install pin
    if expected_hash is None:
        expected_hash = cache.get(cache_key)

    if expected_hash is None:
        # First install: fetch PyPI dist hash for audit, pin installed hash
        pypi_hash = get_pypi_hash(package_name, version)
        if pypi_hash:
            cache[pypi_key] = pypi_hash

        # Pin the computed installed-files hash for future comparison
        cache[cache_key] = actual_hash
        _save_hash_cache(cache)
        logger.info(f"Pinned hash for {cache_key}: {actual_hash[:16]}...")
        return {"verified": True, "pinned": True}

    if actual_hash == expected_hash:
        return {"verified": True}

    # Mismatch
    msg = f"Hash mismatch for {cache_key}: expected {expected_hash[:16]}..., got {actual_hash[:16]}..."
    logger.warning(msg)

    if mode == "strict":
        return {"verified": False, "error": msg, "blocked": True}
    else:
        return {"verified": False, "warning": msg}


def _compute_installed_hash(package_name: str) -> str | None:
    """Compute SHA-256 hash of an installed package's RECORD files.

    Uses importlib.metadata to locate installed distribution files and
    hashes the concatenation of their contents in sorted order.

    Args:
        package_name: Installed package name.

    Returns:
        SHA-256 hex digest, or None if package not found.
    """
    try:
        import importlib.metadata

        dist = importlib.metadata.distribution(package_name)
        files = dist.files
        if not files:
            return None

        hasher = hashlib.sha256()
        for f in sorted(files, key=lambda p: str(p)):
            try:
                located = f.locate()
                if located.exists() and located.is_file():
                    hasher.update(located.read_bytes())
            except Exception:
                continue

        return hasher.hexdigest()
    except importlib.metadata.PackageNotFoundError:
        return None
    except Exception as e:
        logger.warning(f"Error computing hash for {package_name}: {e}")
        return None


# =============================================================================
# Synchronous Wrapper
# =============================================================================


def verify_package_security_sync(
    package_name: str,
    skip_pypi_check: bool = False,
) -> dict[str, Any]:
    """
    Synchronous wrapper for verify_package_security.

    For use in contexts where async is not available.
    """
    try:
        loop = asyncio.get_running_loop()
        # We're in an async context - can't use run_until_complete
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run,
                verify_package_security(package_name, skip_pypi_check)
            )
            return future.result(timeout=15.0)
    except RuntimeError:
        # No running loop - we can create one
        return asyncio.run(verify_package_security(package_name, skip_pypi_check))


# =============================================================================
# Batch Verification
# =============================================================================


async def verify_packages_batch(
    package_names: list[str],
) -> dict[str, dict[str, Any]]:
    """
    Verify multiple packages in parallel.

    Args:
        package_names: List of package names to verify

    Returns:
        Dict mapping package name to verification result
    """
    tasks = [verify_package_security(name) for name in package_names]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    return {
        name: result if not isinstance(result, Exception) else {
            "safe": False,
            "risk_level": "high",
            "warnings": [f"Verification error: {result}"],
            "recommendation": "skip",
            "package_info": None,
            "blocked_reason": str(result),
        }
        for name, result in zip(package_names, results)
    }


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    """CLI interface for testing package security."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Package Security Verification")
    parser.add_argument("package", help="Package name to verify")
    parser.add_argument("--skip-pypi", action="store_true", help="Skip PyPI check")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    result = verify_package_security_sync(args.package, skip_pypi_check=args.skip_pypi)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"Package: {args.package}")
        print(f"Safe: {result['safe']}")
        print(f"Risk Level: {result['risk_level']}")
        print(f"Recommendation: {result['recommendation']}")
        if result["warnings"]:
            print("Warnings:")
            for w in result["warnings"]:
                print(f"  - {w}")
        if result["blocked_reason"]:
            print(f"Blocked Reason: {result['blocked_reason']}")
        if result["package_info"]:
            info = result["package_info"]
            print(f"Version: {info.get('version', 'unknown')}")
            if info.get("downloads"):
                print(f"Monthly Downloads: {info['downloads']:,}")


if __name__ == "__main__":
    main()
