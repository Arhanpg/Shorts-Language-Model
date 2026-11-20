"""Resumable sequential Phase 1 processing and measured Phase 2 pilot metrics."""

from __future__ import annotations

import csv
import hashlib
import json
import time
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from shorts_intelligence.analyzer import analyze_video
from shorts_intelligence.config import AnalyzerConfig
from shorts_intelligence.media.probe import sha256_file
from shorts_intelligence.pilot.manifest import write_json
from shorts_intelligence.pilot.schemas import SelectedRecord


def load_selected_manifest(path: Path) -> list[SelectedRecord]:
    records: list[SelectedRecord] = []
    seen: set[str] = set()
    with path.expanduser().resolve(strict=True).open("r", encoding="utf-8") as handle:
        for row_number, line in enumerate(handle, start=1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                record = SelectedRecord.model_validate_json(line)
            except ValidationError as exc:
                raise ValueError(
                    f"Selected manifest row {row_number} is invalid: "
                    f"{exc.errors()[0]['msg']}"
                ) from exc
            if record.record_id in seen:
                raise ValueError(f"Duplicate record_id in selected manifest: {record.record_id}")
            seen.add(record.record_id)
            records.append(record)
    return records


def _config_fingerprint(config: AnalyzerConfig) -> str:
    serialized = json.dumps(asdict(config), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _directory_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(
        child.stat().st_size for child in path.rglob("*") if child.is_file()
    )


def _resume_metrics(
    record: SelectedRecord,
    output_path: Path,
    sidecar_path: Path,
    config_hash: str,
) -> dict[str, Any] | None:
    """Return metrics for an exactly matching previous result; otherwise reprocess."""
    if not output_path.is_file() or not sidecar_path.is_file():
        return None
    try:
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        if sidecar.get("config_sha256") != config_hash:
            return None
        if sidecar.get("media_sha256") != record.media_sha256:
            return None
        if sidecar.get("rights_reference_hash") != record.rights_reference_hash:
            return None
        expiry = record.rights_expires_at.isoformat() if record.rights_expires_at else None
        if sidecar.get("rights_expires_at") != expiry:
            return None
        if payload.get("video", {}).get("sha256") != record.media_sha256:
            return None
        report_rights = payload.get("rights", {})
        if report_rights.get("reference") != record.rights_reference_hash:
            return None
        if report_rights.get("basis") != record.rights_basis:
            return None
        if report_rights.get("model_training_permitted") != record.model_training_permitted:
            return None
        stages = payload.get("stages", {})
        return {
            "record_id": record.record_id,
            "platform": record.platform,
            "language": record.language,
            "topic": record.topic,
            "speech_mode": record.speech_mode,
            "duration_band": record.duration_band,
            "status": sidecar.get("status", "complete"),
            "wall_seconds": 0.0,
            "input_file_bytes": record.file_size_bytes,
            "report_json_bytes": output_path.stat().st_size,
            "artifact_bytes_written": int(sidecar.get("artifact_bytes_written", 0)),
            "frame_count": len(payload.get("frame_evidence", [])),
            "cut_candidate_count": len(payload.get("cut_candidates", [])),
            "transcript_segment_count": len(payload.get("transcript_segments", [])),
            "ocr_span_count": len(payload.get("ocr_spans", [])),
            "model_training_permitted": record.model_training_permitted,
            "stage_statuses": {
                name: value.get("status", "unknown")
                for name, value in stages.items()
            },
            "resumed": True,
            "error": None,
        }
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def process_selected(
    manifest_path: Path,
    output_dir: Path,
    *,
    limit: int | None = None,
    config: AnalyzerConfig | None = None,
    resume: bool = True,
) -> dict[str, object]:
    """Process records one at a time; completed outputs can be safely resumed.

    The run sidecar fingerprints the Phase 1 config, media SHA-256 and hashed
    rights reference. Changes invalidate the previous result and trigger reprocessing.
    """
    manifest_path = manifest_path.expanduser().resolve(strict=True)
    records = load_selected_manifest(manifest_path)
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        records = records[:limit]
    output_dir.mkdir(parents=True, exist_ok=True)
    telemetry_dir = output_dir / "telemetry"
    telemetry_dir.mkdir(parents=True, exist_ok=True)
    config = config or AnalyzerConfig()
    config_hash = _config_fingerprint(config)
    run_started = time.perf_counter()
    metrics: list[dict[str, Any]] = []

    for record in records:
        output_path = telemetry_dir / f"{record.record_id}.analysis.json"
        sidecar_path = telemetry_dir / f"{record.record_id}.run.json"
        started = time.perf_counter()
        status = "complete"
        message: str | None = None
        try:
            if not (
                record.media_analysis_permitted
                and record.temporary_processing_permitted
                and record.derived_artifact_retention_permitted
            ):
                raise PermissionError(
                    "Selected record lacks required processing capabilities."
                )
            if record.rights_expires_at and record.rights_expires_at <= datetime.now(UTC):
                raise PermissionError("Media-processing permission has expired.")
            media_path = Path(record.media_path).expanduser().resolve(strict=True)
            if not media_path.is_file():
                raise FileNotFoundError("Local media path is not a file.")
            current_hash = sha256_file(media_path)
            if current_hash != record.media_sha256:
                raise ValueError("Media SHA-256 changed after manifest validation.")
            if media_path.stat().st_size != record.file_size_bytes:
                raise ValueError("Media file size changed after manifest validation.")

            if resume:
                resumed = _resume_metrics(record, output_path, sidecar_path, config_hash)
                if resumed is not None:
                    metrics.append(resumed)
                    continue

            report = analyze_video(
                input_path=media_path,
                output_path=output_path,
                rights_basis=record.rights_basis,
                rights_reference=record.rights_reference_hash,
                training_permitted=record.model_training_permitted,
                config=config,
            )
            stage_statuses = {
                name: stage.status for name, stage in report.stages.items()
            }
            if any(value == "failed" for value in stage_statuses.values()):
                status = "partial"
            frame_count = len(report.frame_evidence)
            cut_count = len(report.cut_candidates)
            asr_count = len(report.transcript_segments)
            ocr_count = len(report.ocr_spans)
            report_json_bytes = output_path.stat().st_size
            artifact_dir = telemetry_dir / f"{output_path.stem}_frames"
            artifact_bytes_written = _directory_bytes(artifact_dir)
            sidecar = {
                "schema_version": "1.0.0",
                "media_sha256": record.media_sha256,
                "rights_reference_hash": record.rights_reference_hash,
                "rights_expires_at": (
                    record.rights_expires_at.isoformat()
                    if record.rights_expires_at else None
                ),
                "config_sha256": config_hash,
                "status": status,
                "artifact_bytes_written": artifact_bytes_written,
            }
            write_json(sidecar_path, sidecar)
            input_file_bytes = record.file_size_bytes
        except Exception as exc:
            status = "failed"
            message = f"{type(exc).__name__}: {str(exc)[:500]}"
            input_file_bytes = record.file_size_bytes
            report_json_bytes = 0
            artifact_bytes_written = 0
            frame_count = cut_count = asr_count = ocr_count = 0
            stage_statuses = {}

        elapsed = time.perf_counter() - started
        metrics.append({
            "record_id": record.record_id,
            "platform": record.platform,
            "language": record.language,
            "topic": record.topic,
            "speech_mode": record.speech_mode,
            "duration_band": record.duration_band,
            "status": status,
            "wall_seconds": round(elapsed, 4),
            "input_file_bytes": input_file_bytes,
            "report_json_bytes": report_json_bytes,
            "artifact_bytes_written": artifact_bytes_written,
            "frame_count": frame_count,
            "cut_candidate_count": cut_count,
            "transcript_segment_count": asr_count,
            "ocr_span_count": ocr_count,
            "model_training_permitted": record.model_training_permitted,
            "stage_statuses": stage_statuses,
            "resumed": False,
            "error": message,
        })

    run_seconds = time.perf_counter() - run_started
    status_counts = Counter(str(item["status"]) for item in metrics)
    success = status_counts["complete"] + status_counts["partial"]
    analyzed_now = [item for item in metrics if not item["resumed"]]
    input_total = sum(int(item["input_file_bytes"]) for item in metrics)
    report_total = sum(int(item["report_json_bytes"]) for item in metrics)
    artifact_total = sum(int(item["artifact_bytes_written"]) for item in metrics)
    quality_slices: dict[str, dict[str, Any]] = {}
    stage_status_counts: Counter[str] = Counter()
    for item in metrics:
        slice_key = "|".join([
            str(item["platform"]), str(item["language"]), str(item["topic"]),
            str(item["speech_mode"]), str(item["duration_band"]),
        ])
        slice_metrics = quality_slices.setdefault(slice_key, {
            "records": 0, "complete": 0, "partial": 0, "failed": 0,
            "wall_seconds": 0.0, "frames": 0, "cut_candidates": 0,
            "asr_segments": 0, "ocr_spans": 0,
        })
        slice_metrics["records"] += 1
        slice_metrics[str(item["status"])] += 1
        slice_metrics["wall_seconds"] += float(item["wall_seconds"])
        slice_metrics["frames"] += int(item["frame_count"])
        slice_metrics["cut_candidates"] += int(item["cut_candidate_count"])
        slice_metrics["asr_segments"] += int(item["transcript_segment_count"])
        slice_metrics["ocr_spans"] += int(item["ocr_span_count"])
        for stage_name, stage_status in item["stage_statuses"].items():
            stage_status_counts[f"{stage_name}:{stage_status}"] += 1
    for slice_metrics in quality_slices.values():
        slice_metrics["wall_seconds"] = round(float(slice_metrics["wall_seconds"]), 3)
        records_in_slice = max(int(slice_metrics["records"]), 1)
        slice_metrics["success_rate"] = round(
            (int(slice_metrics["complete"]) + int(slice_metrics["partial"]))
            / records_in_slice, 4
        )

    summary: dict[str, object] = {
        "schema_version": "1.0.0",
        "manifest_name": manifest_path.name,
        "requested_records": len(records),
        "processed_records": len(metrics),
        "analyzed_new_records": len(analyzed_now),
        "resumed_records": sum(1 for item in metrics if item["resumed"]),
        "complete_records": status_counts["complete"],
        "partial_records": status_counts["partial"],
        "failed_records": status_counts["failed"],
        "success_rate": round(success / max(len(metrics), 1), 4),
        "training_permitted_processed_records": sum(
            1 for item in metrics if item["model_training_permitted"]
        ),
        "total_wall_seconds": round(run_seconds, 3),
        "mean_seconds_per_record_this_run": round(run_seconds / max(len(metrics), 1), 3),
        "mean_seconds_per_newly_analyzed_record": round(
            sum(float(item["wall_seconds"]) for item in analyzed_now) / max(len(analyzed_now), 1),
            3,
        ),
        "input_media_file_bytes_total": input_total,
        "telemetry_report_json_bytes_total": report_total,
        "keyframe_artifact_bytes_total": artifact_total,
        "total_cut_candidates": sum(int(item["cut_candidate_count"]) for item in metrics),
        "total_frames_retained": sum(int(item["frame_count"]) for item in metrics),
        "total_asr_segments": sum(int(item["transcript_segment_count"]) for item in metrics),
        "total_ocr_spans": sum(int(item["ocr_span_count"]) for item in metrics),
        "stage_status_counts": dict(stage_status_counts),
        "quality_by_stratum": quality_slices,
        "status_note": (
            "Byte totals are per-file input size plus generated JSON/keyframe artifact sizes; "
            "they are not physical disk I/O counters. Wall time excludes human review, "
            "licensing, cloud billing and any costs not measured by this local run."
        ),
    }
    with (output_dir / "processing_metrics.jsonl").open("w", encoding="utf-8") as handle:
        for item in metrics:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    columns = [
        "record_id", "platform", "language", "topic", "speech_mode", "duration_band",
        "status", "wall_seconds", "input_file_bytes",
        "report_json_bytes", "artifact_bytes_written", "frame_count",
        "cut_candidate_count", "transcript_segment_count", "ocr_span_count",
        "model_training_permitted", "resumed", "error",
    ]
    with (output_dir / "processing_metrics.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for item in metrics:
            writer.writerow({key: item.get(key) for key in columns})
    write_json(output_dir / "processing_summary.json", summary)
    return summary
