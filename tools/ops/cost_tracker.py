"""
Per-API-call cost tracking.

Records model, tokens, and cost for every API call so that budget
alerting and analytics can query aggregated totals.

Usage:
    from tools.ops.cost_tracker import record_cost, get_daily_cost

    record_cost(user_id="owner", model="claude-sonnet-4-5", cost_usd=0.012)
    total = get_daily_cost()
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from tools.ops import DATA_DIR


try:
    from tools.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

DB_PATH = DATA_DIR / "audit.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS cost_tracking (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        user_id TEXT,
        channel TEXT,
        model TEXT NOT NULL,
        input_tokens INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        cost_usd REAL NOT NULL,
        session_key TEXT,
        complexity TEXT
    )""")
    conn.commit()
    return conn


def record_cost(
    model: str,
    cost_usd: float,
    user_id: str | None = None,
    channel: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    session_key: str | None = None,
    complexity: str | None = None,
) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO cost_tracking
            (user_id, channel, model, input_tokens, output_tokens, cost_usd, session_key, complexity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, channel, model, input_tokens, output_tokens, cost_usd, session_key, complexity),
        )
        row_id = cursor.lastrowid
        conn.commit()
        return row_id
    finally:
        conn.close()


def get_daily_cost(user_id: str | None = None) -> float:
    conn = get_connection()
    try:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        if user_id:
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) as total FROM cost_tracking WHERE timestamp >= ? AND user_id = ?",
                (today, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) as total FROM cost_tracking WHERE timestamp >= ?",
                (today,),
            ).fetchone()
        return row["total"]
    finally:
        conn.close()


def get_session_cost(session_key: str) -> float:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) as total FROM cost_tracking WHERE session_key = ?",
            (session_key,),
        ).fetchone()
        return row["total"]
    finally:
        conn.close()


def get_cost_summary(days: int = 7) -> dict[str, Any]:
    conn = get_connection()
    try:
        since = (datetime.now() - timedelta(days=days)).isoformat()

        total_row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) as total, COUNT(*) as calls FROM cost_tracking WHERE timestamp >= ?",
            (since,),
        ).fetchone()

        by_model_rows = conn.execute(
            "SELECT model, SUM(cost_usd) as total, COUNT(*) as calls FROM cost_tracking WHERE timestamp >= ? GROUP BY model ORDER BY total DESC",
            (since,),
        ).fetchall()

        by_day_rows = conn.execute(
            "SELECT DATE(timestamp) as day, SUM(cost_usd) as total FROM cost_tracking WHERE timestamp >= ? GROUP BY DATE(timestamp) ORDER BY day",
            (since,),
        ).fetchall()

        return {
            "period_days": days,
            "total_cost_usd": round(total_row["total"], 6),
            "total_calls": total_row["calls"],
            "by_model": {r["model"]: {"cost": round(r["total"], 6), "calls": r["calls"]} for r in by_model_rows},
            "by_day": [{"day": r["day"], "cost": round(r["total"], 6)} for r in by_day_rows],
        }
    finally:
        conn.close()


__all__ = ["get_cost_summary", "get_daily_cost", "get_session_cost", "record_cost"]
