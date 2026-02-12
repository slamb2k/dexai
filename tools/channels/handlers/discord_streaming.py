from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from tools.channels.models import UnifiedMessage
from tools.channels.session_manager import get_session_manager

logger = logging.getLogger(__name__)

STREAM_UPDATE_INTERVAL_MS = 500
TYPING_CURSOR = "\u258c"


async def sdk_handler_discord_streaming(
    message: UnifiedMessage,
    context: dict,
) -> dict[str, Any]:
    try:
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
    except ImportError:
        return {"success": False, "error": "SDK not installed"}

    from tools.channels.router import get_router
    router = get_router()
    adapter = router.adapters.get("discord")

    if not adapter:
        return {"success": False, "error": "Discord adapter not available"}

    initial_message = UnifiedMessage(
        id=str(uuid.uuid4()),
        channel="discord",
        channel_message_id=None,
        user_id=message.user_id,
        channel_user_id=message.channel_user_id,
        direction="outbound",
        content=f"Thinking...{TYPING_CURSOR}",
        content_type="text",
        attachments=[],
        reply_to=message.id,
        timestamp=datetime.now(),
        metadata=message.metadata,
    )

    send_result = await adapter.send_message(initial_message)

    if not send_result.get("success"):
        from tools.channels.sdk_handler import sdk_handler
        return await sdk_handler(message, context)

    message_obj = send_result.get("message_obj")

    if not message_obj:
        from tools.channels.sdk_handler import sdk_handler
        return await sdk_handler(message, context)

    manager = get_session_manager()

    from tools.channels.sdk_handler import create_ask_user_handler, _log_to_dashboard
    ask_handler = create_ask_user_handler(message)

    accumulated_text = ""
    last_update_time = asyncio.get_event_loop().time()

    try:
        async for msg in manager.stream_message(
            channel=message.channel,
            content=message.content,
            ask_user_handler=ask_handler,
        ):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        accumulated_text += block.text

                        current_time = asyncio.get_event_loop().time()
                        if (current_time - last_update_time) * 1000 >= STREAM_UPDATE_INTERVAL_MS:
                            display_text = accumulated_text[:1997] + TYPING_CURSOR
                            await adapter.update_message(
                                message_obj=message_obj,
                                content=display_text,
                            )
                            last_update_time = current_time

            elif isinstance(msg, ResultMessage):
                break

        if accumulated_text:
            final_text = accumulated_text[:2000]
            await adapter.update_message(
                message_obj=message_obj,
                content=final_text,
            )
        else:
            await adapter.update_message(
                message_obj=message_obj,
                content="I completed the task but have no text response.",
            )

        _log_to_dashboard(
            event_type="task",
            summary=f"Discord streaming response ({len(accumulated_text)} chars)",
            channel="discord",
            user_id=message.user_id,
            details={
                "message_id": message.id,
                "response_length": len(accumulated_text),
                "streaming": True,
                "truncated": len(accumulated_text) > 2000,
            },
            severity="info",
        )

        return {
            "success": True,
            "handler": "sdk_handler_discord_streaming",
            "response_length": len(accumulated_text),
            "streaming": True,
            "truncated": len(accumulated_text) > 2000,
        }

    except Exception as e:
        logger.error(f"Discord streaming error: {e}")
        try:
            error_msg = accumulated_text[:2000] if accumulated_text else f"Error: {str(e)[:100]}"
            await adapter.update_message(
                message_obj=message_obj,
                content=error_msg,
            )
        except Exception:
            pass

        return {"success": False, "error": str(e)}
