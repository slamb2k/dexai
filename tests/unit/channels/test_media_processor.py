"""Tests for tools/channels/media_processor.py — MediaProcessor class

Tests attachment processing:
- Routing to image/document processors
- Image analysis via mocked Anthropic Vision API
- Document text extraction via mocked PyPDF2/python-docx
- ADHD-friendly batch limits and budget enforcement
- Error handling at each processing stage
"""

import io
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.channels.media_processor import MediaProcessor
from tools.channels.models import Attachment, MediaContent


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def multimodal_config():
    """Config dict matching args/multimodal.yaml structure."""
    return {
        "processing": {
            "enabled": True,
            "max_file_size_mb": 50,
            "max_processing_cost_usd": 0.20,
            "vision": {
                "enabled": True,
                "pricing": {
                    "input_per_mtok": 3.0,
                    "output_per_mtok": 15.0,
                },
            },
            "documents": {
                "enabled": True,
                "supported_formats": ["pdf", "docx", "txt", "md"],
                "max_pages": 20,
                "max_chars_per_doc": 10000,
            },
        },
        "adhd": {
            "max_attachments": 3,
        },
    }


@pytest.fixture
def disabled_config():
    """Config with processing disabled."""
    return {
        "processing": {
            "enabled": False,
        },
    }


def make_attachment(
    *,
    id="att-1",
    type="image",
    filename="photo.jpg",
    mime_type="image/jpeg",
    size_bytes=1024,
    url=None,
):
    """Factory for creating Attachment instances with defaults."""
    return Attachment(
        id=id,
        type=type,
        filename=filename,
        mime_type=mime_type,
        size_bytes=size_bytes,
        url=url,
    )


@pytest.fixture
def mock_adapter():
    """AsyncMock adapter with configurable download_attachment."""
    adapter = AsyncMock()
    adapter.download_attachment = AsyncMock(return_value=b"fake image data")
    return adapter


@pytest.fixture
def small_jpeg_bytes():
    """Create a minimal valid JPEG-like byte sequence using PIL."""
    try:
        from PIL import Image

        img = Image.new("RGB", (10, 10), color="red")
        output = io.BytesIO()
        img.save(output, format="JPEG")
        return output.getvalue()
    except ImportError:
        # Fallback: return minimal bytes (won't pass PIL validation,
        # but tests that use this fixture mock PIL anyway)
        return b"\xff\xd8\xff\xe0" + b"\x00" * 100


# ─────────────────────────────────────────────────────────────────────────────
# process_attachment() Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestProcessAttachment:
    """Tests for the top-level process_attachment routing."""

    @pytest.mark.asyncio
    async def test_processing_disabled_returns_unprocessed(self, disabled_config, mock_adapter):
        """When processing is disabled, returns processed=False with no API calls."""
        processor = MediaProcessor(config=disabled_config)
        attachment = make_attachment()

        result = await processor.process_attachment(attachment, "telegram", mock_adapter)

        assert result.processed is False
        mock_adapter.download_attachment.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_file_over_size_limit(self, multimodal_config, mock_adapter):
        """File exceeding max_file_size_mb returns error."""
        processor = MediaProcessor(config=multimodal_config)
        attachment = make_attachment(size_bytes=60 * 1024 * 1024)  # 60MB > 50MB limit

        result = await processor.process_attachment(attachment, "telegram", mock_adapter)

        assert result.processed is False
        assert "too large" in result.processing_error

    @pytest.mark.asyncio
    async def test_routes_image_to_process_image(self, multimodal_config, mock_adapter):
        """Image type routes to _process_image."""
        processor = MediaProcessor(config=multimodal_config)
        attachment = make_attachment(type="image")

        with patch.object(processor, "_process_image", new_callable=AsyncMock) as mock_pi:
            mock_pi.return_value = MediaContent(attachment=attachment, processed=True)
            result = await processor.process_attachment(attachment, "telegram", mock_adapter)

        mock_pi.assert_awaited_once_with(attachment, "telegram", mock_adapter)
        assert result.processed is True

    @pytest.mark.asyncio
    async def test_routes_document_to_process_document(self, multimodal_config, mock_adapter):
        """Document type routes to _process_document."""
        processor = MediaProcessor(config=multimodal_config)
        attachment = make_attachment(type="document", filename="report.pdf")

        with patch.object(processor, "_process_document", new_callable=AsyncMock) as mock_pd:
            mock_pd.return_value = MediaContent(attachment=attachment, processed=True)
            result = await processor.process_attachment(attachment, "telegram", mock_adapter)

        mock_pd.assert_awaited_once_with(attachment, "telegram", mock_adapter)
        assert result.processed is True

    @pytest.mark.asyncio
    async def test_unsupported_type_returns_error(self, multimodal_config, mock_adapter):
        """Unsupported attachment type returns processing_error."""
        processor = MediaProcessor(config=multimodal_config)
        attachment = make_attachment(type="sticker")

        result = await processor.process_attachment(attachment, "telegram", mock_adapter)

        assert result.processed is False
        assert "Unsupported type" in result.processing_error

    @pytest.mark.asyncio
    async def test_exception_caught_and_truncated(self, multimodal_config, mock_adapter):
        """Exceptions in processing are caught and error is truncated to 200 chars."""
        processor = MediaProcessor(config=multimodal_config)
        attachment = make_attachment(type="image")
        long_error = "X" * 300

        with patch.object(processor, "_process_image", new_callable=AsyncMock) as mock_pi:
            mock_pi.side_effect = Exception(long_error)
            result = await processor.process_attachment(attachment, "telegram", mock_adapter)

        assert result.processed is False
        assert len(result.processing_error) <= 200


