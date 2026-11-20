"""Bounded, temporary audio extraction using FFmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path

from shorts_intelligence.media.probe import MediaError, require_binary


def extract_audio_wav(
    video_path: Path, destination: Path, timeout_seconds: int = 240
) -> Path | None:
    """Extract first audio stream to 16 kHz mono PCM WAV; return None if absent."""
    ffmpeg = require_binary("ffmpeg")
    command = [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video_path), "-map", "0:a:0?", "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", str(destination),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout_seconds
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaError("FFmpeg audio extraction timed out.") from exc
    if result.returncode != 0:
        error = (result.stderr or "").lower()
        if "matches no streams" in error or "does not contain any stream" in error:
            return None
        raise MediaError(
            f"FFmpeg audio extraction failed: {(result.stderr or '').strip()[-1000:]}"
        )
    if not destination.exists() or destination.stat().st_size < 44:
        return None
    return destination
