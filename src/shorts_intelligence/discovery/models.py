"""Typed records for search-discovered public short-form video candidates."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

Platform = Literal["youtube", "instagram"]
FormatStatus = Literal["confirmed", "candidate", "unknown", "not_short"]
CandidateStatus = Literal[
    "eligible", "below_threshold", "metric_unknown", "format_unknown",
    "not_short", "downloaded", "download_failed",
]


class DiscoveredCandidate(BaseModel):
    """A discovery result; it is not automatically a training-authorized asset."""

    model_config = ConfigDict(extra="forbid")

    platform: Platform
    source_id: str = Field(min_length=2, max_length=160)
    canonical_url: HttpUrl
    title: str | None = None
    description: str | None = None
    creator: str | None = None
    view_count: int | None = Field(default=None, ge=0)
    # Instagram may expose a distinct play_count; never silently relabel it as views.
    play_count: int | None = Field(default=None, ge=0)
    metric_source: str | None = None
    duration_seconds: float | None = Field(default=None, gt=0)
    upload_date: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    short_format_status: FormatStatus = "unknown"
    status: CandidateStatus = "metric_unknown"
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, object] = Field(default_factory=dict)

    def qualifying_metric(self) -> int | None:
        """Return the platform-native metric without conflating views and plays."""
        if self.platform == "youtube":
            return self.view_count
        return self.play_count if self.play_count is not None else self.view_count

    def qualifying_metric_kind(self) -> str:
        """Return the explicit metric label used for this platform."""
        if self.platform == "youtube":
            return "views"
        return "plays" if self.play_count is not None else "views"


class AcquisitionAuthorization(BaseModel):
    """Per-item rights attestation loaded from a private JSONL file."""

    model_config = ConfigDict(extra="forbid")

    platform: Platform
    source_id: str = Field(min_length=2, max_length=160)
    basis: Literal["creator_owned", "creator_permission", "licensed_dataset", "approved_research"]
    evidence_ref: str = Field(min_length=3, max_length=200)
    media_retrieval: bool = False
    media_analysis: bool = False
    temporary_processing: bool = False
    derived_artifact_retention: bool = False
    model_training: bool = False
    revoked: bool = False
    expires_at: datetime | None = None

    def validate_for_training(self, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        if self.revoked:
            raise ValueError("permission has been revoked")
        if self.expires_at is not None:
            if self.expires_at.tzinfo is None:
                raise ValueError("expires_at must include a timezone")
            if self.expires_at <= now:
                raise ValueError("permission has expired")
        required = {
            "media_retrieval": self.media_retrieval,
            "media_analysis": self.media_analysis,
            "temporary_processing": self.temporary_processing,
            "derived_artifact_retention": self.derived_artifact_retention,
            "model_training": self.model_training,
        }
        missing = [name for name, allowed in required.items() if not allowed]
        if missing:
            raise ValueError("permission does not grant: " + ", ".join(missing))
