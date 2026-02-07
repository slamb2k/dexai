"""
Metrics Route - Usage Statistics and Cost Tracking

Provides endpoints for metrics and analytics:
- GET summary stats (quick stats for dashboard cards)
- GET time series data for charts
- GET routing stats (model routing analytics)
"""

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from tools.dashboard.backend.database import (
    aggregate_metrics,
    get_quick_stats,
    get_routing_stats,
    get_routing_decisions,
)
from tools.dashboard.backend.models import (
    MetricsSummary,
    QuickStats,
    TimeSeriesData,
    TimeSeriesPoint,
    TimeSeriesResponse,
)


# Routing stats response model
class RoutingStatsResponse(BaseModel):
    """Response model for routing statistics."""
    total_queries: int
    complexity_distribution: dict[str, int]
    model_distribution: dict[str, int]
    exacto_percentage: float
    estimated_savings_usd: float
    total_cost_usd: float
    period_days: int


router = APIRouter()


def parse_period(period: str) -> tuple[datetime, datetime]:
    """
    Parse period string to start and end dates.

    Args:
        period: "24h", "7d", "30d", "90d"

    Returns:
        Tuple of (start_date, end_date)
    """
    now = datetime.now()
    end = now

    if period == "24h":
        start = now - timedelta(hours=24)
    elif period == "7d":
        start = now - timedelta(days=7)
    elif period == "30d":
        start = now - timedelta(days=30)
    elif period == "90d":
        start = now - timedelta(days=90)
    else:
        start = now - timedelta(days=7)  # Default to 7d

    return start, end


def period_to_granularity(period: str) -> str:
    """
    Get appropriate granularity for a time period.

    Args:
        period: "24h", "7d", "30d", "90d"

    Returns:
        Granularity string: "1h", "1d", etc.
    """
    if period == "24h":
        return "1h"
    elif period in ("7d", "30d"):
        return "1d"
    else:
        return "1d"


@router.get("/summary", response_model=MetricsSummary)
async def get_summary(period: str = Query("24h", description="Summary period: 24h, 7d, 30d")):
    """
    Get quick summary statistics for dashboard cards.

    Returns counts for today: tasks, messages, cost, active channels,
    average response time, and error rate.
    """
    stats_data = get_quick_stats()

    quick_stats = QuickStats(
        tasks_today=stats_data.get("tasks_today", 0),
        messages_today=stats_data.get("messages_today", 0),
        cost_today_usd=stats_data.get("cost_today_usd", 0.0),
        active_channels=stats_data.get("active_channels", 0),
        avg_response_time_ms=stats_data.get("avg_response_time_ms", 0.0),
        error_rate_percent=stats_data.get("error_rate_percent", 0.0),
    )

    return MetricsSummary(quick_stats=quick_stats, period=period, generated_at=datetime.now())


@router.get("/timeseries", response_model=TimeSeriesResponse)
async def get_timeseries(
    metrics: str = Query("tasks,messages,cost", description="Comma-separated metric names"),
    period: str = Query("7d", description="Time period: 24h, 7d, 30d, 90d"),
    aggregation: str = Query("sum", description="Aggregation: sum, avg, max, min"),
    granularity: str | None = Query(None, description="Data granularity: 1h, 1d"),
):
    """
    Get time series data for charts.

    Supports multiple metrics in a single request.
    Returns aggregated data points based on the specified period and granularity.
    """
    # Parse metric names
    metric_names = [m.strip() for m in metrics.split(",")]

    # Parse period
    start_date, end_date = parse_period(period)

    # Determine granularity
    if not granularity:
        granularity = period_to_granularity(period)

    # Map friendly metric names to database metric names
    metric_map = {
        "tasks": "task_count",
        "messages": "message_count",
        "cost": "api_cost_usd",
        "errors": "error_count",
        "response_time": "response_time_ms",
        "tokens_in": "tokens_input",
        "tokens_out": "tokens_output",
    }

    # Fetch data for each metric
    series_list = []
    for metric_name in metric_names:
        db_metric = metric_map.get(metric_name, metric_name)

        # Get aggregated data
        data_points = aggregate_metrics(
            metric_name=db_metric,
            aggregation=aggregation,
            start_date=start_date,
            end_date=end_date,
            group_by_interval=granularity,
        )

        # Convert to TimeSeriesPoint objects
        points = []
        for point in data_points:
            try:
                if isinstance(point["timestamp"], str):
                    # Handle different date formats
                    if len(point["timestamp"]) == 7:  # Week format: YYYY-WW
                        ts = datetime.strptime(point["timestamp"] + "-1", "%Y-%W-%w")
                    else:
                        ts = datetime.fromisoformat(point["timestamp"])
                else:
                    ts = point["timestamp"]

                points.append(
                    TimeSeriesPoint(
                        timestamp=ts,
                        value=float(point["value"]) if point["value"] else 0.0,
                        label=None,
                    )
                )
            except (ValueError, TypeError):
                continue

        # If no data, return empty series with proper structure
        if not points:
            # Generate empty time points for the period
            current = start_date
            while current <= end_date:
                points.append(TimeSeriesPoint(timestamp=current, value=0.0, label=None))
                if granularity == "1h":
                    current += timedelta(hours=1)
                else:
                    current += timedelta(days=1)

        series_list.append(
            TimeSeriesData(
                metric_name=metric_name, points=points, period=period, aggregation=aggregation
            )
        )

    return TimeSeriesResponse(series=series_list, period=period)


