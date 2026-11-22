from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from shorts_intelligence.discovery.models import (
    AcquisitionAuthorization,
    DiscoveredCandidate,
)
from shorts_intelligence.discovery.storage import DiscoveryStore
from shorts_intelligence.schemas import OCRSpan, StageStatus, TranscriptSegment, VideoMetadata


def _candidate() -> DiscoveredCandidate:
    return DiscoveredCandidate(
        platform="youtube",
        source_id="BatchVideo01",
        canonical_url="https://www.youtube.com/shorts/BatchVideo01",
        title="Batch processing smoke test",
        view_count=1_500_000,
        metric_source="test_fixture",
        short_format_status="confirmed",
    )


def _rights(candidate: DiscoveredCandidate) -> AcquisitionAuthorization:
    return AcquisitionAuthorization(
        platform=candidate.platform,
        source_id=candidate.source_id,
        basis="creator_permission",
        evidence_ref="private-test-consent:batch-video-01",
        media_retrieval=True,
        media_analysis=True,
        temporary_processing=True,
        derived_artifact_retention=True,
        model_training=True,
    )


def _fake_report() -> SimpleNamespace:
    transcript = TranscriptSegment(
        start_seconds=0.2,
        end_seconds=1.4,
        text="A test transcript segment.",
        language="en",
    )
    ocr = OCRSpan(
        timestamp_seconds=0.8,
        text="TEST",
        confidence=0.98,
        bbox_xyxy=[10, 10, 90, 40],
        engine="vidtrace-paddleocr",
        frame_index=4,
    )
    video = VideoMetadata(
        file_name="BatchVideo01.mp4",
        sha256="b" * 64,
        file_size_bytes=1024,
        duration_seconds=12.0,
        width=1080,
        height=1920,
        fps=30.0,
        frame_count=360,
        video_codec="h264",
        audio_present=True,
        audio_codec="aac",
        aspect_ratio="9:16",
    )
    return SimpleNamespace(
        transcript_segments=[transcript],
        ocr_spans=[ocr],
        video=video,
        stages={
            "asr": StageStatus(
                status="complete",
                engine="vidtrace-faster-whisper",
                detail="1 segment",
            ),
            "ocr": StageStatus(
                status="complete",
                engine="vidtrace-paddleocr",
                detail="1 span",
            ),
        },
    )


def _fake_probe(path: Path, _config) -> VideoMetadata:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return VideoMetadata(
        file_name=path.name,
        sha256=digest,
        file_size_bytes=path.stat().st_size,
        duration_seconds=12.0,
        width=1080,
        height=1920,
        fps=30.0,
        frame_count=360,
        video_codec="h264",
        audio_present=True,
        audio_codec="aac",
        aspect_ratio="9:16",
    )


def _write_private_rights(path: Path, authorization: AcquisitionAuthorization) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(authorization.model_dump_json() + "\n", encoding="utf-8")


