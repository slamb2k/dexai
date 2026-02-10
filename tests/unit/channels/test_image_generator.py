"""Tests for tools/channels/image_generator.py

Tests the ImageGenerator class:
- Cost estimation for different sizes and qualities
- Image generation via mocked OpenAI API
- Download-and-generate flow via mocked httpx
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from tools.channels.image_generator import ImageGenerator


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def generation_config():
    """Minimal config with generation section and pricing."""
    return {
        "generation": {
            "enabled": True,
            "model": "dall-e-3",
            "max_cost_per_image": 0.10,
            "pricing": {
                "standard_square": 0.040,
                "standard_wide": 0.080,
                "hd_square": 0.080,
                "hd_wide": 0.120,
            },
        }
    }


@pytest.fixture
def disabled_config():
    """Config with generation disabled."""
    return {
        "generation": {
            "enabled": False,
        }
    }


@pytest.fixture
def low_cost_config():
    """Config with very low cost limit."""
    return {
        "generation": {
            "enabled": True,
            "model": "dall-e-3",
            "max_cost_per_image": 0.01,
            "pricing": {
                "standard_square": 0.040,
                "standard_wide": 0.080,
                "hd_square": 0.080,
                "hd_wide": 0.120,
            },
        }
    }


def _mock_openai_response(url="https://example.com/image.png"):
    """Create a mock OpenAI images.generate response."""
    mock_image = MagicMock()
    mock_image.url = url
    mock_response = MagicMock()
    mock_response.data = [mock_image]
    return mock_response


# ─────────────────────────────────────────────────────────────────────────────
# Cost Estimation Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEstimateCost:
    """Tests for _estimate_cost pricing calculation."""

    def test_standard_square(self, generation_config):
        gen = ImageGenerator(config=generation_config)
        assert gen._estimate_cost("1024x1024", "standard") == 0.040

    def test_standard_wide(self, generation_config):
        gen = ImageGenerator(config=generation_config)
        assert gen._estimate_cost("1792x1024", "standard") == 0.080

    def test_hd_square(self, generation_config):
        gen = ImageGenerator(config=generation_config)
        assert gen._estimate_cost("1024x1024", "hd") == 0.080

    def test_hd_wide(self, generation_config):
        gen = ImageGenerator(config=generation_config)
        assert gen._estimate_cost("1024x1792", "hd") == 0.120


# ─────────────────────────────────────────────────────────────────────────────
# generate() Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGenerate:
    """Tests for the generate() method."""

    @pytest.mark.asyncio
    async def test_successful_generation(self, generation_config):
        """Successful generation returns (url, cost)."""
        gen = ImageGenerator(config=generation_config)
        mock_response = _mock_openai_response("https://example.com/img.png")

        mock_client = AsyncMock()
        mock_client.images.generate = AsyncMock(return_value=mock_response)
        gen._client = mock_client

        url, cost = await gen.generate("a cute dog")

        assert url == "https://example.com/img.png"
        assert cost == 0.040
        mock_client.images.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disabled_raises_runtime_error(self, disabled_config):
        """Generation disabled in config raises RuntimeError."""
        gen = ImageGenerator(config=disabled_config)

        with pytest.raises(RuntimeError, match="disabled"):
            await gen.generate("anything")

    @pytest.mark.asyncio
    async def test_cost_exceeds_limit_raises_value_error(self, low_cost_config):
        """Cost exceeding max_cost_per_image raises ValueError."""
        gen = ImageGenerator(config=low_cost_config)

        with pytest.raises(ValueError, match="exceeds limit"):
            await gen.generate("anything", size="1024x1024", quality="standard")

    @pytest.mark.asyncio
    async def test_api_exception_propagates(self, generation_config):
        """OpenAI API exception propagates to caller."""
        gen = ImageGenerator(config=generation_config)

        mock_client = AsyncMock()
        mock_client.images.generate = AsyncMock(side_effect=Exception("API error"))
        gen._client = mock_client

        with pytest.raises(Exception, match="API error"):
            await gen.generate("a test prompt")

    @pytest.mark.asyncio
    async def test_uses_model_from_config(self, generation_config):
        """Generation uses the model specified in config."""
        gen = ImageGenerator(config=generation_config)
        mock_response = _mock_openai_response()

        mock_client = AsyncMock()
        mock_client.images.generate = AsyncMock(return_value=mock_response)
        gen._client = mock_client

        await gen.generate("test prompt")

        call_kwargs = mock_client.images.generate.call_args[1]
        assert call_kwargs["model"] == "dall-e-3"


# ─────────────────────────────────────────────────────────────────────────────
# generate_and_download() Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGenerateAndDownload:
    """Tests for generate_and_download()."""

    @pytest.mark.asyncio
    async def test_successful_download(self, generation_config):
        """Successful download returns (bytes, cost)."""
        gen = ImageGenerator(config=generation_config)
        mock_response = _mock_openai_response("https://example.com/img.png")

        mock_client = AsyncMock()
        mock_client.images.generate = AsyncMock(return_value=mock_response)
        gen._client = mock_client

        fake_image_bytes = b"\x89PNG\r\n\x1a\nfake_image_data"

        mock_http_response = MagicMock()
        mock_http_response.content = fake_image_bytes
        mock_http_response.raise_for_status = MagicMock()

        with patch("tools.channels.image_generator.httpx.AsyncClient") as mock_async_client_cls:
            mock_async_client = AsyncMock()
            mock_async_client.get = AsyncMock(return_value=mock_http_response)
            mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
            mock_async_client.__aexit__ = AsyncMock(return_value=False)
            mock_async_client_cls.return_value = mock_async_client

            image_bytes, cost = await gen.generate_and_download("test prompt")

        assert image_bytes == fake_image_bytes
        assert cost == 0.040

    @pytest.mark.asyncio
    async def test_http_error_on_download_propagates(self, generation_config):
        """HTTP error during download propagates."""
        gen = ImageGenerator(config=generation_config)
        mock_response = _mock_openai_response("https://example.com/img.png")

        mock_client = AsyncMock()
        mock_client.images.generate = AsyncMock(return_value=mock_response)
        gen._client = mock_client

        with patch("tools.channels.image_generator.httpx.AsyncClient") as mock_async_client_cls:
            mock_async_client = AsyncMock()
            mock_http_resp = MagicMock()
            mock_http_resp.raise_for_status = MagicMock(
                side_effect=httpx.HTTPStatusError("404", request=MagicMock(), response=MagicMock())
            )
            mock_async_client.get = AsyncMock(return_value=mock_http_resp)
            mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
            mock_async_client.__aexit__ = AsyncMock(return_value=False)
            mock_async_client_cls.return_value = mock_async_client

            with pytest.raises(httpx.HTTPStatusError):
                await gen.generate_and_download("test prompt")

    @pytest.mark.asyncio
    async def test_timeout_on_download_propagates(self, generation_config):
        """Timeout during download propagates."""
        gen = ImageGenerator(config=generation_config)
        mock_response = _mock_openai_response("https://example.com/img.png")

        mock_client = AsyncMock()
        mock_client.images.generate = AsyncMock(return_value=mock_response)
        gen._client = mock_client

        with patch("tools.channels.image_generator.httpx.AsyncClient") as mock_async_client_cls:
            mock_async_client = AsyncMock()
            mock_async_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
            mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
            mock_async_client.__aexit__ = AsyncMock(return_value=False)
            mock_async_client_cls.return_value = mock_async_client

            with pytest.raises(httpx.TimeoutException):
                await gen.generate_and_download("test prompt")
