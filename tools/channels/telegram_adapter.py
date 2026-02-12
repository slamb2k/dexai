"""
Tool: Telegram Channel Adapter
Purpose: Telegram bot integration for DexAI

Connects to Telegram using python-telegram-bot library in polling mode.
Handles commands (/start, /pair, /help) and various message types.

Usage:
    python tools/channels/telegram.py --start
    python tools/channels/telegram.py --status
    python tools/channels/telegram.py --test

Dependencies (pip):
    - python-telegram-bot>=20.0

Secrets (via vault, namespace: channels):
    - TELEGRAM_BOT_TOKEN
"""

import argparse
import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.channels.models import Attachment, UnifiedMessage
from tools.channels.router import ChannelAdapter, get_router


class TelegramAdapter(ChannelAdapter):
    """
    Telegram bot adapter using polling mode.

    Handles:
    - /start - Welcome message
    - /pair - Generate pairing code
    - /help - Show available commands
    - Text messages - Route through gateway
    - Voice notes - Receive with Whisper transcription (Phase 15b)
    - Photos - Receive with Vision analysis
    - Documents - Receive with text extraction
    - Videos - Receive with frame extraction and audio transcription (Phase 15b)
    """

    @property
    def name(self) -> str:
        return "telegram"

    def __init__(self, token: str):
        """
        Initialize Telegram adapter.

        Args:
            token: Telegram bot token from BotFather
        """
        self.token = token
        self.application = None
        self.bot = None
        self.router = None
        self._connected = False

    def set_router(self, router) -> None:
        """Set reference to the parent router."""
        self.router = router

    async def connect(self) -> None:
        """Initialize bot and start polling."""
        try:
            from telegram import Bot, Update
            from telegram.ext import (
                Application,
                ApplicationBuilder,
                CommandHandler,
                ContextTypes,
                MessageHandler,
                filters,
            )
        except ImportError:
            raise ImportError(
                "python-telegram-bot required. Install with: pip install python-telegram-bot"
            )

        self.application = ApplicationBuilder().token(self.token).build()
        self.bot = self.application.bot

        # Register command handlers (order matters - specific first)
        self.application.add_handler(CommandHandler("start", self._handle_start))
        self.application.add_handler(CommandHandler("pair", self._handle_pair))
        self.application.add_handler(CommandHandler("help", self._handle_help))
        self.application.add_handler(CommandHandler("status", self._handle_status))

        # Register message handlers
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text)
        )
        self.application.add_handler(MessageHandler(filters.VOICE, self._handle_voice))
        self.application.add_handler(MessageHandler(filters.PHOTO, self._handle_photo))
        self.application.add_handler(MessageHandler(filters.Document.ALL, self._handle_document))

        # Error handler
        self.application.add_error_handler(self._handle_error)

        # Initialize and start
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(allowed_updates=["message", "edited_message"])

        self._connected = True

        # Log startup
        try:
            from tools.security import audit

            audit.log_event(
                event_type="system",
                action="telegram_connected",
                channel="telegram",
                status="success",
            )
        except Exception:
            pass

    async def health_check(self) -> dict[str, Any]:
        """
        Check Telegram bot connection health.

        Returns:
            Dict with connected status, latency_ms, and optional error
        """
        import time

        if not self._connected or not self.bot:
            return {"connected": False, "error": "Not connected"}

        try:
            start = time.time()
            # Use asyncio.wait_for to prevent hanging
            me = await asyncio.wait_for(self.bot.get_me(), timeout=2.0)
            latency = int((time.time() - start) * 1000)

            return {
                "connected": True,
                "latency_ms": latency,
                "bot_username": me.username,
                "bot_id": me.id,
            }
        except asyncio.TimeoutError:
            return {"connected": False, "error": "Health check timed out"}
        except Exception as e:
            return {"connected": False, "error": str(e)[:100]}

    async def disconnect(self) -> None:
        """Stop polling and shutdown."""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

        self._connected = False

        # Log shutdown
        try:
            from tools.security import audit

            audit.log_event(
                event_type="system",
                action="telegram_disconnected",
                channel="telegram",
                status="success",
            )
        except Exception:
            pass

    async def send_message(self, message: UnifiedMessage) -> dict[str, Any]:
        """
        Send message to Telegram chat.

        Args:
            message: UnifiedMessage to send

        Returns:
            Dict with success status and message ID
        """
        chat_id = message.metadata.get("telegram_chat_id")
        if not chat_id:
            # Try to get chat_id from channel_user_id
            chat_id = message.channel_user_id

        if not chat_id:
            return {"success": False, "error": "no_chat_id"}

        reply_to = None
        if message.reply_to:
            try:
                reply_to = int(message.reply_to)
            except (ValueError, TypeError):
                pass

        try:
            result = await self.bot.send_message(
                chat_id=chat_id, text=message.content, reply_to_message_id=reply_to
            )

            return {
                "success": True,
                "message_id": str(result.message_id),
                "chat_id": str(result.chat.id),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def send_image(
        self,
        chat_id: str | int,
        image: bytes | str,
        caption: str | None = None,
        reply_to: int | None = None,
    ) -> dict[str, Any]:
        """
        Send an image to a Telegram chat.

        Args:
            chat_id: Telegram chat ID to send to
            image: Image bytes or URL
            caption: Optional caption for the image
            reply_to: Optional message ID to reply to

        Returns:
            Dict with success status and message ID
        """
        if not self.bot:
            return {"success": False, "error": "bot_not_connected"}

        try:
            if isinstance(image, str) and image.startswith("http"):
                # URL - send directly
                result = await self.bot.send_photo(
                    chat_id=chat_id,
                    photo=image,
                    caption=caption,
                    reply_to_message_id=reply_to,
                )
            else:
                # Bytes - send as file
                import io
                photo_file = io.BytesIO(image)
                photo_file.name = "image.png"
                result = await self.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_file,
                    caption=caption,
                    reply_to_message_id=reply_to,
                )

            return {
                "success": True,
                "message_id": str(result.message_id),
                "chat_id": str(result.chat.id),
            }
        except Exception as e:
            logger.error(f"Failed to send image: {e}")
            return {"success": False, "error": str(e)}

    async def send_voice(
        self,
        chat_id: str | int,
        audio: bytes,
        caption: str | None = None,
        reply_to: int | None = None,
        duration: int | None = None,
    ) -> dict[str, Any]:
        """
        Send a voice note to a Telegram chat (Phase 15b).

        Args:
            chat_id: Telegram chat ID to send to
            audio: Audio bytes (should be OGG/Opus format)
            caption: Optional caption for the voice note
            reply_to: Optional message ID to reply to
            duration: Optional duration in seconds

        Returns:
            Dict with success status and message ID
        """
        if not self.bot:
            return {"success": False, "error": "bot_not_connected"}

        try:
            import io
            voice_file = io.BytesIO(audio)
            voice_file.name = "voice.ogg"

            result = await self.bot.send_voice(
                chat_id=chat_id,
                voice=voice_file,
                caption=caption,
                reply_to_message_id=reply_to,
                duration=duration,
            )

            return {
                "success": True,
                "message_id": str(result.message_id),
                "chat_id": str(result.chat.id),
            }
        except Exception as e:
            logger.error(f"Failed to send voice: {e}")
            return {"success": False, "error": str(e)}

    def to_unified(self, update) -> UnifiedMessage:
        """
        Convert Telegram Update to UnifiedMessage.

        Args:
            update: Telegram Update object

        Returns:
            UnifiedMessage normalized from Telegram
        """
        message = update.message or update.edited_message

        content_type = "text"
        attachments = []
        content = message.text or message.caption or ""

        # Handle voice notes
        if message.voice:
            content_type = "voice"
            attachments.append(
                Attachment(
                    id=message.voice.file_id,
                    type="audio",
                    filename="voice.ogg",
                    mime_type="audio/ogg",
                    size_bytes=message.voice.file_size or 0,
                    url=None,
                )
            )

        # Handle photos
        elif message.photo:
            content_type = "image"
            photo = message.photo[-1]  # Get largest size
            attachments.append(
                Attachment(
                    id=photo.file_id,
                    type="image",
                    filename="photo.jpg",
                    mime_type="image/jpeg",
                    size_bytes=photo.file_size or 0,
                )
            )

        # Handle documents
        elif message.document:
            content_type = "document"
            attachments.append(
                Attachment(
                    id=message.document.file_id,
                    type="document",
                    filename=message.document.file_name or "document",
                    mime_type=message.document.mime_type or "application/octet-stream",
                    size_bytes=message.document.file_size or 0,
                )
            )

        # Handle video
        elif message.video:
            content_type = "video"
            attachments.append(
                Attachment(
                    id=message.video.file_id,
                    type="video",
                    filename="video.mp4",
                    mime_type="video/mp4",
                    size_bytes=message.video.file_size or 0,
                )
            )

        return UnifiedMessage(
            id=str(uuid.uuid4()),
            channel="telegram",
            channel_message_id=str(message.message_id),
            user_id=None,  # Resolved by router
            channel_user_id=str(message.from_user.id),
            direction="inbound",
            content=content,
            content_type=content_type,
            attachments=attachments,
            reply_to=str(message.reply_to_message.message_id) if message.reply_to_message else None,
            timestamp=message.date,
            metadata={
                "telegram_chat_id": message.chat.id,
                "telegram_chat_type": message.chat.type,
                "display_name": message.from_user.first_name or "",
                "username": message.from_user.username,
            },
        )

    def from_unified(self, message: UnifiedMessage) -> dict[str, Any]:
        """
        Convert UnifiedMessage to Telegram send parameters.

        Args:
            message: UnifiedMessage to convert

        Returns:
            Dict with Telegram API parameters
        """
        return {
            "chat_id": message.metadata.get("telegram_chat_id") or message.channel_user_id,
            "text": message.content,
            "reply_to_message_id": int(message.reply_to) if message.reply_to else None,
        }

    async def download_attachment(self, attachment: Attachment) -> bytes:
        """
        Download attachment content from Telegram.

        Uses file_id stored in attachment.id to download via Telegram Bot API.

        Args:
            attachment: Attachment with Telegram file_id

        Returns:
            File content as bytes

        Raises:
            ValueError: If no file_id available
            Exception: On download failure
        """
        if not self.bot:
            raise RuntimeError("Bot not connected")

        file_id = attachment.id
        if not file_id:
            raise ValueError("No file_id in Telegram attachment")

        # Get file info from Telegram
        file_info = await self.bot.get_file(file_id)

        # Download the file
        file_bytes = await file_info.download_as_bytearray()

        return bytes(file_bytes)

    # =========================================================================
    # Command Handlers
    # =========================================================================

    async def _handle_start(self, update, context) -> None:
        """Welcome new users."""
        await update.message.reply_text(
            "Welcome to DexAI!\n\n"
            "I'm your AI assistant for adulting tasks.\n\n"
            "Commands:\n"
            "/pair - Link your account\n"
            "/help - Show available commands\n"
            "/status - Check connection status\n\n"
            "Just send me a message to get started!"
        )

        # Log new user
        try:
            from tools.security import audit

            audit.log_event(
                event_type="command",
                action="telegram_start",
                channel="telegram",
                status="success",
                details={
                    "user_id": update.message.from_user.id,
                    "username": update.message.from_user.username,
                },
            )
        except Exception:
            pass

    async def _handle_pair(self, update, context) -> None:
        """Handle /pair command (deprecated in single-tenant mode)."""
        await update.message.reply_text(
            "Account pairing is no longer needed.\n\n"
            "Your Telegram user ID is automatically recognized. "
            "If you're not getting responses, ask the owner to add your "
            "Telegram user ID to the allowed users list."
        )

    async def _handle_help(self, update, context) -> None:
        """Show available commands."""
        await update.message.reply_text(
            "Available Commands:\n\n"
            "/start - Welcome message\n"
            "/pair - Link your account across devices\n"
            "/help - Show this help message\n"
            "/status - Check connection status\n\n"
            "Messaging:\n"
            "- Send text messages to chat\n"
            "- Send voice notes (transcription coming soon)\n"
            "- Send photos for context\n"
            "- Send documents to share files"
        )

    async def _handle_status(self, update, context) -> None:
        """Check connection status."""
        channel_user_id = str(update.message.from_user.id)

        await update.message.reply_text(
            f"Connection Status: Connected\n"
            f"Your Telegram ID: {channel_user_id}\n"
            f"Platform: Telegram"
        )

    # =========================================================================
    # Message Handlers
    # =========================================================================

    async def _handle_text(self, update, context) -> None:
        """Route text messages through gateway."""
        if not self.router:
            await update.message.reply_text("System not ready. Please try again later.")
            return

        message = self.to_unified(update)
        result = await self.router.route_inbound(message)

        if not result.get("success"):
            reason = result.get("reason", "unknown")

            if reason == "user_not_paired":
                await update.message.reply_text("Please use /pair first to link your account.")
            elif reason == "rate_limited":
                await update.message.reply_text(
                    "You're sending messages too quickly. Please wait a moment."
                )
            elif reason == "content_blocked":
                await update.message.reply_text("Your message could not be processed.")
            elif reason == "permission_denied":
                await update.message.reply_text("You don't have permission to send messages.")
            # For other errors, fail silently

    async def _handle_voice(self, update, context) -> None:
        """Handle voice notes with transcription (Phase 15b)."""
        if self.router:
            message = self.to_unified(update)
            result = await self.router.route_inbound(message)

            if not result.get("success"):
                reason = result.get("reason", "unknown")
                if reason == "user_not_paired":
                    await update.message.reply_text("Please use /pair first to link your account.")
                elif reason == "transcription_failed":
                    await update.message.reply_text(
                        "I received your voice note but couldn't transcribe it. "
                        "Try again or send a text message."
                    )

    async def _handle_photo(self, update, context) -> None:
        """Handle photos."""
        if self.router:
            message = self.to_unified(update)
            result = await self.router.route_inbound(message)

            if not result.get("success"):
                reason = result.get("reason", "unknown")
                if reason == "user_not_paired":
                    await update.message.reply_text("Please use /pair first to link your account.")

    async def _handle_document(self, update, context) -> None:
        """Handle documents."""
        if self.router:
            message = self.to_unified(update)
            result = await self.router.route_inbound(message)

            if not result.get("success"):
                reason = result.get("reason", "unknown")
                if reason == "user_not_paired":
                    await update.message.reply_text("Please use /pair first to link your account.")

    async def _handle_error(self, update, context) -> None:
        """Log errors."""
        try:
            from tools.security import audit

            audit.log_event(
                event_type="error",
                action="telegram_error",
                channel="telegram",
                details={"error": str(context.error)},
            )
        except Exception:
            pass