def test_processing_batch_resumes_without_redownloading_or_reanalyzing(
    tmp_path: Path,
    monkeypatch,
):
    from shorts_intelligence.discovery import processing

    candidate = _candidate()
    authorization = _rights(candidate)
    database = tmp_path / ".shortslm" / "discovery.sqlite3"
    rights_manifest = tmp_path / "private" / "rights.jsonl"
    download_dir = tmp_path / "private" / "acquired"
    artifact_dir = tmp_path / "private" / "processed"
    dataset_manifest = tmp_path / "outputs" / "dataset.jsonl"

    with DiscoveryStore(database) as store:
        store.start_run("processing-batch", 10, 1_000_000)
        store.upsert_candidate(
            candidate, min_views=1_000_000, run_id="processing-batch"
        )

    _write_private_rights(rights_manifest, authorization)
    calls = {"download": 0, "analyze": 0}

    def fake_download(candidate, authorization, output_dir, **_kwargs):
        calls["download"] += 1
        output_dir.mkdir(parents=True, exist_ok=True)
        media_path = output_dir / f"{candidate.source_id}.mp4"
        media_path.write_bytes(b"test-mp4-payload")
        media_path.with_suffix(".metadata.json").write_text("{}", encoding="utf-8")
        return media_path

    def fake_analyze(input_path, output_path, **_kwargs):
        calls["analyze"] += 1
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("{}", encoding="utf-8")
        return _fake_report()

    monkeypatch.setattr(processing, "download_candidate", fake_download)
    monkeypatch.setattr(processing, "probe_video", _fake_probe)
    monkeypatch.setattr(processing, "analyze_video", fake_analyze)

    first = processing.run_processing_batch(
        database=database,
        rights_manifest=rights_manifest,
        download_dir=download_dir,
        artifact_dir=artifact_dir,
        dataset_manifest=dataset_manifest,
        limit=10,
    )
    assert first["processed_this_run"] == 1
    assert first["failed"] == 0
    assert calls == {"download": 1, "analyze": 1}

    item_dir = artifact_dir / "youtube" / candidate.source_id
    assert (item_dir / "analysis.json").is_file()
    transcript_payload = json.loads((item_dir / "transcript.json").read_text(encoding="utf-8"))
    ocr_payload = json.loads((item_dir / "ocr.json").read_text(encoding="utf-8"))
    assert transcript_payload["segment_count"] == 1
    assert ocr_payload["span_count"] == 1

    records = [
        json.loads(line)
        for line in dataset_manifest.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(records) == 1
    assert records[0]["training_ready"] is False
    assert records[0]["review"]["status"] == "review_required"

    second = processing.run_processing_batch(
        database=database,
        rights_manifest=rights_manifest,
        download_dir=download_dir,
        artifact_dir=artifact_dir,
        dataset_manifest=dataset_manifest,
        limit=10,
    )
    assert second["authorized_candidates_selected"] == 0
    assert second["manifest_records"] == 1
    assert calls == {"download": 1, "analyze": 1}


def test_analysis_failure_keeps_downloaded_media_and_retry_skips_download(
    tmp_path: Path,
    monkeypatch,
):
    from shorts_intelligence.discovery import processing

    candidate = _candidate()
    authorization = _rights(candidate)
    database = tmp_path / ".shortslm" / "discovery.sqlite3"
    rights_manifest = tmp_path / "private" / "rights.jsonl"
    download_dir = tmp_path / "private" / "acquired"
    artifact_dir = tmp_path / "private" / "processed"
    dataset_manifest = tmp_path / "outputs" / "dataset.jsonl"

    with DiscoveryStore(database) as store:
        store.start_run("processing-retry", 10, 1_000_000)
        store.upsert_candidate(
            candidate, min_views=1_000_000, run_id="processing-retry"
        )
    _write_private_rights(rights_manifest, authorization)

    calls = {"download": 0, "analyze": 0}

    def fake_download(candidate, authorization, output_dir, **_kwargs):
        calls["download"] += 1
        output_dir.mkdir(parents=True, exist_ok=True)
        media_path = output_dir / f"{candidate.source_id}.mp4"
        media_path.write_bytes(b"stable-test-mp4")
        return media_path

    def flaky_analyze(input_path, output_path, **_kwargs):
        calls["analyze"] += 1
        if calls["analyze"] == 1:
            raise RuntimeError("temporary ASR/OCR initialization failure")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("{}", encoding="utf-8")
        return _fake_report()

    monkeypatch.setattr(processing, "download_candidate", fake_download)
    monkeypatch.setattr(processing, "probe_video", _fake_probe)
    monkeypatch.setattr(processing, "analyze_video", flaky_analyze)

    first = processing.run_processing_batch(
        database=database,
        rights_manifest=rights_manifest,
        download_dir=download_dir,
        artifact_dir=artifact_dir,
        dataset_manifest=dataset_manifest,
        limit=10,
    )
    assert first["failed"] == 1
    with DiscoveryStore(database) as store:
        assert store.connection.execute(
            "SELECT download_status FROM candidates WHERE platform='youtube' AND source_id=?",
            (candidate.source_id,),
        ).fetchone()["download_status"] == "downloaded"
        assert store.processing_summary()["failed"] == 1

    second = processing.run_processing_batch(
        database=database,
        rights_manifest=rights_manifest,
        download_dir=download_dir,
        artifact_dir=artifact_dir,
        dataset_manifest=dataset_manifest,
        limit=10,
    )
    assert second["processed_this_run"] == 1
    assert second["failed"] == 0
    assert calls == {"download": 1, "analyze": 2}
