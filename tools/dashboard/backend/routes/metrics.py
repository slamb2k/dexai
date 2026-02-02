"""
Metrics Route - Usage Statistics and Cost Tracking

Provides endpoints for metrics and analytics:
- GET summary stats (quick stats for dashboard cards)
- GET time series data for charts
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Query

from tools.dashboard.backend.database import aggregate_metrics, get_quick_stats
from tools.dashboard.backend.models import (
    MetricsSummary,
    QuickStats,
    TimeSeriesData,
    TimeSeriesPoint,
    TimeSeriesResponse,
)


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
