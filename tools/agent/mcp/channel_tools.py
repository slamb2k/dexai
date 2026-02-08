"""
DexAI Channel MCP Tools

Provides channel management tools including:
- channel_pair: Complete pairing flow with a pairing code

These are exposed via SDK tools for natural language invocation.
"""

from typing import Any


def dexai_channel_pair(code: str) -> dict[str, Any]:
    """
    Complete channel pairing using a pairing code.

    This allows users to link their external channel (Telegram, Discord, etc.)
    to their DexAI account by entering the pairing code they received.

    Args:
        code: The pairing code (e.g., "29283")

    Returns:
        {"success": True, "channel": str, "message": str} on success
        {"success": False, "error": str} on failure
    """
    import logging
    logger = logging.getLogger(__name__)

    from tools.channels.inbox import (
        consume_pairing_code,
        link_identity,
        update_user_paired_status,
    )

    # Clean up the code (remove spaces, normalize)
    original_code = code
    code = code.strip().upper() if code else ""
    logger.info(f"[PAIRING] Attempting to pair with code: '{code}' (original: '{original_code}')")

    if not code:
        return {
            "success": False,
            "error": "No pairing code provided. Please provide the code you received in your chat app.",
        }

    # Validate and consume the code
    result = consume_pairing_code(code)

    if not result.get("success"):
        error = result.get("error", "unknown_error")
        error_messages = {
            "code_not_found": "That pairing code wasn't found. Please check the code and try again.",
            "code_already_used": "That pairing code has already been used. Request a new one from your chat app.",
            "code_expired": "That pairing code has expired. Request a new one from your chat app.",
        }
        return {
            "success": False,
            "error": error_messages.get(error, f"Pairing failed: {error}"),
        }

    # Extract pairing info
    user_id = result.get("user_id")
    channel = result.get("channel")
    channel_user_id = result.get("channel_user_id")

    # Link the identity (connects channel identity to internal user)
    link_result = link_identity(user_id, channel, channel_user_id)
    if not link_result.get("success"):
        return {
            "success": False,
            "error": f"Failed to link identity: {link_result.get('error')}",
        }

    # Update the paired status
    update_user_paired_status(user_id, is_paired=True)

    # Grant the 'user' role for chat permissions
    try:
        from tools.security.permissions import grant_role
        grant_role(user_id, "user", granted_by="pairing_system")
        logger.info(f"[PAIRING] Granted 'user' role to {user_id}")
    except Exception as e:
        logger.warning(f"[PAIRING] Failed to grant user role: {e}")
        # Continue anyway - pairing succeeded even if role grant failed

    # Format friendly channel name
    channel_names = {
        "telegram": "Telegram",
        "discord": "Discord",
        "slack": "Slack",
        "whatsapp": "WhatsApp",
    }
    friendly_channel = channel_names.get(channel.lower(), channel.title())

    return {
        "success": True,
        "channel": channel,
        "user_id": user_id,
        "message": f"Successfully paired your {friendly_channel} account! You can now use DexAI from {friendly_channel} with full access to all features.",
    }


def dexai_get_linked_channels() -> dict[str, Any]:
    """
    Get all channels linked to the current user.

    Returns:
        {"success": True, "channels": [...]} on success
    """
    # Note: This would need user context from the session
    # For now, return a placeholder
    return {
        "success": True,
        "channels": [],
        "message": "Use this from a paired channel to see your linked accounts.",
    }
