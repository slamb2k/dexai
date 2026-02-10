"""
DexAI Channel MCP Tools

Provides channel management tools including:
- channel_pair: Complete pairing flow with a pairing code
- generate_image: Generate images with DALL-E

These are exposed via SDK tools for natural language invocation.
"""

import threading
from typing import Any

# Thread-local storage for pending images
# Used to pass generated image URLs to the response handler
_pending_images = threading.local()


def get_pending_image() -> str | None:
    """Get the pending image URL for the current thread."""
    return getattr(_pending_images, "url", None)


def set_pending_image(url: str) -> None:
    """Set a pending image URL for the response handler to send."""
    _pending_images.url = url


def clear_pending_image() -> None:
    """Clear the pending image URL."""
    _pending_images.url = None


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


def dexai_generate_image(
    prompt: str,
    size: str = "1024x1024",
    quality: str = "standard",
) -> dict[str, Any]:
    """
    Generate an image using DALL-E and return the URL.

    Use this tool when the user asks you to create, generate, or draw an image.
    The generated image URL will be automatically sent to the user's chat.

    Args:
        prompt: Detailed description of the image to generate
        size: Image size - "1024x1024" (square), "1792x1024" (wide), "1024x1792" (tall)
        quality: "standard" or "hd" (higher quality, costs more)

    Returns:
        {"success": True, "image_url": str, "cost_usd": float} on success
        {"success": False, "error": str} on failure
    """
    import asyncio
    import logging

    logger = logging.getLogger(__name__)

    try:
        from tools.channels.image_generator import ImageGenerator

        generator = ImageGenerator()

        # Run async generation
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already in async context - create task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    generator.generate(prompt, size, quality)
                )
                image_url, cost = future.result(timeout=60)
        else:
            image_url, cost = asyncio.run(generator.generate(prompt, size, quality))

        logger.info(f"Generated image for prompt: {prompt[:50]}...")

        # Store the URL for the response handler to send inline
        set_pending_image(image_url)

        return {
            "success": True,
            "image_url": image_url,
            "cost_usd": cost,
            "message": "I've generated the image and it will be sent to your chat.",
            "_dexai_image_url": image_url,
        }

    except ImportError as e:
        return {
            "success": False,
            "error": f"Image generation not available: {e}. Run: uv pip install openai",
        }
    except ValueError as e:
        return {
            "success": False,
            "error": str(e),
        }
    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        return {
            "success": False,
            "error": f"Failed to generate image: {str(e)[:100]}",
        }
