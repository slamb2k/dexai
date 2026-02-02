"""
Automation Tools - Proactive agent capabilities

This package provides components for transforming the agent from reactive
to proactive, enabling it to:
- Run periodic background checks (heartbeat)
- Execute scheduled tasks (cron)
- React to file changes and webhooks (triggers)
- Send notifications without being prompted (dispatch)

Components:
    scheduler.py: Cron job scheduling and execution tracking
    heartbeat.py: Periodic background awareness checks
    notify.py: Notification dispatch to users via channels
    triggers.py: File/webhook event triggers
    runner.py: Background daemon orchestrating all components

Usage:
    # Start automation daemon
    python tools/automation/runner.py --start

    # Create a scheduled job
    from tools.automation import scheduler
    scheduler.create_job("morning_briefing", "cron", "Generate briefing", schedule="0 7 * * *")

    # Queue a notification
    from tools.automation import notify
    notify.queue_notification("alice", "Your task completed", priority="normal")

Dependencies:
    - croniter>=2.0.0 (cron expression parsing)
    - watchdog>=4.0.0 (file system watching)
    - pyyaml (configuration)
"""

from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'scheduler.db'
CONFIG_PATH = PROJECT_ROOT / 'args' / 'automation.yaml'
HEARTBEAT_FILE = PROJECT_ROOT / 'HEARTBEAT.md'

__all__ = [
    'PROJECT_ROOT',
    'DB_PATH',
    'CONFIG_PATH',
    'HEARTBEAT_FILE',
]