@router.post("/record")
async def record_metric(metric_name: str, value: float, labels: str | None = None):
    """
    Record a metric value.

    This endpoint is used internally to record metrics
    that will be displayed in the dashboard.
    """
    from tools.dashboard.backend.database import record_metric as db_record

    labels_dict = None
    if labels:
        import json

        try:
            labels_dict = json.loads(labels)
        except json.JSONDecodeError:
            labels_dict = {"raw": labels}

    metric_id = db_record(metric_name=metric_name, metric_value=value, labels=labels_dict)

    # Broadcast metrics update via WebSocket
    try:
        from tools.dashboard.backend.websocket import broadcast_metrics_update

        await broadcast_metrics_update()
    except Exception:
        pass

    return {"success": True, "metric_id": metric_id, "message": "Metric recorded"}


@router.get("/system")
async def get_system_metrics():
    """
    Get current system resource metrics.

    Returns CPU, memory, and disk usage percentages.
    Useful for monitoring system health.
    """
    system_metrics = {
        "cpu_percent": 0.0,
        "memory_percent": 0.0,
        "memory_used_mb": 0,
        "memory_total_mb": 0,
        "disk_percent": 0.0,
        "disk_used_gb": 0.0,
        "disk_total_gb": 0.0,
        "timestamp": datetime.now().isoformat(),
    }

    try:
        import psutil

        # CPU usage (non-blocking, uses cached value)
        system_metrics["cpu_percent"] = psutil.cpu_percent(interval=None)

        # Memory usage
        memory = psutil.virtual_memory()
        system_metrics["memory_percent"] = memory.percent
        system_metrics["memory_used_mb"] = round(memory.used / (1024 * 1024), 1)
        system_metrics["memory_total_mb"] = round(memory.total / (1024 * 1024), 1)

        # Disk usage
        disk = psutil.disk_usage("/")
        system_metrics["disk_percent"] = disk.percent
        system_metrics["disk_used_gb"] = round(disk.used / (1024 * 1024 * 1024), 2)
        system_metrics["disk_total_gb"] = round(disk.total / (1024 * 1024 * 1024), 2)

    except ImportError:
        # psutil not available
        system_metrics["error"] = "psutil not installed"
    except Exception as e:
        system_metrics["error"] = str(e)

    return system_metrics


@router.get("/routing", response_model=RoutingStatsResponse)
async def get_routing_metrics(
    days: int = Query(7, description="Number of days to include in stats", ge=1, le=90),
):
    """
    Get model routing statistics.

    Returns complexity distribution, model distribution, Exacto usage,
    and estimated cost savings from intelligent routing.
    """
    stats = get_routing_stats(days=days)

    return RoutingStatsResponse(
        total_queries=stats["total_queries"],
        complexity_distribution=stats["complexity"],
        model_distribution=stats["models"],
        exacto_percentage=stats["exacto_pct"],
        estimated_savings_usd=stats["estimated_savings_usd"],
        total_cost_usd=stats["total_cost_usd"],
        period_days=stats["period_days"],
    )


@router.get("/routing/decisions")
async def get_routing_decision_history(
    user_id: str | None = Query(None, description="Filter by user ID"),
    complexity: str | None = Query(None, description="Filter by complexity level"),
    limit: int = Query(100, description="Maximum results", ge=1, le=1000),
    offset: int = Query(0, description="Pagination offset", ge=0),
):
    """
    Get recent routing decisions with optional filters.

    Returns a list of routing decisions for debugging and analysis.
    """
    decisions = get_routing_decisions(
        user_id=user_id,
        complexity=complexity,
        limit=limit,
        offset=offset,
    )

    return {
        "decisions": decisions,
        "count": len(decisions),
        "limit": limit,
        "offset": offset,
    }


# =============================================================================
# Flow State
# =============================================================================


class FlowStateResponse(BaseModel):
    """Response model for flow state."""

    is_in_flow: bool
    flow_start_time: datetime | None = None
    duration_minutes: int = 0
    intensity: str = "none"  # none, building, deep, fading


@router.get("/flow", response_model=FlowStateResponse)
async def get_flow_state(user_id: str = "default"):
    """
    Get the current flow state.

    Flow state is determined by:
    - Continuous activity without interruptions
    - Focus on a single task
    - Low error rate

    Returns whether user is in flow and for how long.
    """
    flow_start_time = None
    duration_minutes = 0
    intensity = "none"
    is_in_flow = False

    try:
        # Check Dex state for hyperfocus
        from tools.dashboard.backend.database import get_dex_state

        dex_state = get_dex_state()
        if dex_state.get("state") == "hyperfocus":
            is_in_flow = True
            intensity = "deep"

            # Try to get start time from updated_at
            if dex_state.get("updated_at"):
                try:
                    flow_start_time = datetime.fromisoformat(dex_state["updated_at"])
                    duration_minutes = int((datetime.now() - flow_start_time).total_seconds() / 60)
                except Exception:
                    pass

    except Exception:
        pass

    # Also check flow detection settings/data
    try:
        from tools.dashboard.backend.routes.settings import load_yaml_config

        notif_config = load_yaml_config("smart_notifications.yaml")
        flow_config = notif_config.get("smart_notifications", {}).get("flow_detection", {})

        if flow_config.get("currently_in_flow"):
            is_in_flow = True
            if not intensity or intensity == "none":
                intensity = "building"

    except Exception:
        pass

    return FlowStateResponse(
        is_in_flow=is_in_flow,
        flow_start_time=flow_start_time,
        duration_minutes=duration_minutes,
        intensity=intensity,
    )
