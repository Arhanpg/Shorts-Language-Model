from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from shorts_intelligence.analyzer import analyze_video
from shorts_intelligence.config import AnalyzerConfig


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="FFmpeg and ffprobe are required for integration smoke tests",
)
def test_silent_clip_generates_valid_report(tmp_path: Path) -> None:
    clip = tmp_path / "silent.mp4"
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=360x640:rate=24:duration=4",
            "-an", "-c:v", "mpeg4", "-pix_fmt", "yuv420p", str(clip),
        ],
        check=True,
        capture_output=True,
    )
    output = tmp_path / "report.json"
    report = analyze_video(
        clip,
        output,
        rights_basis="creator_owned",
        config=AnalyzerConfig(
            max_duration_seconds=10,
            enable_asr=False,
            enable_ocr=False,
            enable_audio_analysis=False,
        ),
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert report.video.duration_seconds == pytest.approx(4.0, abs=0.2)
    assert payload["video"]["audio_present"] is False
    assert payload["stages"]["asr"]["status"] == "skipped"
    assert payload["stages"]["ocr"]["status"] == "skipped"
    assert len(payload["frame_evidence"]) <= 48


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="FFmpeg and ffprobe are required for integration smoke tests",
)
def test_sampling_does_not_retain_more_than_configured_keyframes(tmp_path: Path) -> None:
    clip = tmp_path / "longer.mp4"
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=360x640:rate=24:duration=12",
            "-an", "-c:v", "mpeg4", "-pix_fmt", "yuv420p", str(clip),
        ],
        check=True,
        capture_output=True,
    )
    from shorts_intelligence.media.probe import probe_video
    from shorts_intelligence.media.sampling import sample_video

    config = AnalyzerConfig(max_keyframes=12, max_duration_seconds=20)
    metadata = probe_video(clip, config)
    result = sample_video(clip, metadata.duration_seconds, config)
    assert len(result.frames) <= 12
    assert result.hook_frame_count > 0
    assert result.motion_samples
