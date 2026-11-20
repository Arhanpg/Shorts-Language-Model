"""Manifest loading, permission gates, local-file validation and QA summaries."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shorts_intelligence.config import AnalyzerConfig
from shorts_intelligence.media.probe import MediaError, probe_video, sha256_file
from shorts_intelligence.pilot.schemas import PilotRecord, ValidationIssue, ValidationSummary


@dataclass(slots=True)
class ValidatedCandidate:
    row_number: int
    record: PilotRecord
    media_path: Path
    media_sha256: str
    file_size_bytes: int
    duration_seconds: float


@dataclass(slots=True)
class ManifestValidation:
    candidates: list[ValidatedCandidate]
    summary: ValidationSummary


def _can_analyze(record: PilotRecord, now: datetime) -> tuple[bool, str | None]:
    rights = record.rights
    if rights.revoked:
        return False, "rights_revoked"
    if rights.expires_at and rights.expires_at <= now:
        return False, "rights_expired"
    if not rights.media_analysis:
        return False, "media_analysis_not_permitted"
    if not rights.temporary_processing:
        return False, "temporary_processing_not_permitted"
    if not rights.derived_artifact_retention:
        return False, "derived_artifact_retention_not_permitted"
    return True, None


def load_and_validate_manifest(
    manifest_path: Path,
    *,
    max_file_size_mb: int = 500,
    max_duration_seconds: float = 180.0,
    require_training_rights: bool = False,
    now: datetime | None = None,
) -> ManifestValidation:
    """Validate JSONL candidate records and probe every locally supplied video.

    No URLs are fetched. Media paths are resolved relative to the manifest file.
    Reports omit raw creator IDs, source references, media paths and consent references.
    """
    manifest_path = manifest_path.expanduser().resolve(strict=True)
    if not manifest_path.is_file():
        raise ValueError("Manifest path must be a JSONL file.")
    now = now or datetime.now(timezone.utc)
    config = AnalyzerConfig(
        max_file_size_mb=max_file_size_mb,
        max_duration_seconds=max_duration_seconds,
    )
    candidates: list[ValidatedCandidate] = []
    issues: list[ValidationIssue] = []
    seen_record_ids: set[str] = set()
    seen_media: dict[str, str] = {}
    input_rows = parsed_rows = duplicate_rows = 0
    warnings: list[str] = []

    with manifest_path.open("r", encoding="utf-8") as handle:
        for row_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            input_rows += 1
            try:
                payload: dict[str, Any] = json.loads(line)
                record = PilotRecord.model_validate(payload)
                parsed_rows += 1
            except (json.JSONDecodeError, ValueError) as exc:
                issues.append(ValidationIssue(
                    row_number=row_number,
                    code="invalid_record",
                    message=str(exc).splitlines()[0][:500],
                ))
                continue

            if record.record_id in seen_record_ids:
                issues.append(ValidationIssue(
                    row_number=row_number,
                    record_id=record.record_id,
                    code="duplicate_record_id",
                    message="record_id must be unique within the manifest.",
                ))
                continue
            seen_record_ids.add(record.record_id)

            permitted, reason = _can_analyze(record, now)
            if not permitted:
                issues.append(ValidationIssue(
                    row_number=row_number,
                    record_id=record.record_id,
                    code=reason or "rights_gate_failed",
                    message="Record lacks required current media-analysis capabilities.",
                ))
                continue
            if require_training_rights and not record.rights.model_training:
                issues.append(ValidationIssue(
                    row_number=row_number,
                    record_id=record.record_id,
                    code="model_training_not_permitted",
                    message="This run requires explicit model-training permission.",
                ))
                continue

            candidate_path = Path(record.media_path).expanduser()
            if not candidate_path.is_absolute():
                candidate_path = manifest_path.parent / candidate_path
            try:
                candidate_path = candidate_path.resolve(strict=True)
                if not candidate_path.is_file():
                    raise ValueError("media_path is not a local file.")
                size = candidate_path.stat().st_size
                if size <= 0:
                    raise ValueError("media file is empty.")
                if size > max_file_size_mb * 1024 * 1024:
                    raise ValueError("media file exceeds configured size limit.")
                metadata = probe_video(candidate_path, config)
                media_hash = sha256_file(candidate_path)
            except (OSError, ValueError, MediaError) as exc:
                issues.append(ValidationIssue(
                    row_number=row_number,
                    record_id=record.record_id,
                    code="media_invalid",
                    message=str(exc).splitlines()[0][:500],
                ))
                continue

            previous_id = seen_media.get(media_hash)
            if previous_id:
                duplicate_rows += 1
                issues.append(ValidationIssue(
                    row_number=row_number,
                    record_id=record.record_id,
                    code="duplicate_media",
                    message=f"Content checksum duplicates accepted record {previous_id}.",
                ))
                continue
            seen_media[media_hash] = record.record_id

            if record.performance and not record.published_at:
                warnings.append(
                    f"{record.record_id}: metric snapshot exists but published_at is missing; "
                    "creator-relative analysis will be unavailable."
                )
            if not record.creator_id:
                warnings.append(
                    f"{record.record_id}: creator_id is missing; creator matching is unavailable."
                )

            candidates.append(ValidatedCandidate(
                row_number=row_number,
                record=record,
                media_path=candidate_path,
                media_sha256=media_hash,
                file_size_bytes=size,
                duration_seconds=metadata.duration_seconds,
            ))

    platforms = Counter(item.record.platform for item in candidates)
    languages = Counter(item.record.language for item in candidates)
    topics = Counter(item.record.topic for item in candidates)
    return ManifestValidation(
        candidates=candidates,
        summary=ValidationSummary(
            manifest_path=manifest_path.name,
            input_rows=input_rows,
            parsed_rows=parsed_rows,
            accepted_rows=len(candidates),
            rejected_rows=input_rows - len(candidates),
            duplicate_media_rows=duplicate_rows,
            training_permitted_rows=sum(
                1 for item in candidates if item.record.rights.model_training
            ),
            warnings=warnings,
            issues=issues,
            platform_counts=dict(platforms),
            language_counts=dict(languages),
            topic_counts=dict(topics),
        ),
    )


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(payload, "model_dump_json"):
        content = payload.model_dump_json(indent=2)  # type: ignore[attr-defined]
    else:
        content = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content + "\n", encoding="utf-8")
    temporary.replace(path)


def validation_template_record(
    media_path: str = "media/replace-with-authorized-video.mp4",
) -> dict[str, object]:
    """Example only; placeholder rights evidence must be replaced before use."""
    return {
        "schema_version": "1.0.0",
        "record_id": "clip_0001",
        "platform": "creator_upload",
        "media_path": media_path,
        "source_ref": None,
        "creator_id": "PRIVATE_CREATOR_IDENTIFIER",
        "rights": {
            "basis": "creator_permission",
            "evidence_ref": "REPLACE_WITH_PRIVATE_CONSENT_OR_LICENSE_REFERENCE",
            "media_analysis": True,
            "temporary_processing": True,
            "derived_artifact_retention": True,
            "raw_media_retention": False,
            "model_training": False,
            "public_redistribution": False,
            "expires_at": None,
            "revoked": False,
        },
        "language": "hi",
        "topic": "cricket",
        "speech_mode": "music_only",
        "published_at": "2026-10-01T12:00:00+00:00",
        "performance": {
            "metric_name": "views",
            "value": 120000,
            "observed_at": "2026-11-20T12:00:00+00:00",
            "source": "creator_authorized_snapshot",
        },
    }
