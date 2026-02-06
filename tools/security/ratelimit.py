"""
Tool: Rate Limiter
Purpose: Prevent abuse through request throttling using token bucket algorithm

Features:
- Token bucket algorithm with configurable refill rate
- Per-user, per-channel, and global limits
- Cost-based tracking (API spend)
- Burst allowance for legitimate spikes
- Clear error messages with retry-after

Usage:
    python tools/security/ratelimit.py --check --user alice --cost 0.01
    python tools/security/ratelimit.py --consume --user alice --tokens 5 --cost 0.05
    python tools/security/ratelimit.py --status --user alice
    python tools/security/ratelimit.py --reset --user alice
    python tools/security/ratelimit.py --stats

Dependencies:
    - sqlite3 (stdlib)
    - time (stdlib)

Configuration:
    See args/rate_limits.yaml for limit values
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


# Database path
DB_PATH = Path(__file__).parent.parent.parent / "data" / "ratelimit.db"

# Config path
CONFIG_PATH = Path(__file__).parent.parent.parent / "args" / "rate_limits.yaml"

# Default limits (fallback if config not available)
DEFAULT_LIMITS = {
    "user": {
        "tokens_per_minute": 30,
        "max_tokens": 60,  # Burst capacity
        "cost_per_hour": 1.00,
        "cost_per_day": 10.00,
    },
    "channel": {"tokens_per_minute": 60, "max_tokens": 120},
    "global": {
        "tokens_per_minute": 1000,
        "max_tokens": 2000,
        "cost_per_hour": 10.00,
        "cost_per_day": 100.00,
    },
}


def load_config() -> dict:
    """Load rate limit configuration from YAML file."""
    if not CONFIG_PATH.exists():
        return DEFAULT_LIMITS

    try:
        import yaml

        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f)
        return config
    except ImportError:
        # YAML not available, use defaults
        return DEFAULT_LIMITS
    except Exception:
        return DEFAULT_LIMITS


def get_connection():
    """Get database connection, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rate_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT CHECK(entity_type IN ('user', 'channel', 'global')),
            entity_id TEXT NOT NULL,
            bucket_tokens REAL,
            last_refill DATETIME,
            cost_hour REAL DEFAULT 0,
            cost_day REAL DEFAULT 0,
            cost_reset_hour DATETIME,
            cost_reset_day DATETIME,
            total_requests INTEGER DEFAULT 0,
            total_cost REAL DEFAULT 0,
            last_request DATETIME,
            UNIQUE(entity_type, entity_id)
        )
    """)

    # Index for lookups
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_ratelimit_entity ON rate_limits(entity_type, entity_id)"
    )

    conn.commit()
    return conn


def get_limits(entity_type: str, entity_id: str = None) -> dict:
    """Get limits for an entity type/id."""
    config = load_config()

    if entity_type == "user":
        # Could have per-user or role-based limits
        return config.get("user", {}).get("standard", DEFAULT_LIMITS["user"])
    elif entity_type == "channel":
        return config.get("channel", {}).get("default", DEFAULT_LIMITS["channel"])
    else:
        return config.get("global", DEFAULT_LIMITS["global"])


def get_or_create_bucket(conn, entity_type: str, entity_id: str) -> dict[str, Any]:
    """Get or create a rate limit bucket."""
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM rate_limits WHERE entity_type = ? AND entity_id = ?
    """,
        (entity_type, entity_id),
    )

    row = cursor.fetchone()
    limits = get_limits(entity_type, entity_id)

    if row:
        return {
            "bucket_tokens": row["bucket_tokens"],
            "last_refill": row["last_refill"],
            "cost_hour": row["cost_hour"],
            "cost_day": row["cost_day"],
            "cost_reset_hour": row["cost_reset_hour"],
            "cost_reset_day": row["cost_reset_day"],
            "total_requests": row["total_requests"],
            "total_cost": row["total_cost"],
            "limits": limits,
        }
    else:
        # Create new bucket at max capacity
        max_tokens = limits.get("max_tokens", limits.get("tokens_per_minute", 30) * 2)
        now = datetime.now().isoformat()

        cursor.execute(
            """
            INSERT INTO rate_limits
            (entity_type, entity_id, bucket_tokens, last_refill,
             cost_hour, cost_day, cost_reset_hour, cost_reset_day)
            VALUES (?, ?, ?, ?, 0, 0, ?, ?)
        """,
            (entity_type, entity_id, max_tokens, now, now, now),
        )
        conn.commit()

        return {
            "bucket_tokens": max_tokens,
            "last_refill": now,
            "cost_hour": 0,
            "cost_day": 0,
            "cost_reset_hour": now,
            "cost_reset_day": now,
            "total_requests": 0,
            "total_cost": 0,
            "limits": limits,
        }


