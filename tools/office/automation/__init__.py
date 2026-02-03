"""Office Automation — Level 5 Autonomous Integration Components

This module provides the automation components for Autonomous (Level 5)
office integration, including email processing, calendar protection,
auto-responses, emergency controls, and VIP contact management.

Philosophy:
    Autonomous actions need safety valves. Users must be able to instantly
    stop all automation when overwhelmed or when things go wrong. VIP contacts
    ensure critical communications always reach the user regardless of policies.

Components:
    emergency.py: Emergency pause/resume system
        - emergency_pause(): Instantly stop all automation
        - resume_automation(): Resume after pause
        - get_pause_status(): Check current pause state
        - schedule_pause(): Pre-schedule pause periods
        - check_pause_status(): Quick synchronous check
        - auto_pause_on_failures(): Auto-pause after repeated failures

    contact_manager.py: VIP contact management
        - add_vip(): Add a VIP contact
        - remove_vip(): Remove a VIP contact
        - list_vips(): List all VIP contacts
        - is_vip(): Check if email is a VIP
        - get_vip_settings(): Get VIP settings for an email
        - suggest_vips(): Suggest VIPs based on email history

    inbox_processor.py: Automated email processing
        - process_email(): Process single email against policies
        - process_inbox_batch(): Process batch of emails
        - start_inbox_watcher(): Start background inbox watcher
        - stop_inbox_watcher(): Stop background inbox watcher

    calendar_guardian.py: Calendar protection and meeting management
        - process_meeting_request(): Auto-accept/decline based on policies
        - protect_focus_blocks(): Check for focus block conflicts
        - suggest_meeting_alternatives(): Find alternative times
        - auto_respond_to_meeting(): Send meeting response

    auto_responder.py: Template-based auto-responses
        - send_auto_reply(): Send templated auto-reply
        - create_template(): Create response template
        - get_template(): Get template by ID
        - list_templates(): List all templates
        - render_template(): Preview rendered template

Emergency Triggers:
    - Dashboard "Emergency Stop" button (big, red, always visible)
    - Channel command: !pause or !stop dex
    - Keyboard shortcut: Ctrl+Shift+P
    - API endpoint for integrations

VIP Priority Levels:
    - critical: Always interrupt, even in Do Not Disturb
    - high: Bypass flow state, immediate notify
    - normal: Just starred/labeled specially
"""

import sys
from pathlib import Path

# Add project root to path for imports
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from tools.office import DB_PATH, PROJECT_ROOT, get_connection

# Re-export for convenience
__all__ = [
    "PROJECT_ROOT",
    "DB_PATH",
    "get_connection",
    # Emergency functions
    "emergency_pause",
    "resume_automation",
    "get_pause_status",
    "schedule_pause",
    "check_pause_status",
    "auto_pause_on_failures",
    "get_scheduled_pauses",
    "cancel_scheduled_pause",
    # VIP contact functions
    "add_vip",
    "remove_vip",
    "list_vips",
    "is_vip",
    "get_vip_settings",
    "suggest_vips",
    "update_vip",
    "record_interaction",
    # Inbox processor functions
    "process_email",
    "process_inbox_batch",
    "start_inbox_watcher",
    "stop_inbox_watcher",
    # Calendar guardian functions
    "process_meeting_request",
    "protect_focus_blocks",
    "suggest_meeting_alternatives",
    "auto_respond_to_meeting",
    # Auto responder functions
    "send_auto_reply",
    "create_template",
    "get_template",
    "list_templates",
    "update_template",
    "delete_template",
    "render_template",
]


# Lazy imports to avoid circular dependencies
def __getattr__(name: str):
    """Lazy load functions from submodules."""
    if name in (
        "emergency_pause",
        "resume_automation",
        "get_pause_status",
        "schedule_pause",
        "check_pause_status",
        "auto_pause_on_failures",
        "get_scheduled_pauses",
        "cancel_scheduled_pause",
    ):
        from tools.office.automation import emergency
        return getattr(emergency, name)

    if name in (
        "add_vip",
        "remove_vip",
        "list_vips",
        "is_vip",
        "get_vip_settings",
        "suggest_vips",
        "update_vip",
        "record_interaction",
    ):
        from tools.office.automation import contact_manager
        return getattr(contact_manager, name)

    if name in (
        "process_email",
        "process_inbox_batch",
        "start_inbox_watcher",
        "stop_inbox_watcher",
    ):
        from tools.office.automation import inbox_processor
        return getattr(inbox_processor, name)

    if name in (
        "process_meeting_request",
        "protect_focus_blocks",
        "suggest_meeting_alternatives",
        "auto_respond_to_meeting",
    ):
        from tools.office.automation import calendar_guardian
        return getattr(calendar_guardian, name)

    if name in (
        "send_auto_reply",
        "create_template",
        "get_template",
        "list_templates",
        "update_template",
        "delete_template",
        "render_template",
    ):
        from tools.office.automation import auto_responder
        return getattr(auto_responder, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
