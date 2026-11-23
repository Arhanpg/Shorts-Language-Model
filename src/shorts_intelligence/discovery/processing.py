"""Resumable media acquisition and VidTrace processing batches."""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shorts_intelligence.analyzer import analyze_video
from shorts_intelligence.config import AnalyzerConfig
from shorts_intelligence.discovery.downloader import download_candidate
from shorts_intelligence.discovery.models import DiscoveredCandidate
from shorts_intelligence.discovery.storage import DiscoveryStore
from shorts_intelligence.media.probe import MediaError, probe_video

logger = logging.getLogger(__name__)


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
    elif _transcript_looks_degenerate(report.transcript_segments):
        flags.append("asr_suspected_gibberish")
    if not report.ocr_spans:
        flags.append("ocr_no_text_spans")
    elif _ocr_is_low_signal(report.ocr_spans):
        flags.append("ocr_low_signal")
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


def _artifact_field(value: Any, field: str, default: Any = None) -> Any:
    """Read a field from either a model object or a decoded JSON object."""
    return value.get(field, default) if isinstance(value, dict) else getattr(value, field, default)


def _read_artifact_json(path_value: str | Path | None) -> dict[str, Any]:
    """Read a local JSON artifact; missing or malformed files do not break export."""
    if not path_value:
        return {}
    try:
        payload = json.loads(Path(path_value).expanduser().read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _artifact_quality_flags(
    existing_flags: list[str],
    *,
    transcript_path: str | Path | None,
    ocr_path: str | Path | None,
) -> list[str]:
    """Re-evaluate saved ASR/OCR artifacts when rebuilding the cumulative manifest."""
    flags = set(existing_flags)
    transcript = _read_artifact_json(transcript_path)
    segments = transcript.get("segments")
    if isinstance(segments, list) and segments and _transcript_looks_degenerate(segments):
        flags.add("asr_suspected_gibberish")
    ocr = _read_artifact_json(ocr_path)
    spans = ocr.get("spans")
    if isinstance(spans, list) and spans and _ocr_is_low_signal(spans):
        flags.add("ocr_low_signal")
    return sorted(flags)


def _transcript_looks_degenerate(segments: list[Any]) -> bool:
    """Flag obvious repeated-token or replacement-character ASR output."""
    text = " ".join(str(_artifact_field(segment, "text", "") or "") for segment in segments).strip()
    if not text:
        return True
    tokens = [token.casefold() for token in re.findall(r"\w+", text, flags=re.UNICODE)]
    if not tokens:
        return True
    unique_ratio = len(set(tokens)) / len(tokens)
    repeated_ratio = max(tokens.count(token) for token in set(tokens)) / len(tokens)
    replacement_ratio = text.count("\ufffd") / max(1, len(text))
    return (
        replacement_ratio >= 0.02
        or (len(tokens) >= 20 and unique_ratio < 0.12)
        or (len(tokens) >= 20 and repeated_ratio >= 0.75)
    )


def _ocr_is_low_signal(spans: list[Any]) -> bool:
    """Flag OCR dominated by low-confidence output without penalizing short scripts."""
    confidences = [
        float(_artifact_field(span, "confidence", 0.0) or 0.0)
        for span in spans
        if _artifact_field(span, "confidence") is not None
    ]
    return bool(confidences) and (
        sum(value < 0.35 for value in confidences) / len(confidences) >= 0.5
    )


def _export_processing_manifest(
    store: DiscoveryStore,
    output_path: Path,
    *,
    min_metric: int,
) -> int:
    """Write a compact JSONL manifest for successfully processed videos."""
    exported_at = datetime.now(UTC).isoformat()
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    count = 0
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in store.iter_processing_records():
            metric = row["metric_value"]
            quality_flags = _artifact_quality_flags(
                json.loads(row["quality_flags_json"] or "[]"),
                transcript_path=row["transcript_path"],
                ocr_path=row["ocr_path"],
            )
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
                    "kind": row["metric_kind"],
                    "value": metric,
                    "is_estimate": bool(row["metric_is_estimate"]),
                    "display_value": row["metric_display_value"],
                    "source": row["metric_source"],
                    "threshold": min_metric,
                    "threshold_met": metric is not None and int(metric) >= min_metric,
                },
                "media": {"path": row["media_path"], "sha256": row["media_sha256"]},
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
                "quality_flags": quality_flags,
                "processing_completed_at": row["completed_at"],
            }
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            count += 1
    temporary.replace(output_path)
    return count