def refill_bucket(bucket: dict, limits: dict) -> float:
    """
    Refill tokens based on time elapsed since last refill.

    Returns:
        New token count
    """
    tokens_per_minute = limits.get("tokens_per_minute", 30)
    max_tokens = limits.get("max_tokens", tokens_per_minute * 2)

    last_refill = datetime.fromisoformat(bucket["last_refill"])
    elapsed = (datetime.now() - last_refill).total_seconds()

    # Tokens to add based on elapsed time
    tokens_to_add = (elapsed / 60) * tokens_per_minute

    # New token count (capped at max)
    new_tokens = min(max_tokens, bucket["bucket_tokens"] + tokens_to_add)

    return new_tokens


def reset_cost_if_needed(bucket: dict, limits: dict) -> dict:
    """Reset hourly/daily cost counters if period has elapsed."""
    now = datetime.now()
    updated = {}

    # Hourly reset
    if bucket["cost_reset_hour"]:
        reset_hour = datetime.fromisoformat(bucket["cost_reset_hour"])
        if (now - reset_hour).total_seconds() >= 3600:
            updated["cost_hour"] = 0
            updated["cost_reset_hour"] = now.isoformat()

    # Daily reset
    if bucket["cost_reset_day"]:
        reset_day = datetime.fromisoformat(bucket["cost_reset_day"])
        if (now - reset_day).total_seconds() >= 86400:
            updated["cost_day"] = 0
            updated["cost_reset_day"] = now.isoformat()

    return updated


def check_rate_limit(
    entity_type: str, entity_id: str, tokens: int = 1, cost: float = 0.0
) -> dict[str, Any]:
    """
    Check if a request would be allowed without consuming tokens.

    Args:
        entity_type: 'user', 'channel', or 'global'
        entity_id: Identifier for the entity
        tokens: Number of tokens this request would consume
        cost: Dollar cost of this request

    Returns:
        dict with allowed status and limit info
    """
    conn = get_connection()
    bucket = get_or_create_bucket(conn, entity_type, entity_id)
    limits = bucket["limits"]

    # Refill tokens
    current_tokens = refill_bucket(bucket, limits)

    # Check token limit
    if current_tokens < tokens:
        tokens_needed = tokens - current_tokens
        tokens_per_minute = limits.get("tokens_per_minute", 30)
        wait_seconds = (tokens_needed / tokens_per_minute) * 60

        conn.close()

        # Log rate limit exceeded to dashboard audit
        try:
            from tools.dashboard.backend.database import log_audit

            log_audit(
                event_type="security.rate_limit",
                severity="warning",
                actor=entity_id,
                target=f"{entity_type}:{entity_id}",
                details={
                    "reason": "token_limit",
                    "current_tokens": round(current_tokens, 2),
                    "required_tokens": tokens,
                    "retry_after_seconds": round(wait_seconds, 1),
                },
            )
        except Exception:
            pass

        return {
            "success": True,
            "allowed": False,
            "reason": "token_limit",
            "current_tokens": round(current_tokens, 2),
            "required_tokens": tokens,
            "retry_after_seconds": round(wait_seconds, 1),
            "message": f"Rate limit exceeded. Retry in {round(wait_seconds)}s",
        }

    # Reset cost counters if needed
    cost_updates = reset_cost_if_needed(bucket, limits)
    new_cost_hour = cost_updates.get("cost_hour", bucket["cost_hour"])
    new_cost_day = cost_updates.get("cost_day", bucket["cost_day"])

    # Check hourly cost limit
    cost_limit_hour = limits.get("cost_per_hour", 1.00)
    if new_cost_hour + cost > cost_limit_hour:
        conn.close()

        # Log cost limit exceeded to dashboard audit
        try:
            from tools.dashboard.backend.database import log_audit

            log_audit(
                event_type="security.cost_limit",
                severity="warning",
                actor=entity_id,
                target=f"{entity_type}:{entity_id}",
                details={
                    "reason": "cost_limit_hour",
                    "current_cost": round(new_cost_hour, 4),
                    "cost_limit": cost_limit_hour,
                },
            )
        except Exception:
            pass

        return {
            "success": True,
            "allowed": False,
            "reason": "cost_limit_hour",
            "current_cost_hour": round(new_cost_hour, 4),
            "cost_limit_hour": cost_limit_hour,
            "message": f"Hourly cost limit (${cost_limit_hour}) exceeded",
        }

    # Check daily cost limit
    cost_limit_day = limits.get("cost_per_day", 10.00)
    if new_cost_day + cost > cost_limit_day:
        conn.close()

        # Log cost limit exceeded to dashboard audit
        try:
            from tools.dashboard.backend.database import log_audit

            log_audit(
                event_type="security.cost_limit",
                severity="warning",
                actor=entity_id,
                target=f"{entity_type}:{entity_id}",
                details={
                    "reason": "cost_limit_day",
                    "current_cost": round(new_cost_day, 4),
                    "cost_limit": cost_limit_day,
                },
            )
        except Exception:
            pass

        return {
            "success": True,
            "allowed": False,
            "reason": "cost_limit_day",
            "current_cost_day": round(new_cost_day, 4),
            "cost_limit_day": cost_limit_day,
            "message": f"Daily cost limit (${cost_limit_day}) exceeded",
        }

    conn.close()
    return {
        "success": True,
        "allowed": True,
        "current_tokens": round(current_tokens, 2),
        "tokens_after": round(current_tokens - tokens, 2),
        "cost_hour_after": round(new_cost_hour + cost, 4),
        "cost_day_after": round(new_cost_day + cost, 4),
    }


