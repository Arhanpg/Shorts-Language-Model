"""Private candidate and pseudonymous selected-record schemas for Phase 2."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Platform = Literal[
    "youtube_shorts", "instagram_reels", "creator_upload",
    "licensed_dataset", "research_dataset", "other",
]
RightsBasis = Literal[
    "creator_owned", "creator_permission", "licensed_dataset", "approved_research",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class RightsScope(StrictModel):
    basis: RightsBasis
    evidence_ref: str = Field(min_length=3, max_length=200)
    media_analysis: bool = False
    temporary_processing: bool = False
    derived_artifact_retention: bool = False
    raw_media_retention: bool = False
    model_training: bool = False
    public_redistribution: bool = False
    expires_at: datetime | None = None
    revoked: bool = False

    @field_validator("expires_at")
    @classmethod
    def expiration_must_be_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("expires_at must include a timezone")
        return value


class PerformanceSnapshot(StrictModel):
    metric_name: str = Field(min_length=1, max_length=40)
    value: float = Field(ge=0)
    observed_at: datetime
    source: str = "creator_authorized_or_permitted_snapshot"

    @field_validator("observed_at")
    @classmethod
    def observed_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("observed_at must include a timezone")
        return value


class PilotRecord(StrictModel):
    """One row in the private candidate manifest. Never commit real manifests."""

    schema_version: str = "1.0.0"
    record_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$")
    platform: Platform
    media_path: str = Field(min_length=1)
    source_ref: str | None = None
    creator_id: str | None = None
    rights: RightsScope
    language: str = "unknown"
    topic: str = "unknown"
    speech_mode: Literal["speech", "music_only", "silent", "mixed", "unknown"] = "unknown"
    published_at: datetime | None = None
    performance: PerformanceSnapshot | None = None
    notes: str | None = None

    @field_validator("published_at")
    @classmethod
    def published_at_must_be_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("published_at must include a timezone")
        return value

    @field_validator("language", "topic")
    @classmethod
    def normalize_category(cls, value: str) -> str:
        normalized = " ".join(value.strip().lower().split())
        return normalized or "unknown"

    @model_validator(mode="after")
    def validate_rights_consistency(self) -> "PilotRecord":
        if self.rights.model_training and not (
            self.rights.media_analysis
            and self.rights.temporary_processing
            and self.rights.derived_artifact_retention
        ):
            raise ValueError(
                "model_training requires media_analysis, temporary_processing "
                "and derived_artifact_retention capabilities"
            )
        if self.performance and self.published_at:
            if self.performance.observed_at < self.published_at:
                raise ValueError("performance observed_at cannot precede published_at")
        return self


class SelectedRecord(StrictModel):
    """Local selected manifest; creator/source identifiers are pseudonymized."""

    schema_version: str = "1.0.0"
    record_id: str
    platform: Platform
    media_path: str
    media_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    file_size_bytes: int = Field(ge=1)
    creator_group: str | None = None
    rights_basis: RightsBasis
    rights_reference_hash: str
    rights_expires_at: datetime | None = None
    media_analysis_permitted: bool
    temporary_processing_permitted: bool
    derived_artifact_retention_permitted: bool
    model_training_permitted: bool
    language: str
    topic: str
    speech_mode: str
    published_at: datetime | None = None
    duration_seconds: float = Field(gt=0)
    duration_band: str
    age_band: str
    metric_name: str | None = None
    metric_value: float | None = Field(default=None, ge=0)
    observed_at: datetime | None = None
    creator_relative_log_score: float | None = None
    creator_relative_multiple: float | None = Field(default=None, gt=0)
    performance_tier: str = "unscored"


class MatchPair(StrictModel):
    pair_id: str
    positive_record_id: str
    control_record_id: str
    creator_group: str
    platform: Platform
    language: str
    topic: str
    positive_relative_multiple: float
    control_relative_multiple: float
    publication_gap_days: int
    duration_gap_fraction: float
    matching_rule: str = (
        "same creator/platform/language/topic; publication gap <= 60d; duration gap <= 30%"
    )


class ValidationIssue(StrictModel):
    row_number: int
    record_id: str | None = None
    code: str
    message: str


class ValidationSummary(StrictModel):
    schema_version: str = "1.0.0"
    manifest_path: str
    input_rows: int
    parsed_rows: int
    accepted_rows: int
    rejected_rows: int
    duplicate_media_rows: int
    training_permitted_rows: int
    warnings: list[str] = Field(default_factory=list)
    issues: list[ValidationIssue] = Field(default_factory=list)
    platform_counts: dict[str, int] = Field(default_factory=dict)
    language_counts: dict[str, int] = Field(default_factory=dict)
    topic_counts: dict[str, int] = Field(default_factory=dict)
