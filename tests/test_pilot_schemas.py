from datetime import datetime

import pytest
from pydantic import ValidationError

from shorts_intelligence.pilot.schemas import PilotRecord, RightsScope


def _record(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "record_id": "clip_0001",
        "platform": "creator_upload",
        "media_path": "clip.mp4",
        "creator_id": "private-creator",
        "rights": {
            "basis": "creator_permission",
            "evidence_ref": "consent-2026-001",
            "media_analysis": True,
            "temporary_processing": True,
            "derived_artifact_retention": True,
            "model_training": False,
        },
    }
    payload.update(updates)
    return payload


def test_training_permission_defaults_false() -> None:
    record = PilotRecord.model_validate(_record())
    assert record.rights.model_training is False


def test_training_requires_processing_and_retention_capabilities() -> None:
    payload = _record()
    payload["rights"] = {
        "basis": "creator_permission", "evidence_ref": "consent-001",
        "media_analysis": True, "temporary_processing": False,
        "derived_artifact_retention": True, "model_training": True,
    }
    with pytest.raises(ValidationError, match="model_training requires"):
        PilotRecord.model_validate(payload)


def test_expiration_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        RightsScope(
            basis="creator_owned", evidence_ref="owner-001",
            expires_at=datetime(2026, 11, 20),
        )


def test_language_topic_normalize() -> None:
    record = PilotRecord.model_validate(
        _record(language=" HI ", topic=" Cricket  Edit ")
    )
    assert record.language == "hi"
    assert record.topic == "cricket edit"

def test_performance_snapshot_cannot_precede_publication() -> None:
    payload = _record(
        published_at="2026-10-01T12:00:00+00:00",
        performance={
            "metric_name": "views",
            "value": 1000,
            "observed_at": "2026-09-30T12:00:00+00:00",
        },
    )
    with pytest.raises(ValidationError, match="cannot precede published_at"):
        PilotRecord.model_validate(payload)