def consume_tokens(
    entity_type: str, entity_id: str, tokens: int = 1, cost: float = 0.0
) -> dict[str, Any]:
    """
    Consume tokens and record cost for a request.

    Args:
        entity_type: 'user', 'channel', or 'global'
        entity_id: Identifier for the entity
        tokens: Number of tokens to consume
        cost: Dollar cost to record

    Returns:
        dict with success status and new limits
    """
    # First check if allowed
    check_result = check_rate_limit(entity_type, entity_id, tokens, cost)
    if not check_result["allowed"]:
        return check_result

    conn = get_connection()
    bucket = get_or_create_bucket(conn, entity_type, entity_id)
    limits = bucket["limits"]
    cursor = conn.cursor()

    # Refill tokens
    current_tokens = refill_bucket(bucket, limits)

    # Consume tokens
    new_tokens = current_tokens - tokens
    now = datetime.now().isoformat()

    # Reset cost counters if needed
    cost_updates = reset_cost_if_needed(bucket, limits)
    new_cost_hour = cost_updates.get("cost_hour", bucket["cost_hour"]) + cost
    new_cost_day = cost_updates.get("cost_day", bucket["cost_day"]) + cost
    cost_reset_hour = cost_updates.get("cost_reset_hour", bucket["cost_reset_hour"])
    cost_reset_day = cost_updates.get("cost_reset_day", bucket["cost_reset_day"])

    cursor.execute(
        """
        UPDATE rate_limits SET
            bucket_tokens = ?,
            last_refill = ?,
            cost_hour = ?,
            cost_day = ?,
            cost_reset_hour = ?,
            cost_reset_day = ?,
            total_requests = total_requests + 1,
            total_cost = total_cost + ?,
            last_request = ?
        WHERE entity_type = ? AND entity_id = ?
    """,
        (
            new_tokens,
            now,
            new_cost_hour,
            new_cost_day,
            cost_reset_hour,
            cost_reset_day,
            cost,
            now,
            entity_type,
            entity_id,
        ),
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "allowed": True,
        "consumed": True,
        "tokens_remaining": round(new_tokens, 2),
        "cost_hour": round(new_cost_hour, 4),
        "cost_day": round(new_cost_day, 4),
    }


def get_status(entity_type: str, entity_id: str) -> dict[str, Any]:
    """Get current rate limit status for an entity."""
    conn = get_connection()
    bucket = get_or_create_bucket(conn, entity_type, entity_id)
    limits = bucket["limits"]

    # Refill tokens
    current_tokens = refill_bucket(bucket, limits)

    # Reset cost counters if needed
    cost_updates = reset_cost_if_needed(bucket, limits)
    current_cost_hour = cost_updates.get("cost_hour", bucket["cost_hour"])
    current_cost_day = cost_updates.get("cost_day", bucket["cost_day"])

    conn.close()

    max_tokens = limits.get("max_tokens", limits.get("tokens_per_minute", 30) * 2)
    cost_limit_hour = limits.get("cost_per_hour", 1.00)
    cost_limit_day = limits.get("cost_per_day", 10.00)

    return {
        "success": True,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "tokens": {
            "current": round(current_tokens, 2),
            "max": max_tokens,
            "refill_rate": limits.get("tokens_per_minute", 30),
        },
        "cost": {
            "hour": {
                "current": round(current_cost_hour, 4),
                "limit": cost_limit_hour,
                "remaining": round(cost_limit_hour - current_cost_hour, 4),
            },
            "day": {
                "current": round(current_cost_day, 4),
                "limit": cost_limit_day,
                "remaining": round(cost_limit_day - current_cost_day, 4),
            },
        },
        "totals": {"requests": bucket["total_requests"], "cost": round(bucket["total_cost"], 4)},
        "last_request": bucket.get("last_request"),
    }


