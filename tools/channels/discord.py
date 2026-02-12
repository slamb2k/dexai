"""
Tool: Discord Channel Adapter
Purpose: Discord bot integration for DexAI

Connects to Discord using discord.py with slash commands.
Handles DMs, mentions, and slash commands (/ask, /pair).

Usage:
    python tools/channels/discord.py --start
    python tools/channels/discord.py --status
    python tools/channels/discord.py --test

Dependencies (pip):
    - discord.py>=2.0

Secrets (via vault, namespace: channels):
    - DISCORD_BOT_TOKEN
"""

import argparse
import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.channels.models import Attachment, UnifiedMessage
from tools.channels.router import ChannelAdapter, get_router


class DiscordAdapter(ChannelAdapter):
    """
    Discord bot adapter using discord.py.

    Handles:
    - DM messages - Route through gateway
    - @mentions - Route through gateway
    - /ask - Ask the AI a question
    - /pair - Generate pairing code
    - /help - Show available commands
    """

    @property
    def name(self) -> str:
        return "discord"

    def __init__(self, token: str):
        """
        Initialize Discord adapter.

        Args:
            token: Discord bot token
        """
        self.token = token
        self.client = None
        self.tree = None
        self.router = None
        self._connected = False

    def set_router(self, router) -> None:
        """Set reference to the parent router."""
        self.router = router

    async def connect(self) -> None:
        """Initialize bot and connect to Discord."""
        try:
            import discord
            from discord import app_commands
        except ImportError:
            raise ImportError("discord.py required. Install with: pip install discord.py")

        # Setup intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.dm_messages = True
        intents.guild_messages = True

        self.client = discord.Client(intents=intents)
        self.tree = app_commands.CommandTree(self.client)

        # Register event handlers
        @self.client.event
        async def on_ready():
            # Sync slash commands
            await self.tree.sync()
            self._connected = True

            # Log startup
            try:
                from tools.security import audit

                audit.log_event(
                    event_type="system",
                    action="discord_connected",
                    channel="discord",
                    status="success",
                    details={"bot_id": self.client.user.id, "bot_name": self.client.user.name},
                )
            except Exception:
                pass

            print(f"Discord bot ready: {self.client.user.name}")

        @self.client.event
        async def on_message(message: discord.Message):
            # Ignore own messages
            if message.author == self.client.user:
                return

            # Handle DMs
            if isinstance(message.channel, discord.DMChannel):
                await self._handle_dm(message)

            # Handle mentions
            elif self.client.user.mentioned_in(message):
                await self._handle_mention(message)

        # Register slash commands
        @self.tree.command(name="ask", description="Ask the AI a question")
        async def ask_command(interaction: discord.Interaction, question: str):
            await self._handle_ask(interaction, question)

        @self.tree.command(name="pair", description="Pair your Discord account")
        async def pair_command(interaction: discord.Interaction):
            await self._handle_pair(interaction)

        @self.tree.command(name="help", description="Show available commands")
        async def help_command(interaction: discord.Interaction):
            await self._handle_help(interaction)

        @self.tree.command(name="status", description="Check connection status")
        async def status_command(interaction: discord.Interaction):
            await self._handle_status(interaction)

        # Start the client
        await self.client.start(self.token)

    async def health_check(self) -> dict[str, Any]:
        """
        Check Discord bot connection health.

        Returns:
            Dict with connected status, latency_ms, and optional error
        """
        if not self._connected or not self.client:
            return {"connected": False, "error": "Not connected"}

        try:
            # Discord.py provides latency directly
            latency_ms = int(self.client.latency * 1000)

            # Check if we have a valid user
            if not self.client.user:
                return {"connected": False, "error": "Bot user not available"}

            return {
                "connected": True,
                "latency_ms": latency_ms,
                "bot_username": self.client.user.name,
                "bot_id": self.client.user.id,
                "guilds": len(self.client.guilds),
            }
        except Exception as e:
            return {"connected": False, "error": str(e)[:100]}

    async def disconnect(self) -> None:
        """Disconnect from Discord."""
        if self.client:
            await self.client.close()

        self._connected = False

        # Log shutdown
        try:
            from tools.security import audit

            audit.log_event(
                event_type="system",
                action="discord_disconnected",
                channel="discord",
                status="success",
            )
        except Exception:
            pass

    async def send_message(self, message: UnifiedMessage) -> dict[str, Any]:
        """
        Send message to Discord.

        Args:
            message: UnifiedMessage to send

        Returns:
            Dict with success status and message ID
        """
        try:
            # Get channel or user to send to
            channel_id = message.metadata.get("discord_channel_id")
            user_id = message.channel_user_id

            target = None

            if channel_id:
                target = self.client.get_channel(int(channel_id))

            if not target and user_id:
                try:
                    user = await self.client.fetch_user(int(user_id))
                    target = await user.create_dm()
                except Exception:
                    pass

            if not target:
                return {"success": False, "error": "no_target_channel"}

            result = await target.send(message.content)

            return {
                "success": True,
                "message_id": str(result.id),
                "channel_id": str(result.channel.id),
                "message_obj": result,  # Include message object for updates
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def send_image(
        self,
        channel_id: str | int | None = None,
        user_id: str | int | None = None,
        image: bytes | str = None,
        caption: str | None = None,
    ) -> dict[str, Any]:
        """
        Send an image to a Discord channel or user.

        Args:
            channel_id: Discord channel ID to send to
            user_id: Discord user ID for DM (if no channel_id)
            image: Image bytes or URL
            caption: Optional caption/message content

        Returns:
            Dict with success status and message ID
        """
        import io
        import discord

        try:
            target = None

            if channel_id:
                target = self.client.get_channel(int(channel_id))

            if not target and user_id:
                try:
                    user = await self.client.fetch_user(int(user_id))
                    target = await user.create_dm()
                except Exception:
                    pass

            if not target:
                return {"success": False, "error": "no_target_channel"}

            if isinstance(image, str) and image.startswith("http"):
                # URL - download first then send
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(image)
                    response.raise_for_status()
                    image = response.content

            # Send as file attachment
            file = discord.File(io.BytesIO(image), filename="image.png")
            result = await target.send(content=caption, file=file)

            return {
                "success": True,
                "message_id": str(result.id),
                "channel_id": str(result.channel.id),
            }

        except Exception as e:
            logger.error(f"Failed to send image: {e}")
            return {"success": False, "error": str(e)}

    async def send_voice(
        self,
        channel_id: str | int | None = None,
        user_id: str | int | None = None,
        audio: bytes = None,
        caption: str | None = None,
        filename: str = "voice.ogg",
    ) -> dict[str, Any]:
        """
        Send a voice/audio file to a Discord channel or user (Phase 15b).

        Args:
            channel_id: Discord channel ID to send to
            user_id: Discord user ID for DM (if no channel_id)
            audio: Audio bytes (OGG/Opus format preferred)
            caption: Optional caption/message content
            filename: Filename for the audio file

        Returns:
            Dict with success status and message ID
        """
        import io
        import discord

        try:
            target = None

            if channel_id:
                target = self.client.get_channel(int(channel_id))

            if not target and user_id:
                try:
                    user = await self.client.fetch_user(int(user_id))
                    target = await user.create_dm()
                except Exception:
                    pass

            if not target:
                return {"success": False, "error": "no_target_channel"}

            # Send audio as attachment
            audio_file = io.BytesIO(audio)
            file = discord.File(audio_file, filename=filename)

            result = await target.send(content=caption, file=file)

            return {
                "success": True,
                "message_id": str(result.id),
                "channel_id": str(result.channel.id),
            }

        except Exception as e:
            logger.error(f"Failed to send voice: {e}")
            return {"success": False, "error": str(e)}

    async def update_message(
        self,
        message_obj,
        content: str,
    ) -> dict[str, Any]:
        """
        Update an existing Discord message.

        Used for streaming responses by progressively updating the message.
        Discord has a 2000 character limit per message.

        Args:
            message_obj: Discord Message object to update
            content: New message content (truncated at 2000 chars)

        Returns:
            Dict with success status
        """
        try:
            # Respect Discord's 2000 character limit
            truncated_content = content[:2000]
            await message_obj.edit(content=truncated_content)
            return {"success": True}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def to_unified(self, message) -> UnifiedMessage:
        """
        Convert Discord Message to UnifiedMessage.

        Args:
            message: Discord Message object

        Returns:
            UnifiedMessage normalized from Discord
        """
        try:
            import discord
        except ImportError:
            raise ImportError("discord.py required")

        content_type = "text"
        attachments = []

        # Handle attachments
        for attach in message.attachments:
            if attach.content_type and attach.content_type.startswith("image"):
                att_type = "image"
                if content_type == "text":
                    content_type = "image"
            elif attach.content_type and attach.content_type.startswith("audio"):
                att_type = "audio"
            elif attach.content_type and attach.content_type.startswith("video"):
                att_type = "video"
            else:
                att_type = "document"

            attachments.append(
                Attachment(
                    id=str(attach.id),
                    type=att_type,
                    filename=attach.filename,
                    mime_type=attach.content_type or "application/octet-stream",
                    size_bytes=attach.size,
                    url=attach.url,
                )
            )

        # Clean content (remove bot mention)
        content = message.content
        if self.client and self.client.user:
            content = content.replace(f"<@{self.client.user.id}>", "").strip()
            content = content.replace(f"<@!{self.client.user.id}>", "").strip()

        # Determine conversation type
        conv_type = "dm" if isinstance(message.channel, discord.DMChannel) else "channel"

        return UnifiedMessage(
            id=str(uuid.uuid4()),
            channel="discord",
            channel_message_id=str(message.id),
            user_id=None,  # Resolved by router
            channel_user_id=str(message.author.id),
            direction="inbound",
            content=content,
            content_type=content_type,
            attachments=attachments,
            reply_to=str(message.reference.message_id) if message.reference else None,
            timestamp=message.created_at,
            metadata={
                "discord_channel_id": message.channel.id,
                "discord_guild_id": message.guild.id if message.guild else None,
                "discord_channel_type": conv_type,
                "display_name": message.author.display_name,
                "username": message.author.name,
            },
        )

    def from_unified(self, message: UnifiedMessage) -> dict[str, Any]:
        """
        Convert UnifiedMessage to Discord send parameters.

        Args:
            message: UnifiedMessage to convert

        Returns:
            Dict with Discord API parameters
        """
        return {
            "content": message.content,
            "channel_id": message.metadata.get("discord_channel_id"),
        }

    async def download_attachment(self, attachment: Attachment) -> bytes:
        """
        Download attachment content from Discord CDN.

        Uses the URL stored in attachment.url to download the file.
        Note: Discord CDN URLs may expire after some time.

        Args:
            attachment: Attachment with Discord CDN URL

        Returns:
            File content as bytes

        Raises:
            ValueError: If no URL available
            Exception: On download failure
        """
        if not attachment.url:
            raise ValueError("No URL in Discord attachment")

        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(attachment.url)
            response.raise_for_status()
            return response.content

    # =========================================================================
    # Message Handlers
    # =========================================================================

    async def _handle_dm(self, message) -> None:
        """Handle DM messages."""
        if not self.router:
            await message.reply("System not ready. Please try again later.")
            return

        unified = self.to_unified(message)
        result = await self.router.route_inbound(unified)

        if not result.get("success"):
            reason = result.get("reason", "unknown")

            if reason == "user_not_paired":
                await message.reply("Please pair your account first using `/pair`")
            elif reason == "rate_limited":
                await message.reply("You're sending messages too quickly. Please wait.")
            elif reason == "content_blocked":
                await message.reply("Your message could not be processed.")

    async def _handle_mention(self, message) -> None:
        """Handle @mentions."""
        if not self.router:
            await message.reply("System not ready. Please try again later.")
            return

        unified = self.to_unified(message)
        result = await self.router.route_inbound(unified)

        if not result.get("success"):
            reason = result.get("reason", "unknown")

            if reason == "user_not_paired":
                await message.reply("Please pair your account first using `/pair`")
            elif reason == "rate_limited":
                await message.reply("You're sending messages too quickly. Please wait.")

    # =========================================================================
    # Slash Command Handlers
    # =========================================================================

    async def _handle_ask(self, interaction, question: str) -> None:
        """Handle /ask command."""
        # Defer to avoid timeout
        await interaction.response.defer()

        if not self.router:
            await interaction.followup.send("System not ready. Please try again later.")
            return

        # Create message from question
        unified = UnifiedMessage(
            id=str(uuid.uuid4()),
            channel="discord",
            channel_message_id=str(interaction.id),
            user_id=None,
            channel_user_id=str(interaction.user.id),
            direction="inbound",
            content=question,
            content_type="text",
            metadata={
                "discord_channel_id": interaction.channel_id,
                "discord_guild_id": interaction.guild_id,
                "display_name": interaction.user.display_name,
                "username": interaction.user.name,
                "is_slash_command": True,
            },
        )

        result = await self.router.route_inbound(unified)

        if not result.get("success"):
            reason = result.get("reason", "unknown")

            if reason == "user_not_paired":
                await interaction.followup.send("Please pair your account first using `/pair`")
            elif reason == "rate_limited":
                await interaction.followup.send("You're sending messages too quickly. Please wait.")
            else:
                await interaction.followup.send("Your question has been received.")
        else:
            await interaction.followup.send(
                "Your question has been received and is being processed."
            )

    async def _handle_pair(self, interaction) -> None:
        """Handle /pair command (deprecated in single-tenant mode)."""
        await interaction.response.send_message(
            "Account pairing is no longer needed.\n\n"
            "Your Discord user ID is automatically recognized. "
            "If you're not getting responses, ask the owner to add your "
            "Discord user ID to the allowed users list.",
            ephemeral=True,
        )

    async def _handle_help(self, interaction) -> None:
        """Handle /help command."""
        import discord

        embed = discord.Embed(
            title="DexAI Help", description="Your AI assistant for adulting tasks", color=0x5865F2
        )

        embed.add_field(
            name="Commands",
            value=(
                "`/ask` - Ask the AI a question\n"
                "`/pair` - Link your account\n"
                "`/help` - Show this help\n"
                "`/status` - Check connection"
            ),
            inline=False,
        )

        embed.add_field(
            name="Messaging",
            value=(
                "Send me a DM to chat privately\n"
                "@mention me in a channel to ask questions\n"
                "Attach files for context"
            ),
            inline=False,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _handle_status(self, interaction) -> None:
        """Handle /status command."""
        channel_user_id = str(interaction.user.id)

        await interaction.response.send_message(
            f"**Connection Status:** Connected\n"
            f"**Your Discord ID:** {channel_user_id}\n"
            f"**Platform:** Discord",
            ephemeral=True,
        )



# =============================================================================
# Token Management
# =============================================================================


def get_discord_token() -> str | None:
    """
    Get Discord bot token from vault.

    Returns:
        Token string or None if not found
    """
    try:
        from tools.security import vault

        result = vault.get_secret("DISCORD_BOT_TOKEN", namespace="channels")
        if result.get("success"):
            return result.get("value")
    except Exception:
        pass

    # Fallback to environment variable
    import os

    return os.environ.get("DISCORD_BOT_TOKEN")


def set_discord_token(token: str) -> dict[str, Any]:
    """
    Store Discord bot token in vault.

    Args:
        token: Discord bot token

    Returns:
        Result dict
    """
    try:
        from tools.security import vault

        return vault.set_secret("DISCORD_BOT_TOKEN", token, namespace="channels")
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# CLI Interface
# =============================================================================


async def run_adapter() -> None:
    """Run the Discord adapter."""
    token = get_discord_token()
    if not token:
        print("ERROR: DISCORD_BOT_TOKEN not found in vault or environment")
        print("Set with: python tools/channels/discord.py --set-token YOUR_TOKEN")
        sys.exit(1)

    adapter = DiscordAdapter(token)
    router = get_router()
    router.register_adapter(adapter)

    # Register SDK handler for full Claude Agent SDK capabilities
    # Uses streaming handler for progressive message updates
    from tools.channels.sdk_handler import sdk_handler_with_streaming
    router.add_message_handler(sdk_handler_with_streaming)

    print("Starting Discord adapter with streaming support...")
    await adapter.connect()


def main():
    parser = argparse.ArgumentParser(description="Discord Channel Adapter")
    parser.add_argument("--start", action="store_true", help="Start the adapter")
    parser.add_argument("--status", action="store_true", help="Check adapter status")
    parser.add_argument("--set-token", metavar="TOKEN", help="Set bot token in vault")
    parser.add_argument("--test", action="store_true", help="Test token validity")

    args = parser.parse_args()

    if args.set_token:
        result = set_discord_token(args.set_token)
        if result.get("success"):
            print("OK: Token stored in vault")
        else:
            print(f"ERROR: {result.get('error')}")
        sys.exit(0 if result.get("success") else 1)

    elif args.status:
        token = get_discord_token()
        status = {
            "token_configured": bool(token),
            "token_preview": f"{token[:10]}..." if token else None,
        }
        print("OK" if token else "NOT CONFIGURED")
        print(json.dumps(status, indent=2))

    elif args.test:
        token = get_discord_token()
        if not token:
            print("ERROR: No token configured")
            sys.exit(1)

        try:
            import discord

            async def test_token():
                try:
                    intents = discord.Intents.default()
                    client = discord.Client(intents=intents)

                    @client.event
                    async def on_ready():
                        result = {
                            "success": True,
                            "bot_id": client.user.id,
                            "bot_name": client.user.name,
                        }
                        print("OK")
                        print(json.dumps(result, indent=2))
                        await client.close()

                    await client.start(token)

                except Exception as e:
                    print("ERROR")
                    print(json.dumps({"success": False, "error": str(e)}, indent=2))

            asyncio.run(test_token())

        except ImportError:
            print("ERROR: discord.py not installed")
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
