"""
Tool: Slack Channel Adapter
Purpose: Slack app integration for DexAI

Connects to Slack using slack-bolt SDK with Socket Mode.
Handles DMs, mentions, and slash commands (/ask, /pair).

Usage:
    python tools/channels/slack.py --start
    python tools/channels/slack.py --status
    python tools/channels/slack.py --test

Dependencies (pip):
    - slack-bolt>=1.18
    - slack-sdk>=3.0

Secrets (via vault, namespace: channels):
    - SLACK_BOT_TOKEN (xoxb-...)
    - SLACK_APP_TOKEN (xapp-...)
"""

import argparse
import asyncio
import json
import secrets
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.channels.models import Attachment, ChannelUser, UnifiedMessage
from tools.channels.router import ChannelAdapter, get_router


class SlackAdapter(ChannelAdapter):
    """
    Slack app adapter using Socket Mode.

    Handles:
    - DM messages - Route through gateway
    - @mentions - Route through gateway
    - /ask - Ask the AI a question
    - /pair - Generate pairing code
    - Thread replies - Stay in thread context
    """

    @property
    def name(self) -> str:
        return "slack"

    def __init__(self, bot_token: str, app_token: str):
        """
        Initialize Slack adapter.

        Args:
            bot_token: Slack bot token (xoxb-...)
            app_token: Slack app token (xapp-...)
        """
        self.bot_token = bot_token
        self.app_token = app_token
        self.app = None
        self.handler = None
        self.router = None
        self._connected = False

    def set_router(self, router) -> None:
        """Set reference to the parent router."""
        self.router = router

    async def connect(self) -> None:
        """Initialize app and start Socket Mode."""
        try:
            from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
            from slack_bolt.async_app import AsyncApp
        except ImportError:
            raise ImportError("slack-bolt required. Install with: pip install slack-bolt slack-sdk")

        self.app = AsyncApp(token=self.bot_token)

        # Register message handlers
        @self.app.message(".*")
        async def handle_message(message, say, client):
            await self._handle_message(message, say, client)

        # Register event handlers
        @self.app.event("app_mention")
        async def handle_mention(event, say, client):
            await self._handle_mention(event, say, client)

        @self.app.event("message")
        async def handle_dm(event, say, client):
            # Handle DMs (channel type is 'im')
            if event.get("channel_type") == "im":
                await self._handle_dm(event, say, client)

        # Register slash commands
        @self.app.command("/ask")
        async def ask_command(ack, command, respond):
            await ack()  # Must ack within 3 seconds
            await self._handle_ask(command, respond)

        @self.app.command("/pair")
        async def pair_command(ack, command, respond):
            await ack()
            await self._handle_pair(command, respond)

        @self.app.command("/ai-help")
        async def help_command(ack, command, respond):
            await ack()
            await self._handle_help(command, respond)

        @self.app.command("/ai-status")
        async def status_command(ack, command, respond):
            await ack()
            await self._handle_status(command, respond)

        # Error handler
        @self.app.error
        async def error_handler(error, body, logger):
            await self._handle_error(error, body)

        # Start Socket Mode
        self.handler = AsyncSocketModeHandler(self.app, self.app_token)
        await self.handler.start_async()

        self._connected = True

        # Log startup
        try:
            from tools.security import audit

            audit.log_event(
                event_type="system", action="slack_connected", channel="slack", status="success"
            )
        except Exception:
            pass

        print("Slack adapter connected")

    async def disconnect(self) -> None:
        """Disconnect from Slack."""
        if self.handler:
            await self.handler.close_async()

        self._connected = False

        # Log shutdown
        try:
            from tools.security import audit

            audit.log_event(
                event_type="system", action="slack_disconnected", channel="slack", status="success"
            )
        except Exception:
            pass

    async def send_message(self, message: UnifiedMessage) -> dict[str, Any]:
        """
        Send message to Slack.

        Args:
            message: UnifiedMessage to send

        Returns:
            Dict with success status and message ID
        """
        try:
            from slack_sdk.web.async_client import AsyncWebClient

            client = AsyncWebClient(token=self.bot_token)

            channel = message.metadata.get("slack_channel_id")
            thread_ts = message.metadata.get("slack_thread_ts")

            if not channel:
                # Try to DM the user
                channel = message.channel_user_id

            if not channel:
                return {"success": False, "error": "no_channel_id"}

            result = await client.chat_postMessage(
                channel=channel, text=message.content, thread_ts=thread_ts
            )

            return {"success": True, "message_id": result["ts"], "channel_id": result["channel"]}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def to_unified(self, event: dict[str, Any]) -> UnifiedMessage:
        """
        Convert Slack event to UnifiedMessage.

        Args:
            event: Slack event dict

        Returns:
            UnifiedMessage normalized from Slack
        """
        content_type = "text"
        attachments = []
        content = event.get("text", "")

        # Handle files
        files = event.get("files", [])
        for file in files:
            file_type = file.get("filetype", "unknown")

            if file_type in ["png", "jpg", "jpeg", "gif", "webp"]:
                att_type = "image"
                if content_type == "text":
                    content_type = "image"
            elif file_type in ["mp3", "wav", "ogg", "m4a"]:
                att_type = "audio"
            elif file_type in ["mp4", "mov", "webm"]:
                att_type = "video"
            else:
                att_type = "document"

            attachments.append(
                Attachment(
                    id=file.get("id", ""),
                    type=att_type,
                    filename=file.get("name", "file"),
                    mime_type=file.get("mimetype", "application/octet-stream"),
                    size_bytes=file.get("size", 0),
                    url=file.get("url_private"),
                )
            )

        # Clean content (remove bot mention)
        # Slack mentions look like <@U123ABC>
        import re

        content = re.sub(r"<@[A-Z0-9]+>", "", content).strip()

        return UnifiedMessage(
            id=str(uuid.uuid4()),
            channel="slack",
            channel_message_id=event.get("ts", ""),
            user_id=None,  # Resolved by router
            channel_user_id=event.get("user", ""),
            direction="inbound",
            content=content,
            content_type=content_type,
            attachments=attachments,
            reply_to=event.get("thread_ts"),
            timestamp=datetime.fromtimestamp(float(event.get("ts", 0))),
            metadata={
                "slack_channel_id": event.get("channel"),
                "slack_thread_ts": event.get("thread_ts"),
                "slack_channel_type": event.get("channel_type"),
                "display_name": event.get("user", "Unknown"),
                "username": event.get("user"),
            },
        )

    def from_unified(self, message: UnifiedMessage) -> dict[str, Any]:
        """
        Convert UnifiedMessage to Slack send parameters.

        Args:
            message: UnifiedMessage to convert

        Returns:
            Dict with Slack API parameters
        """
        return {
            "channel": message.metadata.get("slack_channel_id") or message.channel_user_id,
            "text": message.content,
            "thread_ts": message.metadata.get("slack_thread_ts"),
        }

    # =========================================================================
    # Message Handlers
    # =========================================================================

    async def _handle_message(self, message, say, client) -> None:
        """Handle regular messages."""
        # Skip bot messages
        if message.get("bot_id"):
            return

        if not self.router:
            await say("System not ready. Please try again later.")
            return

        unified = self.to_unified(message)
        result = await self.router.route_inbound(unified)

        if not result.get("success"):
            reason = result.get("reason", "unknown")
            thread_ts = message.get("thread_ts") or message.get("ts")

            if reason == "user_not_paired":
                await say("Please pair your account first using `/pair`", thread_ts=thread_ts)
            elif reason == "rate_limited":
                await say("You're sending messages too quickly. Please wait.", thread_ts=thread_ts)

    async def _handle_dm(self, event, say, client) -> None:
        """Handle DM messages."""
        # Skip bot messages
        if event.get("bot_id"):
            return

        if not self.router:
            await say("System not ready. Please try again later.")
            return

        unified = self.to_unified(event)
        result = await self.router.route_inbound(unified)

        if not result.get("success"):
            reason = result.get("reason", "unknown")

            if reason == "user_not_paired":
                await say("Please pair your account first using `/pair`")
            elif reason == "rate_limited":
                await say("You're sending messages too quickly. Please wait.")

    async def _handle_mention(self, event, say, client) -> None:
        """Handle @mentions."""
        if not self.router:
            await say("System not ready. Please try again later.")
            return

        unified = self.to_unified(event)
        result = await self.router.route_inbound(unified)

        # Reply in thread
        thread_ts = event.get("thread_ts") or event.get("ts")

        if not result.get("success"):
            reason = result.get("reason", "unknown")

            if reason == "user_not_paired":
                await say("Please pair your account first using `/pair`", thread_ts=thread_ts)
            elif reason == "rate_limited":
                await say("You're sending messages too quickly. Please wait.", thread_ts=thread_ts)

    # =========================================================================
    # Slash Command Handlers
    # =========================================================================

    async def _handle_ask(self, command, respond) -> None:
        """Handle /ask command."""
        if not self.router:
            await respond("System not ready. Please try again later.")
            return

        question = command.get("text", "")
        if not question:
            await respond("Please provide a question: `/ask your question here`")
            return

        # Create message from question
        unified = UnifiedMessage(
            id=str(uuid.uuid4()),
            channel="slack",
            channel_message_id=str(uuid.uuid4()),
            user_id=None,
            channel_user_id=command.get("user_id", ""),
            direction="inbound",
            content=question,
            content_type="text",
            metadata={
                "slack_channel_id": command.get("channel_id"),
                "display_name": command.get("user_name"),
                "username": command.get("user_name"),
                "is_slash_command": True,
            },
        )

        result = await self.router.route_inbound(unified)

        if not result.get("success"):
            reason = result.get("reason", "unknown")

            if reason == "user_not_paired":
                await respond("Please pair your account first using `/pair`")
            elif reason == "rate_limited":
                await respond("You're sending messages too quickly. Please wait.")
            else:
                await respond("Your question has been received.")
        else:
            await respond("Your question has been received and is being processed.")

    async def _handle_pair(self, command, respond) -> None:
        """Handle /pair command."""
        # Generate secure code
        code = secrets.token_urlsafe(8).upper()[:8]
        channel_user_id = command.get("user_id", "")

        try:
            from tools.channels import inbox

            # Get existing user or create new one
            user = inbox.get_user_by_channel("slack", channel_user_id)

            if not user:
                user = ChannelUser(
                    id=ChannelUser.generate_id(),
                    channel="slack",
                    channel_user_id=channel_user_id,
                    display_name=command.get("user_name", "Unknown"),
                    username=command.get("user_name"),
                )
                inbox.create_or_update_user(user)
            else:
                if isinstance(user, dict):
                    user = ChannelUser.from_dict(user)

            # Create pairing code (10 min TTL)
            result = inbox.create_pairing_code(
                user_id=user.id,
                channel="slack",
                channel_user_id=channel_user_id,
                code=code,
                ttl_seconds=600,
            )

            if result.get("success"):
                await respond(
                    {
                        "response_type": "ephemeral",
                        "blocks": [
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"Your pairing code:\n\n*`{code}`*\n\n"
                                    f"Enter this code in your main interface to link accounts.\n"
                                    f"Expires in 10 minutes.",
                                },
                            }
                        ],
                    }
                )
            else:
                await respond("Could not generate pairing code. Please try again.")

        except Exception:
            await respond("Error generating pairing code. Please try again.")

    async def _handle_help(self, command, respond) -> None:
        """Handle /ai-help command."""
        await respond(
            {
                "response_type": "ephemeral",
                "blocks": [
                    {"type": "header", "text": {"type": "plain_text", "text": "DexAI Help"}},
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Commands:*\n"
                            "`/ask` - Ask the AI a question\n"
                            "`/pair` - Link your account\n"
                            "`/ai-help` - Show this help\n"
                            "`/ai-status` - Check connection",
                        },
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Messaging:*\n"
                            "Send me a DM to chat privately\n"
                            "@mention me in a channel to ask questions\n"
                            "Attach files for context",
                        },
                    },
                ],
            }
        )

    async def _handle_status(self, command, respond) -> None:
        """Handle /ai-status command."""
        channel_user_id = command.get("user_id", "")

        try:
            from tools.channels import inbox

            user = inbox.get_user_by_channel("slack", channel_user_id)

            if user:
                is_paired = (
                    user.is_paired if hasattr(user, "is_paired") else user.get("is_paired", False)
                )
                status = "Paired and ready" if is_paired else "Not paired"
            else:
                status = "New user"

            await respond(
                {
                    "response_type": "ephemeral",
                    "text": f"*Connection Status:* Connected\n"
                    f"*Account Status:* {status}\n"
                    f"*Platform:* Slack\n\n"
                    f"Use `/pair` to link your account.",
                }
            )
        except Exception:
            await respond(
                {
                    "response_type": "ephemeral",
                    "text": "*Connection Status:* Connected\n*Platform:* Slack",
                }
            )

    async def _handle_error(self, error, body) -> None:
        """Handle errors."""
        try:
            from tools.security import audit

            audit.log_event(
                event_type="error",
                action="slack_error",
                channel="slack",
                details={"error": str(error)},
            )
        except Exception:
            pass


