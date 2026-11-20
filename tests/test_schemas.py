from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from shorts_intelligence.schemas import AnalysisReport, RightsDeclaration


def _report(**overrides: object) -> AnalysisReport:
    payload: dict[str, object] = {
        "generated_at": datetime.now(UTC),
        "rights": {"basis": "creator_owned"},
        "video": {
            "file_name": "clip.mp4",
            "sha256": "a" * 64,
            "file_size_bytes": 100,
            "duration_seconds": 10.0,
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "frame_count": 300,
            "aspect_ratio": "9:16",
        },
        "hook_window": {
            "end_seconds": 3.0,
            "frame_count": 8,
            "cut_candidate_count": 2,
            "mean_motion_score": 1.2,
        },
        "motion": {
            "sample_count": 0,
            "mean_flow_magnitude": 0.0,
            "p95_flow_magnitude": 0.0,
        },
        "stages": {
            "media_validation": {"status": "complete", "engine": "ffprobe"}
        },
    }
    payload.update(overrides)
    return AnalysisReport(**payload)


def test_rights_training_permission_defaults_false() -> None:
    rights = RightsDeclaration(basis="creator_owned")
    assert rights.model_training_permitted is False


def test_report_accepts_valid_payload() -> None:
    report = _report()
    assert report.video.duration_seconds == 10.0


def test_report_rejects_timestamp_after_duration() -> None:
    with pytest.raises(ValidationError, match="timestamps exceed video duration"):
        _report(
            cut_candidates=[
                {
                    "timestamp_seconds": 10.5,
                    "visual_difference": 0.4,
                    "confidence": 0.4,
                }
            ]
        )


def test_report_rejects_extra_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        _report(unreviewed_prediction="viral")
