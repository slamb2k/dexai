"""
Dynamic Malicious Package Feed (OSV/PyPI Advisory API)

Supplements the static MALICIOUS_PACKAGES blocklist with live queries
to the OSV.dev API for known vulnerabilities.

Features:
- Query OSV.dev for known vulnerabilities by package name and version
- SQLite cache with 24-hour TTL to reduce API calls
- Graceful fallback when OSV API is unreachable

Usage:
    from tools.security.advisory_feed import is_package_vulnerable

    result = is_package_vulnerable("requests", "2.31.0")
    if result["vulnerable"]:
        print(f"Advisories: {result['advisories']}")
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "data" / "advisory_cache.db"

OSV_API_URL = "https://api.osv.dev/v1/query"
CACHE_TTL_HOURS = 24


# =============================================================================
# Database
# =============================================================================


def _get_connection() -> sqlite3.Connection:
    """Get database connection, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    conn.execute("""
        CREATE TABLE IF NOT EXISTS advisory_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            package_name TEXT NOT NULL,
            version TEXT NOT NULL,
            advisories_json TEXT NOT NULL,
            fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(package_name, version)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_advisory_cache_pkg
        ON advisory_cache(package_name, version)
    """)
    conn.commit()
    return conn


# =============================================================================
# Cache Operations
# =============================================================================


def check_advisory_cache(
    package_name: str,
    version: str,
) -> list[dict] | None:
    """Check SQLite cache for advisory data.

    Args:
        package_name: PyPI package name.
        version: Package version string.

    Returns:
        List of advisory dicts if cache hit and within TTL, else None.
    """
    try:
        conn = _get_connection()
        cutoff = (datetime.utcnow() - timedelta(hours=CACHE_TTL_HOURS)).isoformat()
        row = conn.execute(
            "SELECT advisories_json, fetched_at FROM advisory_cache "
            "WHERE package_name = ? AND version = ? AND fetched_at > ?",
            (package_name.lower(), version, cutoff),
        ).fetchone()
        conn.close()

        if row:
            return json.loads(row["advisories_json"])
        return None
    except Exception as e:
        logger.warning(f"Advisory cache read error: {e}")
        return None


def update_advisory_cache(
    package_name: str,
    version: str,
    advisories: list[dict],
) -> None:
    """Write advisory data to SQLite cache.

    Args:
        package_name: PyPI package name.
        version: Package version string.
        advisories: List of advisory dicts to cache.
    """
    try:
        conn = _get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO advisory_cache "
            "(package_name, version, advisories_json, fetched_at) "
            "VALUES (?, ?, ?, ?)",
            (
                package_name.lower(),
                version,
                json.dumps(advisories),
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Advisory cache write error: {e}")


# =============================================================================
# OSV API
# =============================================================================


def query_osv(
    package_name: str,
    version: str,
) -> list[dict]:
    """Query the OSV.dev API for known vulnerabilities.

    Args:
        package_name: PyPI package name.
        version: Package version string.

    Returns:
        List of advisory dicts from OSV, each containing id, summary, and details.

    Raises:
        httpx.HTTPError: On network or API errors (caller should handle).
    """
    payload = {
        "package": {
            "name": package_name,
            "ecosystem": "PyPI",
        },
        "version": version,
    }

    with httpx.Client(timeout=10.0) as client:
        response = client.post(OSV_API_URL, json=payload)
        response.raise_for_status()

    data = response.json()
    vulns = data.get("vulns", [])

    advisories = []
    for vuln in vulns:
        advisories.append({
            "id": vuln.get("id", "unknown"),
            "summary": vuln.get("summary", ""),
            "details": vuln.get("details", ""),
            "aliases": vuln.get("aliases", []),
            "severity": _extract_severity(vuln),
        })

    return advisories


def _extract_severity(vuln: dict) -> str | None:
    """Extract severity string from an OSV vulnerability entry."""
    severity_list = vuln.get("severity", [])
    if severity_list:
        return severity_list[0].get("score", None)

    # Try database_specific or ecosystem_specific
    db_specific = vuln.get("database_specific", {})
    return db_specific.get("severity", None)


# =============================================================================
# Main Entry Point
# =============================================================================


def is_package_vulnerable(
    package_name: str,
    version: str,
) -> dict[str, Any]:
    """Check if a package version has known vulnerabilities.

    Checks the local cache first (24h TTL), then queries OSV.dev.
    Gracefully degrades if the API is unreachable.

    Args:
        package_name: PyPI package name.
        version: Package version string.

    Returns:
        {
            "vulnerable": bool,
            "advisories": list[dict],
            "source": "osv" | "cache",
            "error": str | None,
        }
    """
    # Check cache first
    cached = check_advisory_cache(package_name, version)
    if cached is not None:
        return {
            "vulnerable": len(cached) > 0,
            "advisories": cached,
            "source": "cache",
        }

    # Query OSV API
    try:
        advisories = query_osv(package_name, version)
        update_advisory_cache(package_name, version, advisories)
        return {
            "vulnerable": len(advisories) > 0,
            "advisories": advisories,
            "source": "osv",
        }
    except Exception as e:
        logger.warning(f"OSV API unreachable for {package_name}=={version}: {e}")
        return {
            "vulnerable": False,
            "advisories": [],
            "source": "osv",
            "error": "osv_unreachable",
        }