# ─────────────────────────────────────────────────────────────────────────────
# _process_image() Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestProcessImage:
    """Tests for image processing with Vision API."""

    @pytest.mark.asyncio
    async def test_successful_image_processing(
        self, multimodal_config, mock_adapter, small_jpeg_bytes
    ):
        """Successful image: download -> prepare -> vision -> MediaContent."""
        processor = MediaProcessor(config=multimodal_config)
        mock_adapter.download_attachment = AsyncMock(return_value=small_jpeg_bytes)
        attachment = make_attachment()

        fake_prepared = {"type": "image", "source": {"type": "base64", "data": "abc"}}

        # Mock both _prepare_image_for_vision (needs Pillow) and _call_vision_api
        with (
            patch.object(
                processor, "_prepare_image_for_vision", new_callable=AsyncMock
            ) as mock_prepare,
            patch.object(processor, "_call_vision_api", new_callable=AsyncMock) as mock_vision,
        ):
            mock_prepare.return_value = fake_prepared
            mock_vision.return_value = ("A red square image", 0.005)

            result = await processor._process_image(attachment, "telegram", mock_adapter)

        assert result.processed is True
        assert result.vision_description == "A red square image"
        assert result.processing_cost_usd == 0.005

    @pytest.mark.asyncio
    async def test_empty_download_returns_error(self, multimodal_config, mock_adapter):
        """Empty download returns processing_error."""
        processor = MediaProcessor(config=multimodal_config)
        mock_adapter.download_attachment = AsyncMock(return_value=b"")
        attachment = make_attachment()

        result = await processor._process_image(attachment, "telegram", mock_adapter)

        assert result.processed is False
        assert "empty" in result.processing_error.lower()

    @pytest.mark.asyncio
    async def test_download_exception_returns_error(self, multimodal_config, mock_adapter):
        """Download exception populates processing_error."""
        processor = MediaProcessor(config=multimodal_config)
        mock_adapter.download_attachment = AsyncMock(side_effect=Exception("Network error"))
        attachment = make_attachment()

        result = await processor._process_image(attachment, "telegram", mock_adapter)

        assert result.processed is False
        assert "Download failed" in result.processing_error

    @pytest.mark.asyncio
    async def test_vision_disabled_returns_unprocessed(self, mock_adapter):
        """When vision is disabled, returns processed=False."""
        config = {
            "processing": {
                "enabled": True,
                "max_file_size_mb": 50,
                "vision": {"enabled": False},
            }
        }
        processor = MediaProcessor(config=config)
        attachment = make_attachment()

        result = await processor._process_image(attachment, "telegram", mock_adapter)

        assert result.processed is False

    @pytest.mark.asyncio
    async def test_vision_api_exception_returns_error(
        self, multimodal_config, mock_adapter, small_jpeg_bytes
    ):
        """Vision API exception returns error message."""
        processor = MediaProcessor(config=multimodal_config)
        mock_adapter.download_attachment = AsyncMock(return_value=small_jpeg_bytes)
        attachment = make_attachment()

        fake_prepared = {"type": "image", "source": {"type": "base64", "data": "abc"}}

        # Mock _prepare_image_for_vision (needs Pillow) to succeed,
        # then let _call_vision_api raise
        with (
            patch.object(
                processor, "_prepare_image_for_vision", new_callable=AsyncMock
            ) as mock_prepare,
            patch.object(processor, "_call_vision_api", new_callable=AsyncMock) as mock_vision,
        ):
            mock_prepare.return_value = fake_prepared
            mock_vision.side_effect = Exception("Vision API unavailable")

            result = await processor._process_image(attachment, "telegram", mock_adapter)

        assert result.processed is False
        assert "Vision API error" in result.processing_error


