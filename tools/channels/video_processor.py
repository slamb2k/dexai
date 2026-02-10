"""
Video Processor for Multi-Modal Messaging (Phase 15b)

Handles video processing:
- Frame extraction for visual analysis
- Audio track extraction and transcription
- Duration limits and cost controls
- Thumbnail generation

Usage:
    from tools.channels.video_processor import VideoProcessor

    processor = VideoProcessor()
    result = await processor.process_video(video_bytes, filename, adapter)
"""

from __future__ import annotations

import logging
import subprocess

# Ensure project root is in path
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


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


@dataclass
class VideoProcessingResult:
    """Result from video processing."""
    success: bool

    # Audio transcription
    transcription: str | None = None
    audio_language: str | None = None

    # Frame analysis
    frame_descriptions: list[str] = field(default_factory=list)
    thumbnail_bytes: bytes | None = None

    # Metadata
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None

    # Cost tracking
    transcription_cost_usd: float = 0.0
    vision_cost_usd: float = 0.0

    @property
    def total_cost_usd(self) -> float:
        return self.transcription_cost_usd + self.vision_cost_usd

    # Error handling
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "success": self.success,
            "transcription": self.transcription,
            "audio_language": self.audio_language,
            "frame_descriptions": self.frame_descriptions,
            "has_thumbnail": self.thumbnail_bytes is not None,
            "duration_seconds": self.duration_seconds,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "transcription_cost_usd": self.transcription_cost_usd,
            "vision_cost_usd": self.vision_cost_usd,
            "total_cost_usd": self.total_cost_usd,
            "error": self.error,
        }


