import json
from pathlib import Path

import pytest

from shorts_intelligence.pilot.runner import load_selected_manifest


def test_selected_manifest_rejects_duplicate_record_ids(tmp_path: Path) -> None:
    path = tmp_path / "selected.jsonl"
    row = {
        "record_id": "same", "platform": "creator_upload",
        "media_path": "/tmp/video.mp4", "media_sha256": "a" * 64,
        "file_size_bytes": 10, "rights_basis": "creator_owned",
        "rights_reference_hash": "b" * 64,
        "media_analysis_permitted": True,
        "temporary_processing_permitted": True,
        "derived_artifact_retention_permitted": True,
        "model_training_permitted": False,
        "language": "en", "topic": "sports", "speech_mode": "silent",
        "duration_seconds": 10, "duration_band": "00-15s", "age_band": "unknown",
    }
    path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate record_id"):
        load_selected_manifest(path)
