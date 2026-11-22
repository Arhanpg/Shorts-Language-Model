"""Versioned, validated output schemas for short-video telemetry."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RightsBasis = Literal[
    "creator_owned",
    "creator_permission",
    "licensed_dataset",
    "approved_research",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class RightsDeclaration(StrictModel):
    basis: RightsBasis
    reference: str | None = None
    media_analysis_permitted: bool = True
    model_training_permitted: bool = False
    note: str = "User-declared basis; retain evidence of permission outside this report."


class VideoMetadata(StrictModel):
    file_name: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    file_size_bytes: int = Field(ge=1)
    duration_seconds: float = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(ge=0)
    frame_count: int = Field(ge=0)
    video_codec: str | None = None
    audio_present: bool = False
    audio_codec: str | None = None
    aspect_ratio: str


class FrameEvidence(StrictModel):
    timestamp_seconds: float = Field(ge=0)
    frame_index: int = Field(ge=0)
    reason: list[str] = Field(default_factory=list)
    motion_score: float = Field(ge=0)
    image_path: str | None = None


class CutCandidate(StrictModel):
    timestamp_seconds: float = Field(ge=0)
    visual_difference: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    detector: str = "opencv-histogram-difference"
    note: str = "Candidate boundary; not a human-verified edit label."


class MotionSample(StrictModel):
    timestamp_seconds: float = Field(ge=0)
    mean_flow_magnitude: float = Field(ge=0)


class MotionSummary(StrictModel):
    sample_count: int = Field(ge=0)
    mean_flow_magnitude: float = Field(ge=0)
    p95_flow_magnitude: float = Field(ge=0)
    peak_timestamp_seconds: float | None = Field(default=None, ge=0)
    samples: list[MotionSample] = Field(default_factory=list)
    method: str = "opencv-farneback-on-sampled-frames"


class TranscriptSegment(StrictModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    text: str = Field(min_length=1)
    language: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    words: list[dict[str, object]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_interval(self) -> TranscriptSegment:
        if self.end_seconds < self.start_seconds:
            raise ValueError("transcript end_seconds must be >= start_seconds")
        return self


class OCRSpan(StrictModel):
    timestamp_seconds: float = Field(ge=0)
    text: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    bbox_xyxy: list[int] | None = None
    engine: str
    frame_index: int = Field(ge=0)


class AudioFeatures(StrictModel):
    analyzed: bool = False
    duration_seconds: float | None = Field(default=None, ge=0)
    sample_rate: int | None = Field(default=None, gt=0)
    rms_mean: float | None = Field(default=None, ge=0)
    silence_ratio: float | None = Field(default=None, ge=0, le=1)
    estimated_tempo_bpm: float | None = Field(default=None, ge=0)
    beat_times_seconds: list[float] = Field(default_factory=list)
    onset_times_seconds: list[float] = Field(default_factory=list)
    method: str | None = None
    warning: str | None = None


class StageStatus(StrictModel):
    status: Literal["complete", "partial", "skipped", "failed"]
    engine: str | None = None
    detail: str | None = None


class HookWindow(StrictModel):
    start_seconds: float = 0.0
    end_seconds: float = Field(gt=0)
    frame_count: int = Field(ge=0)
    cut_candidate_count: int = Field(ge=0)
    mean_motion_score: float = Field(ge=0)
    note: str = "Descriptive signals only; hook quality is not inferred in Phase 1."


class AnalysisReport(StrictModel):
    schema_version: str = "1.0.0"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    project: str = "Shorts Language Model"
    phase: str = "phase-1-single-video-telemetry"
    source_type: Literal["local_file"] = "local_file"
    rights: RightsDeclaration | None = None
    video: VideoMetadata
    hook_window: HookWindow
    frame_evidence: list[FrameEvidence] = Field(default_factory=list)
    cut_candidates: list[CutCandidate] = Field(default_factory=list)
    motion: MotionSummary
    transcript_segments: list[TranscriptSegment] = Field(default_factory=list)
    ocr_spans: list[OCRSpan] = Field(default_factory=list)
    audio: AudioFeatures = Field(default_factory=AudioFeatures)
    stages: dict[str, StageStatus]
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=lambda: [
        "Phase 1 extracts evidence; it does not yet run a fine-tuned VLM.",
        "Cut, motion and beat events are algorithmic candidates, not ground truth.",
        "This report does not predict views or establish causal virality drivers.",
    ])

    @model_validator(mode="after")
    def validate_timestamps_within_video(self) -> AnalysisReport:
        duration = self.video.duration_seconds
        timestamps: list[float] = [
            item.timestamp_seconds for item in self.frame_evidence
        ]
        timestamps.extend(item.timestamp_seconds for item in self.cut_candidates)
        timestamps.extend(item.timestamp_seconds for item in self.motion.samples)
        timestamps.extend(item.timestamp_seconds for item in self.ocr_spans)
        timestamps.extend(item.start_seconds for item in self.transcript_segments)
        timestamps.extend(item.end_seconds for item in self.transcript_segments)
        timestamps.extend(self.audio.beat_times_seconds)
        timestamps.extend(self.audio.onset_times_seconds)
        if self.motion.peak_timestamp_seconds is not None:
            timestamps.append(self.motion.peak_timestamp_seconds)
        if any(value > duration + 0.05 for value in timestamps):
            raise ValueError("one or more evidence timestamps exceed video duration")
        return self