# ─────────────────────────────────────────────────────────────────────────────
# _process_document() Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestProcessDocument:
    """Tests for document text extraction."""

    @pytest.mark.asyncio
    async def test_txt_file_extraction(self, multimodal_config, mock_adapter):
        """TXT file: download bytes -> decode -> extracted_text."""
        processor = MediaProcessor(config=multimodal_config)
        mock_adapter.download_attachment = AsyncMock(return_value=b"Hello world")
        attachment = make_attachment(type="document", filename="notes.txt", mime_type="text/plain")

        result = await processor._process_document(attachment, "telegram", mock_adapter)

        assert result.processed is True
        assert result.extracted_text == "Hello world"
        assert result.page_count == 1
        assert result.processing_cost_usd == 0.0

    @pytest.mark.asyncio
    async def test_pdf_extraction(self, multimodal_config, mock_adapter):
        """PDF file: mock PdfReader extracts text from pages."""
        processor = MediaProcessor(config=multimodal_config)
        mock_adapter.download_attachment = AsyncMock(return_value=b"fake pdf content")
        attachment = make_attachment(
            type="document", filename="report.pdf", mime_type="application/pdf"
        )

        mock_page1 = MagicMock()
        mock_page1.extract_text.return_value = "Page 1 content"
        mock_page2 = MagicMock()
        mock_page2.extract_text.return_value = "Page 2 content"

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page1, mock_page2]

        # PyPDF2 may not be installed; inject a mock module into sys.modules
        mock_pypdf2 = MagicMock()
        mock_pypdf2.PdfReader = MagicMock(return_value=mock_reader)
        with patch.dict(sys.modules, {"PyPDF2": mock_pypdf2}):
            result = await processor._process_document(attachment, "telegram", mock_adapter)

        assert result.processed is True
        assert "Page 1 content" in result.extracted_text
        assert "Page 2 content" in result.extracted_text
        assert result.page_count == 2

    @pytest.mark.asyncio
    async def test_docx_extraction(self, multimodal_config, mock_adapter):
        """DOCX file: mock Document extracts paragraphs."""
        processor = MediaProcessor(config=multimodal_config)
        mock_adapter.download_attachment = AsyncMock(return_value=b"fake docx content")
        attachment = make_attachment(
            type="document",
            filename="doc.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        mock_para1 = MagicMock()
        mock_para1.text = "First paragraph"
        mock_para2 = MagicMock()
        mock_para2.text = "Second paragraph"
        mock_para_empty = MagicMock()
        mock_para_empty.text = "   "  # Should be filtered out

        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para1, mock_para2, mock_para_empty]

        # python-docx may not be installed; inject a mock module into sys.modules
        mock_docx = MagicMock()
        mock_docx.Document = MagicMock(return_value=mock_doc)
        with patch.dict(sys.modules, {"docx": mock_docx}):
            result = await processor._process_document(attachment, "telegram", mock_adapter)

        assert result.processed is True
        assert "First paragraph" in result.extracted_text
        assert "Second paragraph" in result.extracted_text

    @pytest.mark.asyncio
    async def test_unsupported_format_returns_error(self, multimodal_config, mock_adapter):
        """Unsupported document format (e.g. .xlsx) returns error."""
        processor = MediaProcessor(config=multimodal_config)
        attachment = make_attachment(
            type="document", filename="data.xlsx", mime_type="application/vnd.ms-excel"
        )

        result = await processor._process_document(attachment, "telegram", mock_adapter)

        assert result.processed is False
        assert "Unsupported format: xlsx" in result.processing_error

    @pytest.mark.asyncio
    async def test_long_text_truncated(self, multimodal_config, mock_adapter):
        """Text exceeding max_chars_per_doc is truncated."""
        processor = MediaProcessor(config=multimodal_config)
        long_text = "A" * 15000
        mock_adapter.download_attachment = AsyncMock(return_value=long_text.encode("utf-8"))
        attachment = make_attachment(type="document", filename="long.txt", mime_type="text/plain")

        result = await processor._process_document(attachment, "telegram", mock_adapter)

        assert result.processed is True
        # max_chars_per_doc is 10000 in config
        assert "[Truncated" in result.extracted_text
        # Content before truncation marker should be 10000 chars
        assert result.extracted_text.startswith("A" * 10000)


