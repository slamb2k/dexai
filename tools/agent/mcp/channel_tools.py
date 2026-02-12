"""
DexAI Channel MCP Tools

Provides channel management tools including:
- channel_pair: Deprecated (single-tenant, access via allowlist)
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
    Channel pairing is no longer required (single-tenant).

    Access is now controlled via allowed_channel_user_ids in args/user.yaml.

    Args:
        code: Ignored (pairing codes are deprecated)

    Returns:
        {"success": False, "error": str} always
    """
    return {
        "success": False,
        "error": (
            "Pairing is no longer required. "
            "Access is managed via allowed_channel_user_ids in your user configuration."
        ),
    }


def dexai_get_linked_channels() -> dict[str, Any]:
    """
    Get linked channels (single-tenant: returns configured channels).

    Returns:
        {"success": True, "message": str}
    """
    return {
        "success": True,
        "message": "Single-tenant mode: channels are configured via allowed_channel_user_ids in args/user.yaml.",
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
