"""Safe local media validation and ffprobe metadata extraction."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

from shorts_intelligence.config import AnalyzerConfig
from shorts_intelligence.schemas import VideoMetadata


class MediaError(RuntimeError):
    """Raised when an input cannot be safely analyzed."""


def require_binary(name: str) -> str:
    binary = shutil.which(name)
    if not binary:
        raise MediaError(
            f"Required executable '{name}' was not found on PATH. "
            "Install FFmpeg (it includes ffprobe) and reopen your terminal."
        )
    return binary


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_rate(value: str | None) -> float:
    if not value or value in {"0/0", "N/A"}:
        return 0.0
    try:
        numerator, denominator = value.split("/", 1)
        denom = float(denominator)
        return float(numerator) / denom if denom else 0.0
    except (ValueError, ZeroDivisionError):
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0


def validate_input(path: Path, config: AnalyzerConfig) -> Path:
    path = path.expanduser().resolve(strict=True)
    if not path.is_file():
        raise MediaError(f"Input must be a single local file, not a directory: {path}")
    allowed = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
    if path.suffix.lower() not in allowed:
        raise MediaError(
            f"Unsupported extension '{path.suffix}'. Supported: {', '.join(sorted(allowed))}"
        )
    size = path.stat().st_size
    if size <= 0:
        raise MediaError("Input file is empty.")
    limit = config.max_file_size_mb * 1024 * 1024
    if size > limit:
        raise MediaError(
            f"Input is {size / 1024 / 1024:.1f} MB; "
            f"configured limit is {config.max_file_size_mb} MB."
        )
    return path


def probe_video(path: Path, config: AnalyzerConfig) -> VideoMetadata:
    ffprobe = require_binary("ffprobe")
    command = [
        ffprobe, "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,nb_frames,duration",
        "-of", "json", str(path),
    ]
    try:
        result = subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaError("ffprobe timed out while reading this file.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "unknown ffprobe error").strip()[-1000:]
        raise MediaError(f"ffprobe could not read the input: {detail}") from exc
    try:
        payload: dict[str, Any] = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaError("ffprobe returned invalid JSON metadata.") from exc

    streams = payload.get("streams", [])
    video_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "video"), None
    )
    audio_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"), None
    )
    if not video_stream:
        raise MediaError("No video stream was found in this file.")

    duration = float(
        video_stream.get("duration")
        or payload.get("format", {}).get("duration")
        or 0
    )
    if duration <= 0:
        raise MediaError("Could not determine a positive video duration.")
    if duration > config.max_duration_seconds:
        raise MediaError(
            f"Video duration is {duration:.1f}s; "
            f"Phase 1 limit is {config.max_duration_seconds:.0f}s. "
            "Raise --max-duration only after checking the resource budget."
        )

    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    if not width or not height:
        raise MediaError("Video width/height metadata is missing.")
    fps = _parse_rate(
        video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate")
    )
    try:
        frame_count = int(
            video_stream.get("nb_frames") or round(duration * fps)
        )
    except (ValueError, TypeError):
        frame_count = max(0, round(duration * fps))
    ratio_gcd = math.gcd(width, height)
    ratio = f"{width // ratio_gcd}:{height // ratio_gcd}"

    return VideoMetadata(
        file_name=path.name,
        sha256=sha256_file(path),
        file_size_bytes=path.stat().st_size,
        duration_seconds=duration,
        width=width,
        height=height,
        fps=max(0.0, fps),
        frame_count=max(0, frame_count),
        video_codec=video_stream.get("codec_name"),
        audio_present=audio_stream is not None,
        audio_codec=audio_stream.get("codec_name") if audio_stream else None,
        aspect_ratio=ratio,
    )