def run_processing_batch(
    *,
    database: Path,
    download_dir: Path,
    artifact_dir: Path,
    dataset_manifest: Path,
    limit: int = 25,
    min_metric: int = 1_000_000,
    platform: str = "all",
    instagram_session_username: str | None = None,
    instagram_session_file: Path | None = None,
    asr_model: str = "small",
    asr_device: str = "cuda",
    asr_timeout_seconds: float = 300.0,
    language: str | None = None,
    max_duration_seconds: float = 180.0,
    max_file_size_mb: int = 1000,
    max_keyframes: int = 24,
    max_ocr_frames: int = 12,
    keep_frame_artifacts: bool = False,
    delete_media_after_processing: bool = False,
    max_processing_attempts: int = 2,
) -> dict[str, int | str]:
    """Download and process a bounded batch of discovered Shorts and Reels."""
    processed = downloaded = failed = duplicates = 0
    platform_totals = {
        "youtube": {"selected": 0, "downloaded": 0, "processed": 0},
        "instagram": {"selected": 0, "downloaded": 0, "processed": 0},
    }
    with DiscoveryStore(database) as store:
        queued = store.processing_candidates(
            min_metric=min_metric,
            limit=limit,
            platform=platform,
            max_attempts=max_processing_attempts,
        )
        for candidate, _, _, _ in queued:
            platform_totals[candidate.platform]["selected"] += 1
        for item_index, (candidate, existing_path, download_status, stored_hash) in enumerate(queued, start=1):
            item_started = time.monotonic()
            platform, source_id = candidate.platform, candidate.source_id
            logger.info(
                "Processing video %d/%d | platform=%s | id=%s | metric=%s",
                item_index,
                len(queued),
                platform,
                source_id,
                candidate.qualifying_metric(),
            )
            did_download = download_attempted = download_succeeded = False
            media_validation_failed = False
            media_path: Path | None = None
            store.mark_processing_started(candidate)
            try:
                item_dir = artifact_dir.expanduser().resolve() / platform / _safe_component(source_id)
                item_dir.mkdir(parents=True, exist_ok=True)
                config = AnalyzerConfig(
                    max_file_size_mb=max_file_size_mb,
                    max_duration_seconds=max_duration_seconds,
                    max_keyframes=max_keyframes,
                    max_ocr_frames=max_ocr_frames,
                    asr_model=asr_model,
                    asr_device=asr_device,
                    asr_timeout_seconds=asr_timeout_seconds,
                    language=language,
                    enable_asr=True,
                    enable_ocr=True,
                    enable_audio_analysis=True,
                    keep_artifacts=keep_frame_artifacts,
                )
                media_path = Path(existing_path).expanduser().resolve() if existing_path else None
                if media_path is None or not media_path.is_file() or media_path.stat().st_size == 0:
                    download_attempted = True
                    media_path = download_candidate(
                        candidate,
                        download_dir,
                        instagram_session_username=instagram_session_username,
                        instagram_session_file=str(instagram_session_file) if instagram_session_file else None,
                    )
                    did_download = True
                    downloaded += 1
                    platform_totals[platform]["downloaded"] += 1

                media_path = media_path.expanduser().resolve(strict=True)
                try:
                    media_metadata = probe_video(media_path, config)
                except Exception:
                    media_validation_failed = True
                    raise
                media_hash = media_metadata.sha256
                download_succeeded = True
                if stored_hash and not did_download and stored_hash != media_hash:
                    raise MediaError("Stored media SHA-256 does not match the local file.")

                duplicate = store.find_media_hash(media_hash)
                if duplicate and (duplicate["platform"], duplicate["source_id"]) != (platform, source_id):
                    duplicate_of = f"{duplicate['platform']}:{duplicate['source_id']}"
                    store.mark_duplicate_media(platform, source_id, duplicate_of=duplicate_of, media_sha256=media_hash)
                    store.mark_processing_duplicate(platform, source_id, duplicate_of=duplicate_of, media_sha256=media_hash)
                    if did_download or delete_media_after_processing:
                        media_path.unlink(missing_ok=True)
                        media_path.with_suffix(".metadata.json").unlink(missing_ok=True)
                    duplicates += 1
                    continue

                if did_download or download_status != "downloaded" or not existing_path:
                    store.mark_download(platform, source_id, path=str(media_path), media_sha256=media_hash)

                analysis_path = item_dir / "analysis.json"
                logger.info(
                    "Media ready | platform=%s | id=%s | path=%s",
                    platform,
                    source_id,
                    media_path,
                )
                report = analyze_video(media_path, analysis_path, config=config)
                logger.info(
                    "Analysis stages | platform=%s | id=%s | ASR=%s | OCR=%s",
                    platform,
                    source_id,
                    report.stages["asr"].engine or report.stages["asr"].status,
                    report.stages["ocr"].engine or report.stages["ocr"].status,
                )
                transcript_path, transcript_count, detected_language = _write_transcript_artifacts(item_dir, candidate, report)
                ocr_path, ocr_count = _write_ocr_artifact(item_dir, candidate, report)
                _atomic_write_json(item_dir / "asset.json", {
                    "schema_version": "1.0.0",
                    "candidate": candidate.model_dump(mode="json"),
                    "media_path": str(media_path),
                    "media_sha256": media_hash,
                    "video": report.video.model_dump(mode="json"),
                    "analysis_report": str(analysis_path),
                    "transcript": str(transcript_path),
                    "ocr": str(ocr_path),
                })
                store.mark_processing_complete(
                    platform, source_id,
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
                    quality_flags=_quality_flags(report, candidate),
                )
                if delete_media_after_processing:
                    media_path.unlink(missing_ok=True)
                    media_path.with_suffix(".metadata.json").unlink(missing_ok=True)
                    store.mark_processed_media_deleted(platform, source_id)
                processed += 1
                platform_totals[platform]["processed"] += 1
                logger.info(
                    "Video complete | platform=%s | id=%s | transcript_segments=%d | ocr_spans=%d | elapsed=%.1fs",
                    platform,
                    source_id,
                    transcript_count,
                    ocr_count,
                    time.monotonic() - item_started,
                )
            except Exception as exc:
                logger.exception(
                    "Video processing failed | platform=%s | id=%s | elapsed=%.1fs",
                    platform,
                    source_id,
                    time.monotonic() - item_started,
                )
                error_text = f"{type(exc).__name__}: {exc}"
                # Duration/size/format validation failures are terminal asset
                # classifications, not transient pipeline errors. Do not spend
                # the retry budget downloading the same invalid asset again.
                terminal_media_error = isinstance(exc, MediaError) and any(
                    marker in str(exc).casefold()
                    for marker in (
                        "video duration is", "configured limit is", "no video stream",
                        "unsupported extension", "input is",
                    )
                )
                if terminal_media_error:
                    store.mark_processing_rejected(platform, source_id, reason=error_text)
                else:
                    store.mark_processing_failure(platform, source_id, error=error_text)
                if delete_media_after_processing and media_path is not None:
                    media_path.unlink(missing_ok=True)
                    media_path.with_suffix(".metadata.json").unlink(missing_ok=True)
                    store.mark_download_failure(platform, source_id, error=f"{type(exc).__name__}: {exc}")
                if media_validation_failed or (download_attempted and not download_succeeded):
                    store.mark_download_failure(platform, source_id, error=f"{type(exc).__name__}: {exc}")
                    if media_validation_failed and media_path is not None:
                        media_path.unlink(missing_ok=True)
                        media_path.with_suffix(".metadata.json").unlink(missing_ok=True)
                failed += 1

        manifest_count = _export_processing_manifest(store, dataset_manifest, min_metric=min_metric)
        statuses = store.processing_summary()

    return {
        "candidates_selected": len(queued),
        "media_downloaded_this_run": downloaded,
        "processed_this_run": processed,
        "duplicates": duplicates,
        "failed": failed,
        "manifest_records": manifest_count,
        "manifest_path": str(dataset_manifest.expanduser().resolve()),
        "processing_complete_total": statuses.get("complete", 0),
        "processing_failed_total": statuses.get("failed", 0),
        "youtube_candidates_selected": platform_totals["youtube"]["selected"],
        "instagram_candidates_selected": platform_totals["instagram"]["selected"],
        "youtube_downloaded": platform_totals["youtube"]["downloaded"],
        "instagram_downloaded": platform_totals["instagram"]["downloaded"],
        "youtube_processed": platform_totals["youtube"]["processed"],
        "instagram_processed": platform_totals["instagram"]["processed"],
        "platform": platform,
    }