# =============================================================================
# Token Management
# =============================================================================


def get_slack_tokens() -> dict[str, str | None]:
    """
    Get Slack tokens from vault.

    Returns:
        Dict with bot_token and app_token
    """
    tokens = {"bot_token": None, "app_token": None}

    try:
        from tools.security import vault

        bot_result = vault.get_secret("SLACK_BOT_TOKEN", namespace="channels")
        if bot_result.get("success"):
            tokens["bot_token"] = bot_result.get("value")

        app_result = vault.get_secret("SLACK_APP_TOKEN", namespace="channels")
        if app_result.get("success"):
            tokens["app_token"] = app_result.get("value")

    except Exception:
        pass

    # Fallback to environment variables
    if not tokens["bot_token"]:
        import os

        tokens["bot_token"] = os.environ.get("SLACK_BOT_TOKEN")

    if not tokens["app_token"]:
        import os

        tokens["app_token"] = os.environ.get("SLACK_APP_TOKEN")

    return tokens


def set_slack_tokens(bot_token: str = None, app_token: str = None) -> dict[str, Any]:
    """
    Store Slack tokens in vault.

    Args:
        bot_token: Slack bot token (xoxb-...)
        app_token: Slack app token (xapp-...)

    Returns:
        Result dict
    """
    results = {}

    try:
        from tools.security import vault

        if bot_token:
            results["bot_token"] = vault.set_secret(
                "SLACK_BOT_TOKEN", bot_token, namespace="channels"
            )

        if app_token:
            results["app_token"] = vault.set_secret(
                "SLACK_APP_TOKEN", app_token, namespace="channels"
            )

        return {"success": True, "results": results}

    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# CLI Interface
