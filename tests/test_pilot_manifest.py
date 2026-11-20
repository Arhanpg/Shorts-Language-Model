from datetime import datetime, timezone

from shorts_intelligence.pilot.manifest import _can_analyze
from shorts_intelligence.pilot.schemas import PilotRecord


def _record() -> PilotRecord:
    return PilotRecord.model_validate({
        "record_id": "clip_001",
        "platform": "creator_upload",
        "media_path": "clip.mp4",
        "rights": {
            "basis": "creator_owned",
            "evidence_ref": "owner-proof-1",
            "media_analysis": True,
            "temporary_processing": True,
            "derived_artifact_retention": True,
            "model_training": False,
        },
    })


def test_rights_gate_accepts_permitted_record() -> None:
    ok, reason = _can_analyze(_record(), datetime.now(timezone.utc))
    assert ok is True
    assert reason is None


def test_rights_gate_rejects_revoked_record() -> None:
    record = _record()
    record.rights.revoked = True
    ok, reason = _can_analyze(record, datetime.now(timezone.utc))
    assert ok is False
    assert reason == "rights_revoked"
