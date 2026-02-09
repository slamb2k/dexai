"""
Pydantic models for Dashboard API request/response types.

These models define the data structures for all dashboard endpoints,
providing validation, serialization, and documentation.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================


class AvatarState(str, Enum):
    """Valid states for the Dex avatar."""

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    WORKING = "working"
    SUCCESS = "success"
    ERROR = "error"
    SLEEPING = "sleeping"
    HYPERFOCUS = "hyperfocus"
    WAITING = "waiting"


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EventSeverity(str, Enum):
    """Event severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class EventType(str, Enum):
    """Types of dashboard events."""

    MESSAGE = "message"
    TASK = "task"
    SYSTEM = "system"
    ERROR = "error"
    LLM = "llm"
    SECURITY = "security"


# =============================================================================
# Status Models
# =============================================================================


class DexStatus(BaseModel):
    """Current Dex state for avatar display."""

    state: AvatarState = Field(default=AvatarState.IDLE, description="Current avatar state")
    current_task: str | None = Field(None, description="Description of current task")
    uptime_seconds: int = Field(default=0, description="System uptime in seconds")
    version: str = Field(default="0.1.0", description="DexAI version")
    last_activity: datetime | None = Field(None, description="Timestamp of last activity")


class HealthCheck(BaseModel):
    """Health check response."""

    status: str = Field(default="healthy", description="Overall system status")
    version: str = Field(default="0.1.0", description="API version")
    timestamp: datetime = Field(default_factory=datetime.now, description="Check timestamp")
    services: dict[str, str] = Field(
        default_factory=dict, description="Individual service statuses"
    )


# =============================================================================
# Task Models
# =============================================================================


class TaskSummary(BaseModel):
    """Summary of a task for list views."""

    id: str = Field(..., description="Task ID")
    request: str = Field(..., description="Original task request")
    status: TaskStatus = Field(..., description="Current status")
    channel: str | None = Field(None, description="Source channel")
    created_at: datetime = Field(..., description="Creation timestamp")
    completed_at: datetime | None = Field(None, description="Completion timestamp")
    duration_seconds: float | None = Field(None, description="Execution duration")
    cost_usd: float | None = Field(None, description="Estimated cost in USD")


class TaskDetail(TaskSummary):
    """Full task details including execution info."""

    response: str | None = Field(None, description="Task response/output")
    tools_used: list[str] = Field(default_factory=list, description="Tools invoked")
    tokens_in: int | None = Field(None, description="Input tokens consumed")
    tokens_out: int | None = Field(None, description="Output tokens generated")
    error_message: str | None = Field(None, description="Error if failed")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class TaskListResponse(BaseModel):
    """Paginated list of tasks."""

    tasks: list[TaskSummary] = Field(default_factory=list, description="Task list")
    total: int = Field(default=0, description="Total matching tasks")
    page: int = Field(default=1, description="Current page")
    page_size: int = Field(default=20, description="Items per page")
    has_more: bool = Field(default=False, description="More pages available")


class TaskFilters(BaseModel):
    """Filters for task queries."""

    status: TaskStatus | None = Field(None, description="Filter by status")
    channel: str | None = Field(None, description="Filter by channel")
    start_date: datetime | None = Field(None, description="Start of date range")
    end_date: datetime | None = Field(None, description="End of date range")
    search: str | None = Field(None, description="Search in request text")


# =============================================================================
# Activity Models
# =============================================================================


class ActivityEvent(BaseModel):
    """Single activity event."""

    id: int = Field(..., description="Event ID")
    event_type: EventType = Field(..., description="Type of event")
    timestamp: datetime = Field(..., description="Event timestamp")
    channel: str | None = Field(None, description="Related channel")
    user_id: str | None = Field(None, description="Related user")
    summary: str = Field(..., description="Short description")
    details: dict[str, Any] | None = Field(None, description="Full event data")
    severity: EventSeverity = Field(default=EventSeverity.INFO, description="Severity level")


class ActivityFeed(BaseModel):
    """Paginated activity feed."""

    events: list[ActivityEvent] = Field(default_factory=list, description="Activity events")
    total: int = Field(default=0, description="Total matching events")
    cursor: str | None = Field(None, description="Cursor for next page")
    has_more: bool = Field(default=False, description="More events available")


class NewActivityEvent(BaseModel):
    """Request to log a new activity event."""

    event_type: EventType = Field(..., description="Type of event")
    summary: str = Field(..., description="Short description")
    channel: str | None = Field(None, description="Related channel")
    user_id: str | None = Field(None, description="Related user")
    details: dict[str, Any] | None = Field(None, description="Full event data")
    severity: EventSeverity = Field(default=EventSeverity.INFO, description="Severity level")


# =============================================================================
# Metrics Models
# =============================================================================


