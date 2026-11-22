"""Resumable rights-gated media acquisition and VidTrace processing batches."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shorts_intelligence.analyzer import analyze_video
from shorts_intelligence.config import AnalyzerConfig
from shorts_intelligence.discovery.downloader import download_candidate
from shorts_intelligence.discovery.models import DiscoveredCandidate
from shorts_intelligence.discovery.storage import DiscoveryStore
from shorts_intelligence.media.probe import MediaError, probe_video


def _safe_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("Source ID cannot be converted to a safe artifact path.")
    return cleaned[:120]


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _format_timestamp(seconds: float) -> str:
    total_ms = max(0, round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


def _write_transcript_artifacts(
    artifact_dir: Path,
    candidate: DiscoveredCandidate,
    report: Any,
) -> tuple[Path, int, str | None]:
    segments = [
        item.model_dump(mode="json")
        for item in report.transcript_segments
    ]
    language = next(
        (item.language for item in report.transcript_segments if item.language),
        None,
    )
    payload = {
        "schema_version": "1.0.0",
        "platform": candidate.platform,
        "source_id": candidate.source_id,
        "language": language,
        "segment_count": len(segments),
        "segments": segments,
        "asr_stage": report.stages["asr"].model_dump(mode="json"),
    }
    json_path = artifact_dir / "transcript.json"
    _atomic_write_json(json_path, payload)

    markdown = [
        f"# Transcript — {candidate.platform}:{candidate.source_id}",
        "",
        f"- Language: {language or 'unknown'}",
        f"- Segments: {len(segments)}",
        f"- ASR engine: {report.stages['asr'].engine or 'unavailable'}",
        "",
    ]
    for segment in report.transcript_segments:
        markdown.append(
            f"[{_format_timestamp(segment.start_seconds)} – "
            f"{_format_timestamp(segment.end_seconds)}] {segment.text}"
        )
    md_path = artifact_dir / "transcript.md"
    temporary = md_path.with_name(md_path.name + ".tmp")
    temporary.write_text("\n".join(markdown) + "\n", encoding="utf-8")
    temporary.replace(md_path)
    return json_path, len(segments), language


def _write_ocr_artifact(
    artifact_dir: Path,
    candidate: DiscoveredCandidate,
    report: Any,
) -> tuple[Path, int]:
    spans = [
        item.model_dump(mode="json")
        for item in report.ocr_spans
    ]
    payload = {
        "schema_version": "1.0.0",
        "platform": candidate.platform,
        "source_id": candidate.source_id,
        "span_count": len(spans),
        "spans": spans,
        "ocr_stage": report.stages["ocr"].model_dump(mode="json"),
    }
    json_path = artifact_dir / "ocr.json"
    _atomic_write_json(json_path, payload)

    lines = [
        f"# OCR — {candidate.platform}:{candidate.source_id}",
        "",
        f"- Text spans: {len(spans)}",
        f"- OCR engine: {report.stages['ocr'].engine or 'unavailable'}",
        "",
    ]
    for span in report.ocr_spans:
        lines.append(
            f"[{_format_timestamp(span.timestamp_seconds)} | frame "
            f"{span.frame_index} | confidence {span.confidence:.3f}] {span.text}"
        )
    md_path = artifact_dir / "ocr.md"
    temporary = md_path.with_name(md_path.name + ".tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(md_path)
    return json_path, len(spans)


def _quality_flags(report: Any, candidate: DiscoveredCandidate) -> list[str]:
    flags: list[str] = []
    if not report.transcript_segments:
        flags.append("asr_no_segments")
    if not report.ocr_spans:
        flags.append("ocr_no_text_spans")
    if report.stages["asr"].status != "complete":
        flags.append(f"asr_{report.stages['asr'].status}")
    if report.stages["ocr"].status != "complete":
        flags.append(f"ocr_{report.stages['ocr'].status}")
    if candidate.metadata.get("metric_is_estimate") is True:
        flags.append("engagement_metric_is_estimated")
    if candidate.qualifying_metric_kind() == "plays":
        flags.append("instagram_play_count_not_youtube_view_count")
    if report.video.duration_seconds > 180:
        flags.append("duration_over_short_form_target")
    return sorted(set(flags))


def _export_processing_manifest(
    store: DiscoveryStore,
    output_path: Path,
    *,
    min_metric: int,
) -> int:
    """Stream current, rights-valid processing records to an atomic JSONL manifest."""
    exported_at = datetime.now(UTC).isoformat()
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    count = 0
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in store.iter_processing_records():
            metadata = json.loads(row.get("metadata_json") or "{}")
            is_estimate = bool(row["metric_is_estimate"])
            metric = row["metric_value"]
            metric_kind = row["metric_kind"]
            flags = json.loads(row.get("quality_flags_json") or "[]")
            reasons = ["manual_content_and_transcript_review_required"]
            if is_estimate:
                reasons.append("engagement_metric_is_estimated")
            if metric is None or int(metric) < min_metric:
                reasons.append("metric_below_export_threshold")
            if row["transcript_segments"] == 0:
                reasons.append("no_transcript_segments")
            if row["ocr_spans"] == 0:
                reasons.append("no_ocr_text_spans")
            record = {
                "schema_version": "1.0.0",
                "record_type": "short_video_multimodal_observation",
                "exported_at": exported_at,
                "platform": row["platform"],
                "source_id": row["source_id"],
                "canonical_url": row["canonical_url"],
                "title": row["title"],
                "creator": row["creator"],
                "description": row["description"],
                "hashtags": json.loads(row["hashtags_json"] or "[]"),
                "discovered_at": row["discovered_at"],
                "metric": {
                    "kind": metric_kind,
                    "value": metric,
                    "is_estimate": is_estimate,
                    "display_value": row["metric_display_value"],
                    "source": row["metric_source"],
                    "threshold": min_metric,
                    "threshold_met": metric is not None and int(metric) >= min_metric,
                },
                "media": {
                    "path": row["media_path"],
                    "sha256": row["media_sha256"],
                },
                "artifacts": {
                    "analysis_json": row["analysis_path"],
                    "transcript_json": row["transcript_path"],
                    "ocr_json": row["ocr_path"],
                },
                "telemetry": {
                    "transcript_segments": row["transcript_segments"],
                    "ocr_spans": row["ocr_spans"],
                    "language": row["detected_language"],
                    "asr_engine": row["asr_engine"],
                    "ocr_engine": row["ocr_engine"],
                },
                "rights": {
                    "basis": row["rights_basis"],
                    "evidence_ref": row["evidence_ref"],
                    "media_retrieval": bool(row["media_retrieval"]),
                    "media_analysis": bool(row["media_analysis"]),
                    "temporary_processing": bool(row["temporary_processing"]),
                    "derived_artifact_retention": bool(row["derived_artifact_retention"]),
                    "model_training": bool(row["model_training"]),
                    "status": "locally_attested_current_grant",
                },
                "quality_flags": flags,
                "processing_completed_at": row["completed_at"],
                "review": {
                    "status": "review_required",
                    "training_approved": False,
                    "reasons": sorted(set(reasons)),
                },
                "training_ready": False,
                "source_metadata_snapshot": metadata,
            }
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            count += 1

    temporary.replace(output_path)
    return count


def run_processing_batch(
    *,
    database: Path,
    rights_manifest: Path,
    download_dir: Path,
    artifact_dir: Path,
    dataset_manifest: Path,
    limit: int = 25,
    min_metric: int = 1_000_000,
    allow_estimated_metrics: bool = False,
    instagram_session_username: str | None = None,
    instagram_session_file: Path | None = None,
    asr_model: str = "small",
    asr_device: str = "cpu",
    language: str | None = None,
    max_duration_seconds: float = 180.0,
    max_file_size_mb: int = 1000,
    max_keyframes: int = 24,
    max_ocr_frames: int = 12,
    keep_frame_artifacts: bool = False,
) -> dict[str, int | str]:
    """Acquire and process a bounded set of authorized 1M+ short-form videos."""
    from shorts_intelligence.discovery.cli import _iter_rights_manifest

    processed = downloaded = failed = duplicates = 0
    with DiscoveryStore(database) as store:
        indexed = store.replace_rights_authorizations(
            _iter_rights_manifest(rights_manifest)
        )
        queued = store.processing_candidates(
            min_metric=min_metric,
            allow_estimated_metrics=allow_estimated_metrics,
            limit=limit,
        )
        blocked = store.count_processing_blocked(min_metric=min_metric)
        for candidate, authorization, existing_path, download_status, stored_hash in queued:
            authorization.validate_for_training()
            platform = candidate.platform
            source_id = candidate.source_id
            did_download = False
            download_attempted = False
            download_succeeded = False
            media_validation_failed = False
            media_path: Path | None = None
            store.mark_processing_started(candidate, authorization)

            try:
                safe_id = _safe_component(source_id)
                item_dir = (
                    artifact_dir.expanduser().resolve()
                    / platform
                    / safe_id
                )
                item_dir.mkdir(parents=True, exist_ok=True)
                config = AnalyzerConfig(
                    max_file_size_mb=max_file_size_mb,
                    max_duration_seconds=max_duration_seconds,
                    max_keyframes=max_keyframes,
                    max_ocr_frames=max_ocr_frames,
                    asr_model=asr_model,
                    asr_device=asr_device,
                    language=language,
                    enable_asr=True,
                    enable_ocr=True,
                    enable_audio_analysis=True,
                    keep_artifacts=keep_frame_artifacts,
                )
                media_path = (
                    Path(existing_path).expanduser().resolve()
                    if existing_path else None
                )
                if media_path is None or not media_path.is_file() or media_path.stat().st_size == 0:
                    download_attempted = True
                    media_path = download_candidate(
                        candidate,
                        authorization,
                        download_dir,
                        instagram_session_username=instagram_session_username,
                        instagram_session_file=(
                            str(instagram_session_file)
                            if instagram_session_file else None
                        ),
                    )
                    did_download = True
                    downloaded += 1

                media_path = media_path.expanduser().resolve(strict=True)
                try:
                    media_metadata = probe_video(media_path, config)
                except Exception:
                    media_validation_failed = True
                    raise
                media_hash = media_metadata.sha256
                download_succeeded = True
                if stored_hash and not did_download and stored_hash != media_hash:
                    raise MediaError(
                        "Stored media SHA-256 no longer matches the downloaded file; "
                        "move the changed file aside and investigate before retrying."
                    )

                duplicate = store.find_media_hash(media_hash)
                if duplicate and not (
                    duplicate["platform"] == platform
                    and duplicate["source_id"] == source_id
                ):
                    duplicate_of = (
                        f"{duplicate['platform']}:{duplicate['source_id']}"
                    )
                    store.mark_duplicate_media(
                        platform,
                        source_id,
                        duplicate_of=duplicate_of,
                        media_sha256=media_hash,
                    )
                    store.mark_processing_duplicate(
                        platform,
                        source_id,
                        duplicate_of=duplicate_of,
                        media_sha256=media_hash,
                    )
                    if did_download:
                        media_path.unlink(missing_ok=True)
                        media_path.with_suffix(".metadata.json").unlink(missing_ok=True)
                    duplicates += 1
                    continue

                if did_download or download_status != "downloaded" or not existing_path:
                    store.mark_download(
                        platform,
                        source_id,
                        path=str(media_path),
                        media_sha256=media_hash,
                    )

                analysis_path = item_dir / "analysis.json"
                report = analyze_video(
                    media_path,
                    analysis_path,
                    rights_basis=authorization.basis,
                    rights_reference=authorization.evidence_ref,
                    training_permitted=authorization.model_training,
                    config=config,
                )
                transcript_path, transcript_count, detected_language = (
                    _write_transcript_artifacts(item_dir, candidate, report)
                )
                ocr_path, ocr_count = _write_ocr_artifact(
                    item_dir, candidate, report
                )
                asset_path = item_dir / "asset.json"
                _atomic_write_json(asset_path, {
                    "schema_version": "1.0.0",
                    "candidate": candidate.model_dump(mode="json"),
                    "rights": authorization.model_dump(mode="json"),
                    "media_path": str(media_path),
                    "media_sha256": media_hash,
                    "video": report.video.model_dump(mode="json"),
                    "analysis_report": str(analysis_path),
                    "transcript": str(transcript_path),
                    "ocr": str(ocr_path),
                    "training_ready": False,
                    "review_status": "review_required",
                })
                flags = _quality_flags(report, candidate)
                store.mark_processing_complete(
                    platform,
                    source_id,
                    media_path=str(media_path),
                    media_sha256=media_hash,
                    analysis_path=str(analysis_path),
                    transcript_path=str(transcript_path),
                    ocr_path=str(ocr_path),
                    transcript_segments=transcript_count,
                    ocr_spans=ocr_count,
                    detected_language=detected_language,
                    asr_engine=report.stages["asr"].engine,
                    ocr_engine=report.stages["ocr"].engine,
                    quality_flags=flags,
                )
                processed += 1
            except Exception as exc:
                store.mark_processing_failure(
                    platform,
                    source_id,
                    error=f"{type(exc).__name__}: {exc}",
                )
                if media_validation_failed or (
                    download_attempted and not download_succeeded
                ):
                    store.mark_download_failure(
                        platform,
                        source_id,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    if media_validation_failed and media_path is not None:
                        media_path.unlink(missing_ok=True)
                        media_path.with_suffix(".metadata.json").unlink(missing_ok=True)
                failed += 1

        manifest_count = _export_processing_manifest(
            store,
            dataset_manifest,
            min_metric=min_metric,
        )
        statuses = store.processing_summary()

    return {
        "rights_records_indexed": indexed,
        "authorized_candidates_selected": len(queued),
        "blocked_without_current_rights": blocked,
        "media_downloaded_this_run": downloaded,
        "processed_this_run": processed,
        "duplicates": duplicates,
        "failed": failed,
        "manifest_records": manifest_count,
        "manifest_path": str(dataset_manifest.expanduser().resolve()),
        "processing_complete_total": statuses.get("complete", 0),
        "processing_failed_total": statuses.get("failed", 0),
        "estimated_metrics_included": int(allow_estimated_metrics),
    }