# =============================================================================


async def run_adapter() -> None:
    """Run the Slack adapter."""
    tokens = get_slack_tokens()

    if not tokens["bot_token"]:
        print("ERROR: SLACK_BOT_TOKEN not found in vault or environment")
        print("Set with: python tools/channels/slack.py --set-bot-token YOUR_TOKEN")
        sys.exit(1)

    if not tokens["app_token"]:
        print("ERROR: SLACK_APP_TOKEN not found in vault or environment")
        print("Set with: python tools/channels/slack.py --set-app-token YOUR_TOKEN")
        sys.exit(1)

    adapter = SlackAdapter(tokens["bot_token"], tokens["app_token"])
    router = get_router()
    router.register_adapter(adapter)

    print("Starting Slack adapter...")
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
    parser = argparse.ArgumentParser(description="Slack Channel Adapter")
    parser.add_argument("--start", action="store_true", help="Start the adapter")
    parser.add_argument("--status", action="store_true", help="Check adapter status")
    parser.add_argument("--set-bot-token", metavar="TOKEN", help="Set bot token (xoxb-...)")
    parser.add_argument("--set-app-token", metavar="TOKEN", help="Set app token (xapp-...)")
    parser.add_argument("--test", action="store_true", help="Test token validity")

    args = parser.parse_args()

    if args.set_bot_token or args.set_app_token:
        result = set_slack_tokens(bot_token=args.set_bot_token, app_token=args.set_app_token)
        if result.get("success"):
            print("OK: Token(s) stored in vault")
        else:
            print(f"ERROR: {result.get('error')}")
        sys.exit(0 if result.get("success") else 1)

    elif args.status:
        tokens = get_slack_tokens()
        status = {
            "bot_token_configured": bool(tokens["bot_token"]),
            "bot_token_preview": f"{tokens['bot_token'][:15]}..." if tokens["bot_token"] else None,
            "app_token_configured": bool(tokens["app_token"]),
            "app_token_preview": f"{tokens['app_token'][:15]}..." if tokens["app_token"] else None,
        }
        configured = tokens["bot_token"] and tokens["app_token"]
        print("OK" if configured else "NOT FULLY CONFIGURED")
        print(json.dumps(status, indent=2))

    elif args.test:
        tokens = get_slack_tokens()
        if not tokens["bot_token"]:
            print("ERROR: No bot token configured")
            sys.exit(1)

        try:
            from slack_sdk import WebClient

            client = WebClient(token=tokens["bot_token"])
            auth = client.auth_test()

            result = {
                "success": True,
                "bot_id": auth["bot_id"],
                "bot_name": auth["user"],
                "team": auth["team"],
                "app_token_configured": bool(tokens["app_token"]),
            }
            print("OK")
            print(json.dumps(result, indent=2))

        except ImportError:
            print("ERROR: slack-sdk not installed")
            sys.exit(1)
        except Exception as e:
            print("ERROR")
            print(json.dumps({"success": False, "error": str(e)}, indent=2))
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
