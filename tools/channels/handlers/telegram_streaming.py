from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from tools.channels.models import UnifiedMessage

logger = logging.getLogger(__name__)


async def sdk_handler_telegram_fallback(
    message: UnifiedMessage,
    context: dict,
) -> dict[str, Any]:
    from tools.channels.router import get_router
    router = get_router()
    adapter = router.adapters.get("telegram")

    if not adapter:
        return {"success": False, "error": "Telegram adapter not available"}

    ack_message = UnifiedMessage(
        id=str(uuid.uuid4()),
        channel="telegram",
        channel_message_id=None,
        user_id=message.user_id,
        channel_user_id=message.channel_user_id,
        direction="outbound",
        content="Working on your request...",
        content_type="text",
        attachments=[],
        reply_to=message.channel_message_id,
        timestamp=datetime.now(),
        metadata=message.metadata,
    )

    await adapter.send_message(ack_message)

    from tools.channels.sdk_handler import sdk_handler
    return await sdk_handler(message, context)
