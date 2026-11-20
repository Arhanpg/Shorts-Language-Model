"""Process selected pilot records through Phase 1 and meter actual work."""

from __future__ import annotations

import csv
import json
import time
from collections import Counter
from pathlib import Path

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


def process_selected(
    manifest_path: Path,
    output_dir: Path,
    *,
    limit: int | None = None,
    config: AnalyzerConfig | None = None,
) -> dict[str, object]:
    records = load_selected_manifest(manifest_path)
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        records = records[:limit]
    output_dir.mkdir(parents=True, exist_ok=True)
    telemetry_dir = output_dir / "telemetry"
    telemetry_dir.mkdir(parents=True, exist_ok=True)
    config = config or AnalyzerConfig()
    run_started = time.perf_counter()
    metrics: list[dict[str, object]] = []

    for record in records:
        started = time.perf_counter()
        status = "complete"
        message: str | None = None
        output_path = telemetry_dir / f"{record.record_id}.analysis.json"
        try:
            if not (
                record.media_analysis_permitted
                and record.temporary_processing_permitted
                and record.derived_artifact_retention_permitted
            ):
                raise PermissionError(
                    "Selected record lacks required processing capabilities."
                )
            media_path = Path(record.media_path).expanduser().resolve(strict=True)
            if not media_path.is_file():
                raise FileNotFoundError("Local media path is not a file.")
            current_hash = sha256_file(media_path)
            if current_hash != record.media_sha256:
                raise ValueError("Media SHA-256 changed after manifest validation.")
            if media_path.stat().st_size != record.file_size_bytes:
                raise ValueError("Media file size changed after manifest validation.")
            report = analyze_video(
                input_path=media_path,
                output_path=output_path,
                rights_basis=record.rights_basis,
                rights_reference=record.rights_reference_hash,
                training_permitted=record.model_training_permitted,
                config=config,
            )
            input_bytes = record.file_size_bytes
            output_bytes = output_path.stat().st_size
            frame_count = len(report.frame_evidence)
            cut_count = len(report.cut_candidates)
            asr_count = len(report.transcript_segments)
            ocr_count = len(report.ocr_spans)
            stage_statuses = {
                name: stage.status for name, stage in report.stages.items()
            }
            if any(value == "failed" for value in stage_statuses.values()):
                status = "partial"
        except Exception as exc:
            status = "failed"
            message = f"{type(exc).__name__}: {str(exc)[:500]}"
            input_bytes = record.file_size_bytes
            output_bytes = 0
            frame_count = cut_count = asr_count = ocr_count = 0
            stage_statuses = {}
        elapsed = time.perf_counter() - started
        metrics.append({
            "record_id": record.record_id,
            "status": status,
            "wall_seconds": round(elapsed, 4),
            "input_bytes": input_bytes,
            "report_bytes": output_bytes,
            "frame_count": frame_count,
            "cut_candidate_count": cut_count,
            "transcript_segment_count": asr_count,
            "ocr_span_count": ocr_count,
            "model_training_permitted": record.model_training_permitted,
            "stage_statuses": stage_statuses,
            "error": message,
        })

    run_seconds = time.perf_counter() - run_started
    status_counts = Counter(str(item["status"]) for item in metrics)
    success = status_counts["complete"] + status_counts["partial"]
    input_total = sum(int(item["input_bytes"]) for item in metrics)
    report_total = sum(int(item["report_bytes"]) for item in metrics)
    summary: dict[str, object] = {
        "schema_version": "1.0.0",
        "manifest_name": manifest_path.name,
        "requested_records": len(records),
        "processed_records": len(metrics),
        "complete_records": status_counts["complete"],
        "partial_records": status_counts["partial"],
        "failed_records": status_counts["failed"],
        "success_rate": round(success / max(len(metrics), 1), 4),
        "training_permitted_processed_records": sum(
            1 for item in metrics if item["model_training_permitted"]
        ),
        "total_wall_seconds": round(run_seconds, 3),
        "mean_seconds_per_record": round(run_seconds / max(len(metrics), 1), 3),
        "input_media_bytes_read": input_total,
        "telemetry_report_bytes_written": report_total,
        "total_cut_candidates": sum(int(item["cut_candidate_count"]) for item in metrics),
        "total_frames_retained": sum(int(item["frame_count"]) for item in metrics),
        "total_asr_segments": sum(int(item["transcript_segment_count"]) for item in metrics),
        "total_ocr_spans": sum(int(item["ocr_span_count"]) for item in metrics),
        "status_note": (
            "Wall-clock and byte counts are measured by this run; no cloud, human-review, "
            "licensing or monetary cost has been inferred."
        ),
    }
    with (output_dir / "processing_metrics.jsonl").open("w", encoding="utf-8") as handle:
        for item in metrics:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    columns = [
        "record_id", "status", "wall_seconds", "input_bytes", "report_bytes",
        "frame_count", "cut_candidate_count", "transcript_segment_count",
        "ocr_span_count", "model_training_permitted", "error",
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