class VideoProcessor:
    """
    Process video content for AI context.

    Handles:
    - Frame extraction at key points
    - Audio track extraction and transcription
    - Duration and size limits
    - Thumbnail generation
    - Cost tracking
    """

    # Supported video formats
    SUPPORTED_FORMATS = {
        "mp4", "webm", "avi", "mov", "mkv", "m4v", "3gp", "mpeg", "mpg"
    }

    # MIME type to extension mapping
    MIME_TO_EXT = {
        "video/mp4": "mp4",
        "video/webm": "webm",
        "video/x-msvideo": "avi",
        "video/quicktime": "mov",
        "video/x-matroska": "mkv",
        "video/3gpp": "3gp",
        "video/mpeg": "mpeg",
    }

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize video processor.

        Args:
            config: Optional config override (defaults to args/multimodal.yaml)
        """
        self.config = config or load_config()
        self._temp_dir = Path(tempfile.mkdtemp(prefix="dexai_video_"))
        self._ffmpeg_available = self._check_ffmpeg()

    def _check_ffmpeg(self) -> bool:
        """Check if FFmpeg is available."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    async def process_video(
        self,
        video_bytes: bytes,
        filename: str = "video.mp4",
        mime_type: str = "video/mp4",
    ) -> VideoProcessingResult:
        """
        Process video for AI context.

        Extracts frames and audio, transcribes audio track.

        Args:
            video_bytes: Raw video data
            filename: Original filename
            mime_type: MIME type of video

        Returns:
            VideoProcessingResult with transcription and frame descriptions
        """
        video_config = self.config.get("processing", {}).get("video", {})

        if not video_config.get("enabled", True):
            return VideoProcessingResult(
                success=False,
                error="Video processing disabled in configuration",
            )

        # Check file size limit
        max_size_mb = video_config.get("max_file_size_mb", 100)
        if len(video_bytes) > max_size_mb * 1024 * 1024:
            return VideoProcessingResult(
                success=False,
                error=f"Video too large (>{max_size_mb}MB)",
            )

        # Check FFmpeg availability
        if not self._ffmpeg_available:
            return VideoProcessingResult(
                success=False,
                error="FFmpeg not available for video processing",
            )

        try:
            # Save video to temp file
            ext = self._get_extension(filename, mime_type)
            video_path = self._temp_dir / f"{uuid.uuid4()}.{ext}"
            video_path.write_bytes(video_bytes)

            # Get video metadata
            metadata = await self._get_video_metadata(video_path)
            if not metadata:
                return VideoProcessingResult(
                    success=False,
                    error="Failed to read video metadata",
                )

            # Check duration limit
            max_duration = video_config.get("max_duration_seconds", 300)
            if metadata.get("duration", 0) > max_duration:
                return VideoProcessingResult(
                    success=False,
                    error=f"Video too long ({metadata['duration']:.0f}s > {max_duration}s limit)",
                    duration_seconds=metadata.get("duration"),
                )

            result = VideoProcessingResult(
                success=True,
                duration_seconds=metadata.get("duration"),
                width=metadata.get("width"),
                height=metadata.get("height"),
                fps=metadata.get("fps"),
            )

            # Extract and transcribe audio
            if video_config.get("transcribe_audio", True):
                audio_result = await self._extract_and_transcribe_audio(
                    video_path, video_config
                )
                if audio_result:
                    result.transcription = audio_result.get("text")
                    result.audio_language = audio_result.get("language")
                    result.transcription_cost_usd = audio_result.get("cost", 0.0)

            # Extract key frames
            if video_config.get("extract_frames", True):
                frame_result = await self._extract_and_analyze_frames(
                    video_path, metadata, video_config
                )
                if frame_result:
                    result.frame_descriptions = frame_result.get("descriptions", [])
                    result.thumbnail_bytes = frame_result.get("thumbnail")
                    result.vision_cost_usd = frame_result.get("cost", 0.0)

            # Cleanup temp video file
            try:
                video_path.unlink()
            except Exception:
                pass

            return result

        except Exception as e:
            logger.error(f"Video processing failed: {e}")
            return VideoProcessingResult(
                success=False,
                error=f"Video processing failed: {str(e)[:100]}",
            )

    async def _get_video_metadata(self, video_path: Path) -> dict[str, Any] | None:
        """
        Get video metadata using FFprobe.

        Args:
            video_path: Path to video file

        Returns:
            Dict with duration, width, height, fps or None on error
        """
        try:
            import json as json_module

            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(video_path),
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=30,
            )

            if result.returncode != 0:
                return None

            data = json_module.loads(result.stdout)

            # Find video stream
            video_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    video_stream = stream
                    break

            if not video_stream:
                return None

            # Extract metadata
            duration = float(data.get("format", {}).get("duration", 0))

            # Parse frame rate (can be "24/1" or "23.976")
            fps_str = video_stream.get("r_frame_rate", "0/1")
            if "/" in fps_str:
                num, den = fps_str.split("/")
                fps = float(num) / float(den) if float(den) > 0 else 0
            else:
                fps = float(fps_str)

            return {
                "duration": duration,
                "width": video_stream.get("width"),
                "height": video_stream.get("height"),
                "fps": fps,
            }

        except Exception as e:
            logger.error(f"Failed to get video metadata: {e}")
            return None

    async def _extract_and_transcribe_audio(
        self,
        video_path: Path,
        config: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Extract audio track and transcribe using Whisper.

        Args:
            video_path: Path to video file
            config: Video processing config

        Returns:
            Dict with text, language, cost or None on error
        """
        try:
            # Extract audio to temp file
            audio_path = self._temp_dir / f"{uuid.uuid4()}.mp3"

            cmd = [
                "ffmpeg",
                "-i", str(video_path),
                "-vn",  # No video
                "-acodec", "libmp3lame",
                "-ar", "16000",  # 16kHz for Whisper
                "-ac", "1",  # Mono
                "-q:a", "4",  # Quality
                str(audio_path),
                "-y",  # Overwrite
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=60,
            )

            if result.returncode != 0 or not audio_path.exists():
                logger.warning(f"Audio extraction failed: {result.stderr[:200]}")
                return None

            # Check if audio was actually extracted (not silent)
            if audio_path.stat().st_size < 1000:  # Less than 1KB = likely no audio
                audio_path.unlink()
                return None

            # Transcribe using AudioProcessor
            from tools.channels.audio_processor import get_audio_processor

            processor = get_audio_processor()
            audio_bytes = audio_path.read_bytes()

            transcription = await processor.transcribe(
                audio_bytes,
                "audio.mp3",
                "audio/mpeg",
            )

            # Cleanup
            audio_path.unlink()

            if transcription.success:
                return {
                    "text": transcription.text,
                    "language": transcription.language,
                    "cost": transcription.cost_usd,
                }
            else:
                return None

        except Exception as e:
            logger.error(f"Audio extraction/transcription failed: {e}")
            return None

    async def _extract_and_analyze_frames(
        self,
        video_path: Path,
        metadata: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Extract key frames and analyze with Vision API.

        Args:
            video_path: Path to video file
            metadata: Video metadata
            config: Video processing config

        Returns:
            Dict with descriptions, thumbnail, cost or None on error
        """
        try:
            duration = metadata.get("duration", 0)
            max_frames = config.get("max_frames", 3)

            # Calculate frame extraction points (start, middle, end)
            if duration <= 5:
                # Short video: just get one frame from middle
                timestamps = [duration / 2]
            elif duration <= 30:
                # Medium video: start, middle, end
                timestamps = [1, duration / 2, duration - 1]
            else:
                # Long video: sample evenly
                step = duration / (max_frames + 1)
                timestamps = [step * (i + 1) for i in range(max_frames)]

            # Extract frames
            frames = []
            for i, ts in enumerate(timestamps[:max_frames]):
                frame_path = self._temp_dir / f"frame_{i}.jpg"

                cmd = [
                    "ffmpeg",
                    "-ss", str(ts),
                    "-i", str(video_path),
                    "-vframes", "1",
                    "-q:v", "2",  # High quality JPEG
                    str(frame_path),
                    "-y",
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=30,
                )

                if result.returncode == 0 and frame_path.exists():
                    frames.append({
                        "path": frame_path,
                        "timestamp": ts,
                    })

            if not frames:
                return None

            # Use first frame as thumbnail
            thumbnail_bytes = frames[0]["path"].read_bytes()

            # Analyze frames with Vision API
            descriptions = []
            total_vision_cost = 0.0

            if config.get("analyze_frames", True):
                from tools.channels.media_processor import MediaProcessor

                processor = MediaProcessor(self.config)

                for frame in frames:
                    frame_bytes = frame["path"].read_bytes()

                    # Prepare for vision
                    prepared = await processor._prepare_image_for_vision(frame_bytes)
                    if prepared:
                        try:
                            desc, cost = await processor._call_vision_api(prepared)
                            descriptions.append(f"[{frame['timestamp']:.1f}s] {desc}")
                            total_vision_cost += cost
                        except Exception as e:
                            logger.warning(f"Frame analysis failed: {e}")

            # Cleanup frame files
            for frame in frames:
                try:
                    frame["path"].unlink()
                except Exception:
                    pass

            return {
                "descriptions": descriptions,
                "thumbnail": thumbnail_bytes,
                "cost": total_vision_cost,
            }

        except Exception as e:
            logger.error(f"Frame extraction/analysis failed: {e}")
            return None

    def _get_extension(self, filename: str, mime_type: str) -> str:
        """Get file extension from filename or MIME type."""
        ext = Path(filename).suffix.lower().lstrip(".")
        if ext in self.SUPPORTED_FORMATS:
            return ext

        return self.MIME_TO_EXT.get(mime_type, "mp4")

    def cleanup(self) -> None:
        """Remove temporary files."""
        import shutil

        try:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        except Exception:
            pass


# =============================================================================
# Module-Level Instance
# =============================================================================

_processor_instance: VideoProcessor | None = None


def get_video_processor() -> VideoProcessor:
    """Get or create the global VideoProcessor instance."""
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = VideoProcessor()
    return _processor_instance


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    """CLI for testing video processor."""
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Video Processor Test")
    parser.add_argument("--config", action="store_true", help="Show config")
    parser.add_argument("--process", metavar="FILE", help="Process video file")
    parser.add_argument("--check-ffmpeg", action="store_true", help="Check FFmpeg availability")

    args = parser.parse_args()

    if args.config:
        import json
        config = load_config()
        print(json.dumps(config.get("processing", {}).get("video", {}), indent=2))

    elif args.check_ffmpeg:
        processor = VideoProcessor()
        if processor._ffmpeg_available:
            print("✓ FFmpeg is available")
        else:
            print("✗ FFmpeg is NOT available")
            print("Install with: apt install ffmpeg (Linux) or brew install ffmpeg (macOS)")

    elif args.process:
        async def run_process():
            processor = VideoProcessor()
            file_path = Path(args.process)
            if not file_path.exists():
                print(f"File not found: {file_path}")
                return

            video_bytes = file_path.read_bytes()
            result = await processor.process_video(
                video_bytes,
                file_path.name,
                f"video/{file_path.suffix.lstrip('.')}"
            )

            print(f"Success: {result.success}")
            if result.success:
                print(f"Duration: {result.duration_seconds:.1f}s")
                print(f"Resolution: {result.width}x{result.height}")
                print(f"FPS: {result.fps:.1f}")
                if result.transcription:
                    print(f"\nTranscription:\n{result.transcription[:500]}")
                if result.frame_descriptions:
                    print("\nFrame descriptions:")
                    for desc in result.frame_descriptions:
                        print(f"  {desc[:100]}...")
                print(f"\nTotal cost: ${result.total_cost_usd:.4f}")
            else:
                print(f"Error: {result.error}")

        asyncio.run(run_process())

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