def reset_limits(entity_type: str, entity_id: str) -> dict[str, Any]:
    """Reset rate limits for an entity."""
    conn = get_connection()
    limits = get_limits(entity_type, entity_id)
    max_tokens = limits.get("max_tokens", limits.get("tokens_per_minute", 30) * 2)
    now = datetime.now().isoformat()

    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE rate_limits SET
            bucket_tokens = ?,
            last_refill = ?,
            cost_hour = 0,
            cost_day = 0,
            cost_reset_hour = ?,
            cost_reset_day = ?
        WHERE entity_type = ? AND entity_id = ?
    """,
        (max_tokens, now, now, now, entity_type, entity_id),
    )

    if cursor.rowcount == 0:
        conn.close()
        return {
            "success": False,
            "error": f"No rate limit record found for {entity_type}/{entity_id}",
        }

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Rate limits reset for {entity_type}/{entity_id}",
        "tokens": max_tokens,
    }


def get_stats() -> dict[str, Any]:
    """Get overall rate limiting statistics."""
    conn = get_connection()
    cursor = conn.cursor()

    # Total entities tracked
    cursor.execute("SELECT entity_type, COUNT(*) as count FROM rate_limits GROUP BY entity_type")
    by_type = {row["entity_type"]: row["count"] for row in cursor.fetchall()}

    # Total requests and cost
    cursor.execute(
        "SELECT SUM(total_requests) as requests, SUM(total_cost) as cost FROM rate_limits"
    )
    row = cursor.fetchone()
    total_requests = row["requests"] or 0
    total_cost = row["cost"] or 0

    # Most active users
    cursor.execute("""
        SELECT entity_id, total_requests, total_cost
        FROM rate_limits
        WHERE entity_type = 'user'
        ORDER BY total_requests DESC
        LIMIT 10
    """)
    top_users = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return {
        "success": True,
        "stats": {
            "entities_by_type": by_type,
            "total_requests": total_requests,
            "total_cost": round(total_cost, 4),
            "top_users": top_users,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Rate Limiter")
    parser.add_argument("--check", action="store_true", help="Check if request would be allowed")
    parser.add_argument("--consume", action="store_true", help="Consume tokens for a request")
    parser.add_argument("--status", action="store_true", help="Get current status")
    parser.add_argument("--reset", action="store_true", help="Reset limits for an entity")
    parser.add_argument("--stats", action="store_true", help="Get overall statistics")

    parser.add_argument("--user", help="User ID")
    parser.add_argument("--channel", help="Channel ID")
    parser.add_argument(
        "--global", dest="is_global", action="store_true", help="Check/consume global limits"
    )

    parser.add_argument("--tokens", type=int, default=1, help="Tokens to check/consume")
    parser.add_argument("--cost", type=float, default=0.0, help="Dollar cost of request")

    args = parser.parse_args()

    # Determine entity type and ID
    if args.is_global:
        entity_type = "global"
        entity_id = "system"
    elif args.channel:
        entity_type = "channel"
        entity_id = args.channel
    elif args.user:
        entity_type = "user"
        entity_id = args.user
    else:
        if not args.stats:
            print("Error: Must specify --user, --channel, or --global")
            sys.exit(1)
        entity_type = None
        entity_id = None

    result = None

    if args.check:
        result = check_rate_limit(entity_type, entity_id, args.tokens, args.cost)
    elif args.consume:
        result = consume_tokens(entity_type, entity_id, args.tokens, args.cost)
    elif args.status:
        result = get_status(entity_type, entity_id)
    elif args.reset:
        result = reset_limits(entity_type, entity_id)
    elif args.stats:
        result = get_stats()
    else:
        print("Error: Must specify an action (--check, --consume, --status, --reset, --stats)")
        sys.exit(1)

    if result.get("success"):
        if result.get("allowed") is False:
            print(f"BLOCKED {result.get('message', 'Rate limit exceeded')}")
        else:
            print(f"OK {result.get('message', 'Success')}")
    else:
        print(f"ERROR {result.get('error')}")
        sys.exit(1)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
