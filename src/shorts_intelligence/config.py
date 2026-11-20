"""Validated runtime configuration for the Phase 1 analyzer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnalyzerConfig:
    max_file_size_mb: int = 500
    max_duration_seconds: float = 180.0
    hook_window_seconds: float = 3.0
    hook_sample_interval_seconds: float = 0.25
    analysis_sample_interval_seconds: float = 0.25
    max_keyframes: int = 48
    max_ocr_frames: int = 12
    cut_threshold: float = 0.28
    motion_resize_width: int = 160
    keyframe_width: int = 640
    jpeg_quality: int = 88
    asr_model: str = "small"
    asr_device: str = "cpu"
    asr_compute_type: str = "int8"
    language: str | None = None
    enable_asr: bool = True
    enable_ocr: bool = True
    enable_audio_analysis: bool = True
    keep_artifacts: bool = False

    def __post_init__(self) -> None:
        if self.max_file_size_mb <= 0:
            raise ValueError("max_file_size_mb must be positive")
        if self.max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be positive")
        if not 4 <= self.max_keyframes <= 96:
            raise ValueError("max_keyframes must be between 4 and 96 to bound image memory")
        if self.max_ocr_frames < 1:
            raise ValueError("max_ocr_frames must be at least 1")
        if not 0.0 < self.cut_threshold <= 1.0:
            raise ValueError("cut_threshold must be in (0, 1]")
        if self.hook_sample_interval_seconds <= 0 or self.analysis_sample_interval_seconds <= 0:
            raise ValueError("frame sampling intervals must be positive")
        if self.motion_resize_width <= 0 or self.keyframe_width <= 0:
            raise ValueError("frame widths must be positive")
        if not 1 <= self.jpeg_quality <= 100:
            raise ValueError("jpeg_quality must be between 1 and 100")
        if self.asr_device not in {"cpu", "cuda", "auto"}:
            raise ValueError("asr_device must be cpu, cuda or auto")