# =============================================================================
# Token Management
# =============================================================================


def get_telegram_token() -> str | None:
    """
    Get Telegram bot token from vault.

    Returns:
        Token string or None if not found
    """
    try:
        from tools.security import vault

        result = vault.get_secret("TELEGRAM_BOT_TOKEN", namespace="channels")
        if result.get("success"):
            return result.get("value")
    except Exception:
        pass

    # Fallback to environment variable
    import os

    return os.environ.get("TELEGRAM_BOT_TOKEN")


def set_telegram_token(token: str) -> dict[str, Any]:
    """
    Store Telegram bot token in vault.

    Args:
        token: Telegram bot token

    Returns:
        Result dict
    """
    try:
        from tools.security import vault

        return vault.set_secret("TELEGRAM_BOT_TOKEN", token, namespace="channels")
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# CLI Interface
# =============================================================================


async def run_adapter() -> None:
    """Run the Telegram adapter."""
    token = get_telegram_token()
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not found in vault or environment")
        print("Set with: python tools/channels/telegram.py --set-token YOUR_TOKEN")
        sys.exit(1)

    adapter = TelegramAdapter(token)
    router = get_router()
    router.register_adapter(adapter)

    # Register SDK handler for full Claude Agent SDK capabilities
    # Uses streaming handler which routes to channel-specific implementations
    from tools.channels.sdk_handler import sdk_handler_with_streaming
    router.add_message_handler(sdk_handler_with_streaming)

    print("Starting Telegram adapter with DexAI SDK streaming handler...")
    await adapter.connect()

    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await adapter.disconnect()


