"""
Budget watchdog — checks spend against configured thresholds
and pushes alerts via the dashboard WebSocket + audit trail.

Usage:
    from tools.ops.budget_alerter import BudgetWatchdog

    watchdog = BudgetWatchdog()
    alert = watchdog.check()
    if alert:
        print(alert)
"""

from __future__ import annotations

import logging
from typing import Any

import yaml

from tools.ops import PROJECT_ROOT
from tools.ops.cost_tracker import get_daily_cost, get_session_cost


try:
    from tools.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

ROUTING_CONFIG_PATH = PROJECT_ROOT / "args" / "routing.yaml"


def _load_thresholds() -> dict[str, Any]:
    if not ROUTING_CONFIG_PATH.exists():
        return {}
    with open(ROUTING_CONFIG_PATH) as f:
        config = yaml.safe_load(f) or {}
    return config.get("alert_thresholds", config.get("budget", {}))


class BudgetWatchdog:
    def __init__(self, thresholds: dict[str, Any] | None = None):
        self._thresholds = thresholds or _load_thresholds()

    def check(
        self,
        user_id: str | None = None,
        session_key: str | None = None,
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []

        daily_limit = self._thresholds.get("max_per_day_usd")
        if daily_limit is not None:
            daily_cost = get_daily_cost()
            if daily_cost >= daily_limit:
                alerts.append({
                    "level": "critical",
                    "type": "daily_budget_exceeded",
                    "limit_usd": daily_limit,
                    "current_usd": round(daily_cost, 4),
                })
            elif daily_cost >= daily_limit * 0.8:
                alerts.append({
                    "level": "warning",
                    "type": "daily_budget_80pct",
                    "limit_usd": daily_limit,
                    "current_usd": round(daily_cost, 4),
                })

        user_limit = self._thresholds.get("max_per_user_per_day_usd")
        if user_limit is not None and user_id:
            user_cost = get_daily_cost(user_id=user_id)
            if user_cost >= user_limit:
                alerts.append({
                    "level": "critical",
                    "type": "user_budget_exceeded",
                    "user_id": user_id,
                    "limit_usd": user_limit,
                    "current_usd": round(user_cost, 4),
                })

        session_limit = self._thresholds.get("max_per_session_usd")
        if session_limit is not None and session_key:
            session_cost = get_session_cost(session_key)
            if session_cost >= session_limit:
                alerts.append({
                    "level": "warning",
                    "type": "session_budget_exceeded",
                    "session_key": session_key,
                    "limit_usd": session_limit,
                    "current_usd": round(session_cost, 4),
                })

        for alert in alerts:
            self._emit(alert)

        return alerts

    def _emit(self, alert: dict[str, Any]) -> None:
        # Audit trail
        try:
            from tools.security.audit import log_event
            log_event(
                event_type="system",
                action="budget_alert",
                status="blocked" if alert["level"] == "critical" else "success",
                details=alert,
            )
        except ImportError:
            pass  # Audit module not available
        except Exception as e:
            logger.warning(f"Failed to log budget alert to audit: {e}")

        # WebSocket push
        try:
            from tools.dashboard.backend.websocket import sync_broadcast_activity
            sync_broadcast_activity({
                "event_type": "budget_alert",
                "severity": alert["level"],
                "summary": f"Budget alert: {alert['type']} (${alert['current_usd']:.2f} / ${alert['limit_usd']:.2f})",
                "details": alert,
            })
        except ImportError:
            pass  # WebSocket module not available
        except Exception as e:
            logger.warning(f"Failed to broadcast budget alert via WebSocket: {e}")

        logger.warning(f"Budget alert: {alert['type']} — ${alert['current_usd']:.2f} / ${alert['limit_usd']:.2f}")


__all__ = ["BudgetWatchdog"]
