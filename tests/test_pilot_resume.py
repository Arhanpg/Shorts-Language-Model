import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from shorts_intelligence.config import AnalyzerConfig
from shorts_intelligence.pilot.runner import _config_fingerprint, process_selected
from shorts_intelligence.pilot.schemas import SelectedRecord


def _selected_record(media: Path) -> SelectedRecord:
    digest = hashlib.sha256(media.read_bytes()).hexdigest()
    return SelectedRecord(
        record_id="clip_resume_01",
        platform="creator_upload",
        media_path=str(media.resolve()),
        media_sha256=digest,
        file_size_bytes=media.stat().st_size,
        creator_group="creator-hmac",
        rights_basis="creator_owned",
        rights_reference_hash="b" * 64,
        rights_expires_at=None,
        media_analysis_permitted=True,
        temporary_processing_permitted=True,
        derived_artifact_retention_permitted=True,
        model_training_permitted=False,
        language="en",
        topic="sports",
        speech_mode="silent",
        published_at=datetime(2026, 10, 1, tzinfo=UTC),
        duration_seconds=8,
        duration_band="00-15s",
        age_band="31-90d",
    )


def test_completed_record_resumes_only_for_matching_input_and_config(tmp_path: Path) -> None:
    media = tmp_path / "owned_clip.mp4"
    media.write_bytes(b"test fixture video bytes")
    record = _selected_record(media)
    manifest = tmp_path / "selected_manifest.jsonl"
    manifest.write_text(record.model_dump_json() + "\n", encoding="utf-8")

    output_dir = tmp_path / "pilot"
    telemetry_dir = output_dir / "telemetry"
    telemetry_dir.mkdir(parents=True)
    report_path = telemetry_dir / f"{record.record_id}.analysis.json"
    sidecar_path = telemetry_dir / f"{record.record_id}.run.json"
    report_path.write_text(json.dumps({
        "video": {"sha256": record.media_sha256},
        "rights": {
            "reference": record.rights_reference_hash,
            "basis": record.rights_basis,
            "model_training_permitted": False,
        },
        "frame_evidence": [{"timestamp_seconds": 0.1}],
        "cut_candidates": [],
        "transcript_segments": [],
        "ocr_spans": [],
        "stages": {"asr": {"status": "complete"}},
    }), encoding="utf-8")
    config = AnalyzerConfig()
    sidecar_path.write_text(json.dumps({
        "config_sha256": _config_fingerprint(config),
        "media_sha256": record.media_sha256,
        "rights_reference_hash": record.rights_reference_hash,
        "rights_expires_at": None,
        "status": "complete",
        "artifact_bytes_written": 0,
    }), encoding="utf-8")

    summary = process_selected(manifest, output_dir, config=config, resume=True)
    assert summary["resumed_records"] == 1
    assert summary["analyzed_new_records"] == 0
    assert summary["complete_records"] == 1


def test_changed_input_invalidates_resume_and_reports_failure(tmp_path: Path) -> None:
    media = tmp_path / "owned_clip.mp4"
    media.write_bytes(b"original")
    record = _selected_record(media)
    manifest = tmp_path / "selected_manifest.jsonl"
    manifest.write_text(record.model_dump_json() + "\n", encoding="utf-8")
    media.write_bytes(b"modified bytes")
    summary = process_selected(
        manifest, tmp_path / "pilot", config=AnalyzerConfig(), resume=True
    )
    assert summary["resumed_records"] == 0
    assert summary["failed_records"] == 1