def main():
    parser = argparse.ArgumentParser(description="Telegram Channel Adapter")
    parser.add_argument("--start", action="store_true", help="Start the adapter")
    parser.add_argument("--status", action="store_true", help="Check adapter status")
    parser.add_argument("--set-token", metavar="TOKEN", help="Set bot token in vault")
    parser.add_argument("--test", action="store_true", help="Test token validity")

    args = parser.parse_args()

    if args.set_token:
        result = set_telegram_token(args.set_token)
        if result.get("success"):
            print("OK: Token stored in vault")
        else:
            print(f"ERROR: {result.get('error')}")
        sys.exit(0 if result.get("success") else 1)

    elif args.status:
        token = get_telegram_token()
        status = {
            "token_configured": bool(token),
            "token_preview": f"{token[:10]}..." if token else None,
        }
        print("OK" if token else "NOT CONFIGURED")
        print(json.dumps(status, indent=2))

    elif args.test:
        token = get_telegram_token()
        if not token:
            print("ERROR: No token configured")
            sys.exit(1)

        try:
            async def test_token():
                try:
                    from telegram import Bot

                    bot = Bot(token)
                    me = await bot.get_me()
                    return {
                        "success": True,
                        "bot_id": me.id,
                        "bot_username": me.username,
                        "bot_name": me.first_name,
                    }
                except Exception as e:
                    return {"success": False, "error": str(e)}

            result = asyncio.run(test_token())
            print("OK" if result.get("success") else "ERROR")
            print(json.dumps(result, indent=2))

        except ImportError:
            print("ERROR: python-telegram-bot not installed")
            sys.exit(1)

    elif args.start:
        try:
            asyncio.run(run_adapter())
        except KeyboardInterrupt:
            print("\nStopped")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
