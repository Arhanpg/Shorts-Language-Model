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
        """Return a discovery metric, keeping estimated UI counts in metadata."""
        if self.platform == "youtube":
            return self.view_count
        exact_metric = (
            self.play_count if self.play_count is not None else self.view_count
        )
        if exact_metric is not None:
            return exact_metric
        if self.metadata.get("metric_is_estimate") is True:
            estimate = self.metadata.get("metric_conservative_lower_bound")
            if isinstance(estimate, int) and not isinstance(estimate, bool) and estimate >= 0:
                return estimate
        return None

    def qualifying_metric_kind(self) -> str:
        """Return the platform-native label without relabeling estimated values."""
        if self.platform == "youtube":
            return "views"
        if self.play_count is not None:
            return "plays"
        if self.view_count is not None:
            return "views"
        kind = self.metadata.get("metric_kind")
        return str(kind) if kind in {"plays", "views"} else "views"
