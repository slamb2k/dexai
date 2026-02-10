"""
Location Processor for Multi-Modal Messaging (Phase 15d)

Handles geocoding and place lookup for location attachments:
- Reverse geocoding (lat/lon -> address) via OpenStreetMap Nominatim
- Forward geocoding (address -> lat/lon) via Nominatim
- Map URL generation

Uses httpx for async HTTP calls. Respects Nominatim rate limit (1 req/sec).

Usage:
    from tools.channels.media.location_processor import get_location_processor

    processor = get_location_processor()
    result = await processor.process_location(51.5074, -0.1278)
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

# Config path
CONFIG_PATH = PROJECT_ROOT / "args" / "multimodal.yaml"

# Nominatim API base URL
NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"

# User-Agent header required by Nominatim usage policy
NOMINATIM_USER_AGENT = "DexAI/1.0"

# Minimum interval between Nominatim requests (seconds)
NOMINATIM_RATE_LIMIT = 1.0


def _load_config() -> dict[str, Any]:
    """Load multimodal configuration."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


class LocationProcessor:
    """
    Process location data with geocoding and place lookup.

    Phase 15d: Provides reverse and forward geocoding via the
    OpenStreetMap Nominatim API, with rate limiting and graceful
    fallback on errors.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """
        Initialize location processor.

        Args:
            config: Optional config override (defaults to args/multimodal.yaml).
        """
        self.config = config or _load_config()
        self._last_request_time: float = 0.0
        self._httpx_client: Any | None = None

    async def _get_client(self) -> Any:
        """
        Get or create the async httpx client.

        Returns:
            An httpx.AsyncClient instance.

        Raises:
            ImportError: If httpx is not installed.
        """
        if self._httpx_client is None:
            try:
                import httpx
            except ImportError:
                raise ImportError(
                    "httpx is required for location processing. "
                    "Run: uv pip install httpx"
                )
            self._httpx_client = httpx.AsyncClient(
                headers={"User-Agent": NOMINATIM_USER_AGENT},
                timeout=10.0,
            )
        return self._httpx_client

    async def _rate_limit(self) -> None:
        """Enforce Nominatim rate limit of 1 request per second."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < NOMINATIM_RATE_LIMIT:
            await asyncio.sleep(NOMINATIM_RATE_LIMIT - elapsed)
        self._last_request_time = time.monotonic()

    async def process_location(
        self, latitude: float, longitude: float, **kwargs: Any
    ) -> dict[str, Any]:
        """
        Process a location by reverse geocoding coordinates.

        Performs a reverse geocode lookup via Nominatim and returns
        structured location data. Falls back gracefully if geocoding
        fails, returning coordinates and a map URL without address info.

        Args:
            latitude: Latitude in decimal degrees.
            longitude: Longitude in decimal degrees.
            **kwargs: Additional metadata (ignored, reserved for future use).

        Returns:
            Dict with keys: success, latitude, longitude, address,
            place_name, map_url. On geocoding failure, address and
            place_name will be empty strings.
        """
        map_url = (
            f"https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}"
            f"#map=16/{latitude}/{longitude}"
        )

        # Attempt reverse geocoding
        try:
            client = await self._get_client()
            await self._rate_limit()

            response = await client.get(
                f"{NOMINATIM_BASE_URL}/reverse",
                params={
                    "lat": str(latitude),
                    "lon": str(longitude),
                    "format": "jsonv2",
                    "addressdetails": "1",
                },
            )
            response.raise_for_status()
            data = response.json()

            address = data.get("display_name", "")
            place_name = data.get("name", "") or data.get("namedetails", {}).get(
                "name", ""
            )

            # If no specific place name, try to build one from address parts
            if not place_name:
                addr_parts = data.get("address", {})
                place_name = (
                    addr_parts.get("amenity", "")
                    or addr_parts.get("building", "")
                    or addr_parts.get("road", "")
                    or addr_parts.get("suburb", "")
                    or addr_parts.get("city", "")
                    or ""
                )

            logger.info(
                f"Reverse geocoded ({latitude}, {longitude}) -> {address[:80]}"
            )

            return {
                "success": True,
                "latitude": latitude,
                "longitude": longitude,
                "address": address,
                "place_name": place_name,
                "map_url": map_url,
            }

        except ImportError:
            # httpx not installed - return basic result
            logger.warning("httpx not available for geocoding")
            return {
                "success": True,
                "latitude": latitude,
                "longitude": longitude,
                "address": "",
                "place_name": "",
                "map_url": map_url,
            }

        except Exception as e:
            logger.warning(f"Reverse geocoding failed: {e}")
            return {
                "success": True,
                "latitude": latitude,
                "longitude": longitude,
                "address": "",
                "place_name": "",
                "map_url": map_url,
            }

    async def geocode_address(self, address: str) -> dict[str, Any]:
        """
        Forward geocode an address string to coordinates.

        Looks up an address via Nominatim and returns the best matching
        latitude, longitude, and display name.

        Args:
            address: Free-form address string to geocode.

        Returns:
            Dict with keys: success, latitude, longitude, display_name.
            On failure, success is False and an error key is included.
        """
        if not address or not address.strip():
            return {
                "success": False,
                "error": "Empty address provided",
            }

        try:
            client = await self._get_client()
            await self._rate_limit()

            response = await client.get(
                f"{NOMINATIM_BASE_URL}/search",
                params={
                    "q": address.strip(),
                    "format": "jsonv2",
                    "limit": "1",
                    "addressdetails": "1",
                },
            )
            response.raise_for_status()
            results = response.json()

            if not results:
                return {
                    "success": False,
                    "error": f"No results found for: {address[:100]}",
                }

            best = results[0]
            lat = float(best["lat"])
            lon = float(best["lon"])
            display_name = best.get("display_name", address)

            logger.info(f"Geocoded '{address[:60]}' -> ({lat}, {lon})")

            return {
                "success": True,
                "latitude": lat,
                "longitude": lon,
                "display_name": display_name,
            }

        except ImportError:
            return {
                "success": False,
                "error": "httpx is required for geocoding. Run: uv pip install httpx",
            }

        except Exception as e:
            logger.error(f"Forward geocoding failed: {e}")
            return {
                "success": False,
                "error": f"Geocoding failed: {str(e)[:200]}",
            }

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._httpx_client is not None:
            await self._httpx_client.aclose()
            self._httpx_client = None


# =============================================================================
# Singleton Factory
# =============================================================================

_instance: LocationProcessor | None = None


def get_location_processor(config: dict[str, Any] | None = None) -> LocationProcessor:
    """
    Get or create the global LocationProcessor instance.

    Args:
        config: Optional config override for first initialization.

    Returns:
        The singleton LocationProcessor instance.
    """
    global _instance
    if _instance is None:
        _instance = LocationProcessor(config=config)
    return _instance