class QuickStats(BaseModel):
    """Quick summary statistics for dashboard cards."""

    tasks_today: int = Field(default=0, description="Tasks completed today")
    messages_today: int = Field(default=0, description="Messages processed today")
    cost_today_usd: float = Field(default=0.0, description="Cost incurred today")
    active_channels: int = Field(default=0, description="Number of active channels")
    avg_response_time_ms: float = Field(default=0.0, description="Average response time")
    error_rate_percent: float = Field(default=0.0, description="Error rate percentage")


class MetricsSummary(BaseModel):
    """Summary of metrics for dashboard display."""

    quick_stats: QuickStats = Field(default_factory=QuickStats, description="Quick stats")
    period: str = Field(default="24h", description="Summary period")
    generated_at: datetime = Field(default_factory=datetime.now, description="Generation time")


class TimeSeriesPoint(BaseModel):
    """Single point in a time series."""

    timestamp: datetime = Field(..., description="Point timestamp")
    value: float = Field(..., description="Metric value")
    label: str | None = Field(None, description="Optional label")


class TimeSeriesData(BaseModel):
    """Time series data for charts."""

    metric_name: str = Field(..., description="Metric being tracked")
    points: list[TimeSeriesPoint] = Field(default_factory=list, description="Data points")
    period: str = Field(default="24h", description="Time period")
    aggregation: str = Field(default="sum", description="Aggregation method")


class TimeSeriesRequest(BaseModel):
    """Request for time series data."""

    metrics: list[str] = Field(..., description="Metrics to fetch")
    period: str = Field(default="7d", description="Time period: 24h, 7d, 30d")
    aggregation: str = Field(default="sum", description="Aggregation: sum, avg, max, min")
    granularity: str = Field(default="1h", description="Data point granularity")


class TimeSeriesResponse(BaseModel):
    """Response containing multiple time series."""

    series: list[TimeSeriesData] = Field(default_factory=list, description="Time series data")
    period: str = Field(default="7d", description="Requested period")


# =============================================================================
# Settings Models
# =============================================================================


class SkillDependencySettings(BaseModel):
    """Settings for skill dependency installation."""

    install_mode: str = Field(
        default="ask",
        description="How to handle skill dependencies: 'ask' (prompt user), 'always' (auto-install after security check), 'never' (suggest alternatives)",
    )


class NotificationSettings(BaseModel):
    """Notification preferences."""

    enabled: bool = Field(default=True, description="Notifications enabled")
    quiet_hours_start: str | None = Field(None, description="Start of quiet hours (HH:MM)")
    quiet_hours_end: str | None = Field(None, description="End of quiet hours (HH:MM)")
    channels: list[str] = Field(default_factory=list, description="Enabled notification channels")


class PrivacySettings(BaseModel):
    """Privacy preferences."""

    remember_conversations: bool = Field(default=True, description="Remember conversation history")
    log_activity: bool = Field(default=True, description="Log activity events")
    data_retention_days: int = Field(default=90, description="Data retention period")


class DashboardSettings(BaseModel):
    """All dashboard settings."""

    display_name: str = Field(default="User", description="Display name")
    timezone: str = Field(default="UTC", description="User timezone")
    language: str = Field(default="en", description="Preferred language")
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    privacy: PrivacySettings = Field(default_factory=PrivacySettings)
    skill_dependencies: SkillDependencySettings = Field(default_factory=SkillDependencySettings)
    theme: str = Field(default="dark", description="UI theme")
    sidebar_collapsed: bool = Field(default=False, description="Sidebar state")


class SettingsUpdate(BaseModel):
    """Partial settings update request."""

    display_name: str | None = Field(None, description="Display name")
    timezone: str | None = Field(None, description="User timezone")
    language: str | None = Field(None, description="Preferred language")
    notifications: NotificationSettings | None = Field(None)
    privacy: PrivacySettings | None = Field(None)
    skill_dependencies: SkillDependencySettings | None = Field(None)
    theme: str | None = Field(None, description="UI theme")
    sidebar_collapsed: bool | None = Field(None, description="Sidebar state")


# =============================================================================
# WebSocket Models
# =============================================================================


class WSMessage(BaseModel):
    """WebSocket message wrapper."""

    event: str = Field(..., description="Event type")
    data: dict[str, Any] = Field(default_factory=dict, description="Event payload")
    timestamp: datetime = Field(default_factory=datetime.now, description="Event time")


class StateChangeEvent(BaseModel):
    """Dex state change event."""

    state: AvatarState = Field(..., description="New avatar state")
    task: str | None = Field(None, description="Current task if any")
    previous_state: AvatarState | None = Field(None, description="Previous state")


# =============================================================================
# Error Models
# =============================================================================


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error message")
    code: str = Field(default="INTERNAL_ERROR", description="Error code")
    details: dict[str, Any] | None = Field(None, description="Additional details")


class ValidationError(BaseModel):
    """Validation error details."""

    field: str = Field(..., description="Field with error")
    message: str = Field(..., description="Error message")
    value: Any | None = Field(None, description="Invalid value")