# ─────────────────────────────────────────────────────────────────────────────
# process_attachments_batch() Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestProcessAttachmentsBatch:
    """Tests for batch processing with ADHD limits."""

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self, multimodal_config, mock_adapter):
        """Empty attachments list returns empty result list."""
        processor = MediaProcessor(config=multimodal_config)

        result = await processor.process_attachments_batch([], "telegram", mock_adapter)

        assert result == []

    @pytest.mark.asyncio
    async def test_adhd_limit_enforced(self, multimodal_config, mock_adapter):
        """ADHD max_attachments (3) limits processing when 5 are passed."""
        processor = MediaProcessor(config=multimodal_config)
        attachments = [make_attachment(id=f"att-{i}") for i in range(5)]

        with patch.object(processor, "process_attachment", new_callable=AsyncMock) as mock_pa:
            mock_pa.return_value = MediaContent(
                attachment=attachments[0], processed=True, processing_cost_usd=0.01
            )
            result = await processor.process_attachments_batch(
                attachments, "telegram", mock_adapter
            )

        # Should only process max_attachments=3
        assert mock_pa.await_count == 3
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_images_prioritized_over_documents(self, multimodal_config, mock_adapter):
        """Images are sorted before documents for processing priority."""
        processor = MediaProcessor(config=multimodal_config)
        doc = make_attachment(id="doc-1", type="document", filename="report.pdf")
        img = make_attachment(id="img-1", type="image", filename="photo.jpg")

        processed_ids = []

        async def track_processing(attachment, channel, adapter):
            processed_ids.append(attachment.id)
            return MediaContent(attachment=attachment, processed=True, processing_cost_usd=0.01)

        with patch.object(processor, "process_attachment", side_effect=track_processing):
            await processor.process_attachments_batch([doc, img], "telegram", mock_adapter)

        # Image should be processed first
        assert processed_ids[0] == "img-1"
        assert processed_ids[1] == "doc-1"

    @pytest.mark.asyncio
    async def test_budget_enforcement_stops_processing(self, multimodal_config, mock_adapter):
        """Processing stops when budget is exceeded."""
        # Set a very low budget
        multimodal_config["processing"]["max_processing_cost_usd"] = 0.01
        processor = MediaProcessor(config=multimodal_config)
        attachments = [make_attachment(id=f"att-{i}") for i in range(3)]

        call_count = 0

        async def expensive_processing(attachment, channel, adapter):
            nonlocal call_count
            call_count += 1
            return MediaContent(
                attachment=attachment,
                processed=True,
                processing_cost_usd=0.02,  # Exceeds budget after first
            )

        with patch.object(processor, "process_attachment", side_effect=expensive_processing):
            result = await processor.process_attachments_batch(
                attachments, "telegram", mock_adapter
            )

        # First one processed normally, remaining exceed budget
        assert call_count == 1
        assert len(result) == 3
        # Budget-exceeded items have error
        assert result[1].processing_error == "Processing budget exceeded"
        assert result[2].processing_error == "Processing budget exceeded"

    @pytest.mark.asyncio
    async def test_all_results_returned_with_costs(self, multimodal_config, mock_adapter):
        """All results are returned with correct costs tracked."""
        processor = MediaProcessor(config=multimodal_config)
        attachments = [make_attachment(id=f"att-{i}") for i in range(2)]

        costs = [0.005, 0.010]

        async def mock_process(attachment, channel, adapter):
            idx = int(attachment.id.split("-")[1])
            return MediaContent(
                attachment=attachment,
                processed=True,
                processing_cost_usd=costs[idx],
            )

        with patch.object(processor, "process_attachment", side_effect=mock_process):
            result = await processor.process_attachments_batch(
                attachments, "telegram", mock_adapter
            )

        assert len(result) == 2
        assert result[0].processing_cost_usd == 0.005
        assert result[1].processing_cost_usd == 0.010
