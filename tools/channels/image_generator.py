"""
Image Generator for Multi-Modal Messaging

Generates images using DALL-E API and provides utilities for sending
images across different messaging channels.

Usage:
    from tools.channels.image_generator import ImageGenerator

    generator = ImageGenerator()
    image_url, cost = await generator.generate("a cute dog playing fetch")
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

import httpx
import yaml
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Ensure project root is in path
import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

# Config path
CONFIG_PATH = PROJECT_ROOT / "args" / "multimodal.yaml"


def load_config() -> dict[str, Any]:
    """Load multimodal configuration."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


class ImageGenerator:
    """
    Generate images using DALL-E API.

    Supports:
    - DALL-E 3 for high quality images
    - DALL-E 2 for faster/cheaper generation
    - Cost tracking
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize image generator.

        Args:
            config: Optional config override (defaults to args/multimodal.yaml)
        """
        self.config = config or load_config()
        self._client = None

    def _get_client(self):
        """Get or create OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI()
            except ImportError:
                raise ImportError(
                    "openai package not installed. Run: uv pip install openai"
                )
        return self._client

    async def generate(
        self,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "standard",
        style: str = "natural",
    ) -> tuple[str, float]:
        """
        Generate an image from a text prompt.

        Args:
            prompt: Text description of the image to generate
            size: Image size - "1024x1024", "1792x1024", or "1024x1792"
            quality: "standard" or "hd" (DALL-E 3 only)
            style: "natural" or "vivid" (DALL-E 3 only)

        Returns:
            Tuple of (image_url, cost_usd)
        """
        gen_config = self.config.get("generation", {})

        if not gen_config.get("enabled", True):
            raise RuntimeError("Image generation is disabled")

        # Check cost limits
        max_cost = gen_config.get("max_cost_per_image", 0.10)
        estimated_cost = self._estimate_cost(size, quality)

        if estimated_cost > max_cost:
            raise ValueError(
                f"Estimated cost ${estimated_cost:.3f} exceeds limit ${max_cost:.3f}"
            )

        client = self._get_client()
        model = gen_config.get("model", "dall-e-3")

        try:
            response = await client.images.generate(
                model=model,
                prompt=prompt,
                size=size,
                quality=quality,
                style=style,
                n=1,
            )

            image_url = response.data[0].url
            actual_cost = self._estimate_cost(size, quality)

            logger.info(f"Generated image: {prompt[:50]}... (${actual_cost:.3f})")

            return image_url, actual_cost

        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            raise

    async def generate_and_download(
        self,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "standard",
        style: str = "natural",
    ) -> tuple[bytes, float]:
        """
        Generate an image and download it as bytes.

        Args:
            prompt: Text description of the image
            size: Image size
            quality: Image quality
            style: Image style

        Returns:
            Tuple of (image_bytes, cost_usd)
        """
        image_url, cost = await self.generate(prompt, size, quality, style)

        # Download the image
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(image_url)
            response.raise_for_status()
            image_bytes = response.content

        return image_bytes, cost

    def _estimate_cost(self, size: str, quality: str) -> float:
        """
        Estimate cost for image generation.

        Based on OpenAI DALL-E 3 pricing (as of 2024):
        - Standard 1024x1024: $0.040
        - Standard 1024x1792 or 1792x1024: $0.080
        - HD 1024x1024: $0.080
        - HD 1024x1792 or 1792x1024: $0.120
        """
        pricing = self.config.get("generation", {}).get("pricing", {})

        if quality == "hd":
            if size == "1024x1024":
                return pricing.get("hd_square", 0.080)
            else:
                return pricing.get("hd_wide", 0.120)
        else:
            if size == "1024x1024":
                return pricing.get("standard_square", 0.040)
            else:
                return pricing.get("standard_wide", 0.080)


# =============================================================================
# Module-Level Instance
# =============================================================================

_generator_instance: ImageGenerator | None = None


def get_image_generator() -> ImageGenerator:
    """Get or create the global ImageGenerator instance."""
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = ImageGenerator()
    return _generator_instance


# =============================================================================
# CLI Interface
# =============================================================================


async def _async_main(prompt: str, size: str, quality: str):
    """Async CLI helper."""
    generator = ImageGenerator()
    url, cost = await generator.generate(prompt, size, quality)
    print(f"Generated image URL: {url}")
    print(f"Cost: ${cost:.3f}")


def main():
    """CLI for testing image generator."""
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Image Generator Test")
    parser.add_argument("prompt", nargs="?", help="Image prompt")
    parser.add_argument("--size", default="1024x1024", help="Image size")
    parser.add_argument("--quality", default="standard", choices=["standard", "hd"])
    parser.add_argument("--config", action="store_true", help="Show config")

    args = parser.parse_args()

    if args.config:
        import json
        config = load_config()
        print(json.dumps(config.get("generation", {}), indent=2))
    elif args.prompt:
        asyncio.run(_async_main(args.prompt, args.size, args.quality))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
