"""Route parsed voice commands to appropriate handlers.

The router dispatches ParsedCommands to handler functions and logs
all command activity to the voice_commands table.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Callable, Awaitable

from tools.voice import get_connection
from tools.voice.models import (
    CommandResult,
    IntentType,
    ParsedCommand,
)

logger = logging.getLogger(__name__)

# Handler type: async function(parsed_command, user_id) -> CommandResult
HandlerFn = Callable[[ParsedCommand, str], Awaitable[CommandResult]]


class CommandRouter:
    """Routes parsed voice commands to registered handlers."""

    def __init__(self):
        self._handlers: dict[IntentType, HandlerFn] = {}

    def register(self, intent: IntentType, handler: HandlerFn) -> None:
        """Register a handler for an intent type."""
        self._handlers[intent] = handler

    async def route_command(
        self,
        command: ParsedCommand,
        user_id: str,
    ) -> CommandResult:
        """Route a parsed command to the appropriate handler.

        Logs the command and its result to the database.
        """
        start = time.monotonic()
        command_id = str(uuid.uuid4())

        # Handle cancel immediately
        if command.intent == IntentType.CANCEL:
            result = CommandResult(
                success=True,
                message="Cancelled.",
                intent=IntentType.CANCEL,
            )
            self._log_command(command_id, user_id, command, result, 0)
            return result

        # Handle help
        if command.intent == IntentType.HELP:
            from tools.voice.parser.intent_parser import AVAILABLE_COMMANDS
            result = CommandResult(
                success=True,
                message="Here's what you can say:",
                intent=IntentType.HELP,
                data={"commands": AVAILABLE_COMMANDS},
            )
            self._log_command(command_id, user_id, command, result, 0)
            return result

        # Handle unknown
        if command.intent == IntentType.UNKNOWN:
            result = CommandResult(
                success=False,
                message=command.suggestion or 'Say "help" to see available commands',
                intent=IntentType.UNKNOWN,
                error="unrecognized_command",
            )
            self._log_command(command_id, user_id, command, result, 0)
            return result

        # Find handler
        handler = self._handlers.get(command.intent)
        if not handler:
            result = CommandResult(
                success=False,
                message=f"No handler for {command.intent.value}. This feature is coming soon!",
                intent=command.intent,
                error="no_handler",
            )
            self._log_command(command_id, user_id, command, result, 0)
            return result

        # Execute handler
        try:
            result = await handler(command, user_id)
            result.intent = command.intent
        except Exception as e:
            logger.exception(f"Voice command handler failed: {e}")
            result = CommandResult(
                success=False,
                message="Something went wrong. Try again?",
                intent=command.intent,
                error=str(e),
            )

        elapsed_ms = int((time.monotonic() - start) * 1000)
        self._log_command(command_id, user_id, command, result, elapsed_ms)
        return result

    def _log_command(
        self,
        command_id: str,
        user_id: str,
        command: ParsedCommand,
        result: CommandResult,
        execution_time_ms: int,
    ) -> None:
        """Log a voice command to the database."""
        try:
            conn = get_connection()
            conn.execute(
                """INSERT INTO voice_commands
                   (id, user_id, transcript, confidence, intent, entities,
                    parsed_successfully, handler, result, executed_successfully,
                    error_message, execution_time_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    command_id,
                    user_id,
                    command.raw_transcript,
                    command.confidence,
                    command.intent.value,
                    json.dumps([e.to_dict() for e in command.entities]),
                    command.intent != IntentType.UNKNOWN,
                    command.intent.value,
                    json.dumps(result.to_dict()),
                    result.success,
                    result.error,
                    execution_time_ms,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to log voice command: {e}")


def create_default_router() -> CommandRouter:
    """Create a router with all default handlers registered."""
    from tools.voice.commands.task_commands import (
        handle_add_task,
        handle_complete_task,
        handle_decompose_task,
        handle_skip_task,
    )
    from tools.voice.commands.reminder_commands import (
        handle_cancel_reminder,
        handle_set_reminder,
        handle_snooze_reminder,
    )
    from tools.voice.commands.query_commands import (
        handle_query_next_task,
        handle_query_schedule,
        handle_query_search,
        handle_query_status,
    )
    from tools.voice.commands.control_commands import (
        handle_end_focus,
        handle_pause_notifications,
        handle_start_focus,
    )

    router = CommandRouter()

    # Task commands
    router.register(IntentType.ADD_TASK, handle_add_task)
    router.register(IntentType.COMPLETE_TASK, handle_complete_task)
    router.register(IntentType.SKIP_TASK, handle_skip_task)
    router.register(IntentType.DECOMPOSE_TASK, handle_decompose_task)

    # Reminder commands
    router.register(IntentType.SET_REMINDER, handle_set_reminder)
    router.register(IntentType.SNOOZE_REMINDER, handle_snooze_reminder)
    router.register(IntentType.CANCEL_REMINDER, handle_cancel_reminder)

    # Query commands
    router.register(IntentType.QUERY_NEXT_TASK, handle_query_next_task)
    router.register(IntentType.QUERY_SCHEDULE, handle_query_schedule)
    router.register(IntentType.QUERY_STATUS, handle_query_status)
    router.register(IntentType.QUERY_SEARCH, handle_query_search)

    # Control commands
    router.register(IntentType.START_FOCUS, handle_start_focus)
    router.register(IntentType.END_FOCUS, handle_end_focus)
    router.register(IntentType.PAUSE_NOTIFICATIONS, handle_pause_notifications)

    return router
