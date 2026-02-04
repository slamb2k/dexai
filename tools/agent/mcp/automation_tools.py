"""
DexAI Automation MCP Tools

Exposes DexAI's scheduling and notification features as MCP tools for the Claude Agent SDK.

Tools:
- dexai_schedule: Create a scheduled job (cron, heartbeat, or trigger)
- dexai_schedule_list: List scheduled jobs
- dexai_notify: Send a notification to a user
- dexai_reminder: Set a reminder (convenience: schedule + notify)

Usage:
    These tools are registered with the SDK via the agent configuration.
    The SDK agent invokes them as needed during conversations.
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Tool: dexai_schedule
# =============================================================================


def dexai_schedule(
    name: str,
    task: str,
    schedule: str,
    job_type: str = "cron",
    timeout_seconds: int = 120,
    cost_limit: float = 0.50,
    enabled: bool = True,
) -> dict[str, Any]:
    """
    Create a scheduled job to run at specified times.

    Args:
        name: Unique job name (e.g., "morning_briefing")
        task: Task description/prompt to execute
        schedule: Cron expression (e.g., "0 7 * * *" for daily at 7am)
        job_type: "cron", "heartbeat", or "trigger"
        timeout_seconds: Max execution time (default 120)
        cost_limit: Max cost in USD (default 0.50)
        enabled: Whether job is active (default True)

    Returns:
        Dict with job ID and next scheduled run

    Example:
        Input: name="daily_standup", schedule="0 9 * * 1-5", task="Summarize tasks"
        Output: {
            "job_id": "abc123",
            "name": "daily_standup",
            "next_run": "2026-02-05T09:00:00"
        }
    """
    try:
        from tools.automation import scheduler

        result = scheduler.create_job(
            name=name,
            job_type=job_type,
            task=task,
            schedule=schedule,
            timeout_seconds=timeout_seconds,
            cost_limit=cost_limit,
            enabled=enabled,
        )

        if not result.get("success"):
            return {
                "success": False,
                "tool": "dexai_schedule",
                "error": result.get("error", "Failed to create job"),
            }

        return {
            "success": True,
            "tool": "dexai_schedule",
            "job_id": result.get("job_id"),
            "name": result.get("name"),
            "job_type": job_type,
            "schedule": schedule,
            "next_run": result.get("next_run"),
            "message": f"Scheduled job '{name}' created",
        }

    except ImportError as e:
        return {
            "success": False,
            "tool": "dexai_schedule",
            "error": f"Scheduler module not available: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_schedule",
            "error": str(e),
        }


# =============================================================================
# Tool: dexai_schedule_list
# =============================================================================


def dexai_schedule_list(
    job_type: str | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """
    List scheduled jobs.

    Args:
        job_type: Optional filter by type ("cron", "heartbeat", "trigger")
        enabled: Optional filter by enabled status

    Returns:
        Dict with list of jobs
    """
    try:
        from tools.automation import scheduler

        jobs = scheduler.list_jobs(job_type=job_type, enabled=enabled)

        return {
            "success": True,
            "tool": "dexai_schedule_list",
            "count": len(jobs),
            "jobs": [
                {
                    "id": j.get("id"),
                    "name": j.get("name"),
                    "job_type": j.get("job_type"),
                    "schedule": j.get("schedule"),
                    "enabled": j.get("enabled"),
                    "next_run": j.get("next_run"),
                    "last_run": j.get("last_run"),
                }
                for j in jobs
            ],
        }

    except ImportError as e:
        return {
            "success": False,
            "tool": "dexai_schedule_list",
            "error": f"Scheduler module not available: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_schedule_list",
            "error": str(e),
        }


# =============================================================================
# Tool: dexai_schedule_manage
# =============================================================================


def dexai_schedule_manage(
    job_id: str,
    action: str,
) -> dict[str, Any]:
    """
    Manage a scheduled job (enable, disable, delete, run now).

    Args:
        job_id: Job ID or name
        action: "enable", "disable", "delete", or "run"

    Returns:
        Dict with action result
    """
    try:
        from tools.automation import scheduler

        if action == "enable":
            result = scheduler.enable_job(job_id)
        elif action == "disable":
            result = scheduler.disable_job(job_id)
        elif action == "delete":
            result = scheduler.delete_job(job_id)
        elif action == "run":
            result = scheduler.run_job(job_id, triggered_by="manual")
        else:
            return {
                "success": False,
                "tool": "dexai_schedule_manage",
                "error": f"Invalid action: {action}. Must be enable, disable, delete, or run",
            }

        return {
            "success": result.get("success", False),
            "tool": "dexai_schedule_manage",
            "action": action,
            "job_id": job_id,
            "message": result.get("message", f"Job {action}d"),
        }

    except ImportError as e:
        return {
            "success": False,
            "tool": "dexai_schedule_manage",
            "error": f"Scheduler module not available: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_schedule_manage",
            "error": str(e),
        }


# =============================================================================
# Tool: dexai_notify
# =============================================================================


def dexai_notify(
    user_id: str,
    content: str,
    priority: str = "normal",
    channel: str | None = None,
    source: str = "agent",
    flow_aware: bool = True,
) -> dict[str, Any]:
    """
    Send a notification to a user.

    ADHD-aware: By default uses flow awareness to suppress low-priority
    notifications when user is in focus mode.

    Args:
        user_id: Target user ID
        content: Notification message
        priority: "low", "normal", "high", or "urgent"
        channel: Specific channel (or None for user's preferred channel)
        source: Source identifier (default "agent")
        flow_aware: Check flow state before sending (default True)

    Returns:
        Dict with notification result

    Example:
        Input: user_id="alice", content="Your task is complete!", priority="normal"
        Output: {
            "sent": true,
            "notification_id": "xyz789",
            "channel": "telegram"
        }
    """
    try:
        from tools.automation import notify

        # Validate priority
        valid_priorities = ["low", "normal", "high", "urgent"]
        if priority not in valid_priorities:
            return {
                "success": False,
                "tool": "dexai_notify",
                "error": f"Invalid priority: {priority}. Must be one of {valid_priorities}",
            }

        if flow_aware:
            # Use flow-aware sending
            result = asyncio.run(
                notify.send_with_flow_awareness(
                    user_id=user_id,
                    content=content,
                    priority=priority,
                    channel=channel,
                    source=source,
                )
            )
        else:
            # Queue and send immediately
            notification_id = notify.queue_notification(
                user_id=user_id,
                content=content,
                priority=priority,
                channel=channel,
                source=source,
            )
            result = asyncio.run(notify.send_notification(notification_id))
            result["notification_id"] = notification_id

        if result.get("suppressed"):
            return {
                "success": True,
                "tool": "dexai_notify",
                "sent": False,
                "suppressed": True,
                "suppression_id": result.get("suppression_id"),
                "reason": "User in flow state - notification queued for later",
                "flow_score": result.get("flow_score"),
            }

        return {
            "success": result.get("success", False),
            "tool": "dexai_notify",
            "sent": result.get("success", False),
            "suppressed": False,
            "notification_id": result.get("notification_id"),
            "channel": result.get("channel"),
            "message": "Notification sent" if result.get("success") else result.get("error"),
        }

    except ImportError as e:
        return {
            "success": False,
            "tool": "dexai_notify",
            "error": f"Notify module not available: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_notify",
            "error": str(e),
        }


# =============================================================================
# Tool: dexai_reminder
# =============================================================================


def dexai_reminder(
    user_id: str,
    content: str,
    when: str,
    priority: str = "normal",
) -> dict[str, Any]:
    """
    Set a reminder for a user at a specified time.

    This is a convenience tool that creates a scheduled job to send a
    notification at the specified time.

    Args:
        user_id: Target user ID
        content: Reminder message
        when: When to remind - supports:
            - Relative: "in 30 minutes", "in 2 hours", "tomorrow at 9am"
            - Cron: "0 9 * * *" (daily at 9am)
            - ISO datetime: "2026-02-05T15:00:00"
        priority: Notification priority (default "normal")

    Returns:
        Dict with reminder details

    Example:
        Input: user_id="alice", content="Call dentist", when="in 30 minutes"
        Output: {
            "reminder_id": "abc123",
            "scheduled_for": "2026-02-04T14:30:00"
        }
    """
    try:
        from tools.automation import scheduler, notify
        import uuid

        # Parse the "when" parameter
        now = datetime.now()
        schedule_time = None
        cron_expression = None

        # Check for relative time
        when_lower = when.lower().strip()

        if when_lower.startswith("in "):
            # Parse relative time like "in 30 minutes", "in 2 hours"
            parts = when_lower[3:].split()
            if len(parts) >= 2:
                try:
                    amount = int(parts[0])
                    unit = parts[1].rstrip("s")  # Remove trailing 's'

                    if unit == "minute":
                        schedule_time = now + timedelta(minutes=amount)
                    elif unit == "hour":
                        schedule_time = now + timedelta(hours=amount)
                    elif unit == "day":
                        schedule_time = now + timedelta(days=amount)
                    elif unit == "week":
                        schedule_time = now + timedelta(weeks=amount)
                except ValueError:
                    pass

        elif when_lower == "tomorrow":
            schedule_time = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0)

        elif when_lower.startswith("tomorrow at "):
            # Parse "tomorrow at 9am" or "tomorrow at 14:00"
            time_str = when_lower[12:].strip()
            try:
                if "am" in time_str or "pm" in time_str:
                    # Parse 9am, 2pm format
                    time_str = time_str.replace("am", "").replace("pm", "")
                    hour = int(time_str)
                    if "pm" in when_lower and hour != 12:
                        hour += 12
                    schedule_time = (now + timedelta(days=1)).replace(
                        hour=hour, minute=0, second=0
                    )
                else:
                    # Parse 14:00 format
                    parts = time_str.split(":")
                    schedule_time = (now + timedelta(days=1)).replace(
                        hour=int(parts[0]),
                        minute=int(parts[1]) if len(parts) > 1 else 0,
                        second=0,
                    )
            except (ValueError, IndexError):
                pass

        elif " " in when and when.count(" ") == 4 and "*" in when:
            # Looks like a cron expression
            cron_expression = when

        else:
            # Try to parse as ISO datetime
            try:
                schedule_time = datetime.fromisoformat(when)
            except ValueError:
                return {
                    "success": False,
                    "tool": "dexai_reminder",
                    "error": f"Could not parse time: {when}. Try 'in 30 minutes', 'tomorrow at 9am', or ISO format.",
                }

        if not schedule_time and not cron_expression:
            return {
                "success": False,
                "tool": "dexai_reminder",
                "error": f"Could not parse time: {when}",
            }

        # Create a unique reminder name
        reminder_id = str(uuid.uuid4())[:8]
        job_name = f"reminder_{user_id}_{reminder_id}"

        # If we have a specific time, convert to cron expression for one-time run
        if schedule_time:
            # Create cron expression for specific time
            cron_expression = f"{schedule_time.minute} {schedule_time.hour} {schedule_time.day} {schedule_time.month} *"

        # Create the scheduled job
        task = json.dumps({
            "type": "reminder",
            "user_id": user_id,
            "content": content,
            "priority": priority,
        })

        result = scheduler.create_job(
            name=job_name,
            job_type="cron",
            task=task,
            schedule=cron_expression,
            timeout_seconds=30,
            cost_limit=0.05,
            enabled=True,
        )

        if not result.get("success"):
            return {
                "success": False,
                "tool": "dexai_reminder",
                "error": result.get("error", "Failed to create reminder"),
            }

        scheduled_for = schedule_time.isoformat() if schedule_time else result.get("next_run")

        return {
            "success": True,
            "tool": "dexai_reminder",
            "reminder_id": reminder_id,
            "job_name": job_name,
            "user_id": user_id,
            "content": content,
            "scheduled_for": scheduled_for,
            "message": f"Reminder set for {scheduled_for}",
        }

    except ImportError as e:
        return {
            "success": False,
            "tool": "dexai_reminder",
            "error": f"Scheduler module not available: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_reminder",
            "error": str(e),
        }


# =============================================================================
# Tool: dexai_suppressed_count
# =============================================================================


def dexai_suppressed_count(
    user_id: str,
) -> dict[str, Any]:
    """
    Get count of notifications suppressed during flow state.

    ADHD-aware: Shows how many notifications are waiting without
    overwhelming the user with details.

    Args:
        user_id: User identifier

    Returns:
        Dict with count by priority
    """
    try:
        from tools.automation import notify

        result = notify.get_suppressed_count(user_id)

        if not result.get("success"):
            return {
                "success": False,
                "tool": "dexai_suppressed_count",
                "error": result.get("error", "Failed to get count"),
            }

        count = result.get("count", 0)
        priorities = result.get("priorities", {})

        # ADHD-friendly message
        if count == 0:
            message = "No notifications waiting"
        elif count == 1:
            message = "1 notification waiting"
        else:
            message = f"{count} notifications waiting"

        return {
            "success": True,
            "tool": "dexai_suppressed_count",
            "count": count,
            "priorities": priorities,
            "message": message,
        }

    except ImportError as e:
        return {
            "success": False,
            "tool": "dexai_suppressed_count",
            "error": f"Notify module not available: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_suppressed_count",
            "error": str(e),
        }


# =============================================================================
# Tool: dexai_release_suppressed
# =============================================================================


def dexai_release_suppressed(
    user_id: str,
    send_immediately: bool = True,
) -> dict[str, Any]:
    """
    Release suppressed notifications after flow state ends.

    Args:
        user_id: User identifier
        send_immediately: Send notifications now (default True)

    Returns:
        Dict with release count
    """
    try:
        from tools.automation import notify

        result = notify.release_suppressed(user_id, send_immediately=send_immediately)

        return {
            "success": result.get("success", False),
            "tool": "dexai_release_suppressed",
            "released": result.get("released", 0),
            "sent": result.get("sent", 0),
            "message": result.get("message", "Notifications released"),
        }

    except ImportError as e:
        return {
            "success": False,
            "tool": "dexai_release_suppressed",
            "error": f"Notify module not available: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_release_suppressed",
            "error": str(e),
        }


# =============================================================================
# Tool Registry
# =============================================================================


AUTOMATION_TOOLS = {
    "dexai_schedule": {
        "function": dexai_schedule,
        "description": "Create a scheduled job (cron, heartbeat, or trigger)",
        "parameters": {
            "name": {"type": "string", "required": True},
            "task": {"type": "string", "required": True},
            "schedule": {"type": "string", "required": True},
            "job_type": {"type": "string", "required": False, "default": "cron"},
        },
    },
    "dexai_schedule_list": {
        "function": dexai_schedule_list,
        "description": "List scheduled jobs",
        "parameters": {
            "job_type": {"type": "string", "required": False},
            "enabled": {"type": "boolean", "required": False},
        },
    },
    "dexai_schedule_manage": {
        "function": dexai_schedule_manage,
        "description": "Manage a scheduled job (enable, disable, delete, run now)",
        "parameters": {
            "job_id": {"type": "string", "required": True},
            "action": {"type": "string", "required": True},
        },
    },
    "dexai_notify": {
        "function": dexai_notify,
        "description": "Send a notification to a user (flow-aware by default)",
        "parameters": {
            "user_id": {"type": "string", "required": True},
            "content": {"type": "string", "required": True},
            "priority": {"type": "string", "required": False, "default": "normal"},
            "flow_aware": {"type": "boolean", "required": False, "default": True},
        },
    },
    "dexai_reminder": {
        "function": dexai_reminder,
        "description": "Set a reminder for a user at a specified time",
        "parameters": {
            "user_id": {"type": "string", "required": True},
            "content": {"type": "string", "required": True},
            "when": {"type": "string", "required": True},
            "priority": {"type": "string", "required": False, "default": "normal"},
        },
    },
    "dexai_suppressed_count": {
        "function": dexai_suppressed_count,
        "description": "Get count of notifications suppressed during flow state",
        "parameters": {
            "user_id": {"type": "string", "required": True},
        },
    },
    "dexai_release_suppressed": {
        "function": dexai_release_suppressed,
        "description": "Release suppressed notifications after flow state ends",
        "parameters": {
            "user_id": {"type": "string", "required": True},
            "send_immediately": {"type": "boolean", "required": False, "default": True},
        },
    },
}


def get_tool(tool_name: str):
    """Get a tool function by name."""
    tool_info = AUTOMATION_TOOLS.get(tool_name)
    if tool_info:
        return tool_info["function"]
    return None


def list_tools() -> list[str]:
    """List all available automation tools."""
    return list(AUTOMATION_TOOLS.keys())


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    """CLI interface for testing automation tools."""
    import argparse

    parser = argparse.ArgumentParser(description="DexAI Automation MCP Tools")
    parser.add_argument("--tool", required=True, help="Tool to invoke")
    parser.add_argument("--args", help="JSON arguments")
    parser.add_argument("--list", action="store_true", help="List available tools")

    args = parser.parse_args()

    if args.list:
        print("Available automation tools:")
        for name, info in AUTOMATION_TOOLS.items():
            print(f"  {name}: {info['description']}")
        return

    tool_func = get_tool(args.tool)
    if not tool_func:
        print(f"Unknown tool: {args.tool}")
        print(f"Available: {list_tools()}")
        sys.exit(1)

    # Parse arguments
    tool_args = {}
    if args.args:
        tool_args = json.loads(args.args)

    # Invoke tool
    result = tool_func(**tool_args)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
