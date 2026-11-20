"""Deterministic multi-axis sampling and creator-relative performance features."""

from __future__ import annotations

import csv
import hashlib
import hmac
import math
import os
import random
from collections import Counter, defaultdict
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from statistics import median

from shorts_intelligence.pilot.manifest import ValidatedCandidate, write_json
from shorts_intelligence.pilot.schemas import SelectedRecord

DIMENSIONS = (
    "platform", "language", "topic", "duration_band", "performance_tier", "speech_mode",
)


def duration_band(seconds: float) -> str:
    if seconds <= 15:
        return "00-15s"
    if seconds <= 30:
        return "16-30s"
    if seconds <= 60:
        return "31-60s"
    return "60s+"


def age_band(published_at: datetime | None, observed_at: datetime | None) -> str:
    if not published_at or not observed_at:
        return "unknown"
    days = max(0, (observed_at - published_at).total_seconds() / 86400)
    if days <= 7:
        return "00-07d"
    if days <= 30:
        return "08-30d"
    if days <= 90:
        return "31-90d"
    return "90d+"


def create_or_load_salt(path: Path) -> bytes:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        salt = path.read_bytes()
        if len(salt) < 32:
            raise ValueError("Creator salt file must contain at least 32 random bytes.")
        return salt
    salt = os.urandom(32)
    path.write_bytes(salt)
    with suppress(OSError):
        os.chmod(path, 0o600)
    return salt


def pseudonymize_creator(platform: str, creator_id: str | None, salt: bytes) -> str | None:
    if not creator_id or not creator_id.strip():
        return None
    message = f"{platform}:{creator_id.strip()}".encode()
    return hmac.new(salt, message, hashlib.sha256).hexdigest()[:24]


def _relative_performance(
    candidates: list[ValidatedCandidate], creator_groups: dict[str, str | None]
) -> dict[str, tuple[float, float, str]]:
    groups: dict[tuple[str, str, str, str, str], list[tuple[ValidatedCandidate, float]]] = defaultdict(list)
    for candidate in candidates:
        record = candidate.record
        snapshot = record.performance
        creator = creator_groups.get(record.record_id)
        if not creator or not snapshot or not record.published_at:
            continue
        group_age = age_band(record.published_at, snapshot.observed_at)
        key = (
            creator, record.platform, record.language, record.topic,
            f"{snapshot.metric_name}:{group_age}",
        )
        groups[key].append((candidate, math.log1p(snapshot.value)))

    result: dict[str, tuple[float, float, str]] = {}
    for rows in groups.values():
        if len(rows) < 3:
            continue
        baseline = median(value for _, value in rows)
        for candidate, log_value in rows:
            difference = log_value - baseline
            multiple = math.exp(max(-30.0, min(30.0, difference)))
            if multiple < 0.5:
                tier = "below_baseline"
            elif multiple < 2.0:
                tier = "typical"
            elif multiple < 5.0:
                tier = "breakout_2x_5x"
            elif multiple < 20.0:
                tier = "strong_5x_20x"
            else:
                tier = "extreme_20x_plus"
            result[candidate.record.record_id] = (difference, multiple, tier)
    return result


def _performance_bucket(
    candidate: ValidatedCandidate,
    relative: dict[str, tuple[float, float, str]],
) -> str:
    scored = relative.get(candidate.record.record_id)
    if scored:
        return scored[2]
    if not candidate.record.performance:
        return "unknown"
    value = candidate.record.performance.value
    if value < 10_000:
        return "raw_lt10k"
    if value < 100_000:
        return "raw_10k_100k"
    if value < 1_000_000:
        return "raw_100k_1m"
    return "raw_1m_plus"


def _candidate_dimensions(
    candidate: ValidatedCandidate,
    relative: dict[str, tuple[float, float, str]],
) -> dict[str, str]:
    record = candidate.record
    return {
        "platform": record.platform,
        "language": record.language,
        "topic": record.topic,
        "duration_band": duration_band(candidate.duration_seconds),
        "performance_tier": _performance_bucket(candidate, relative),
        "speech_mode": record.speech_mode,
    }


def _quotas(values: Counter[str], target: int) -> dict[str, int]:
    total = sum(values.values())
    if total == 0:
        return {}
    exact = {key: target * count / total for key, count in values.items()}
    result = {key: int(math.floor(value)) for key, value in exact.items()}
    left = target - sum(result.values())
    order = sorted(
        exact,
        key=lambda name: (exact[name] - result[name], name),
        reverse=True,
    )
    for key in order[:left]:
        result[key] += 1
    return result


def select_stratified(
    candidates: list[ValidatedCandidate],
    *,
    target: int,
    seed: int = 42,
    max_per_creator: int = 5,
    salt: bytes,
) -> tuple[list[SelectedRecord], dict[str, object]]:
    """Greedy marginal-quota sampler with deterministic tie-breaking."""
    if target < 1:
        raise ValueError("target must be at least one")
    if not candidates:
        raise ValueError("No rights-eligible candidates were supplied.")
    if len(candidates) < target:
        raise ValueError(
            f"Only {len(candidates)} eligible unique videos are available for target {target}."
        )
    rng = random.Random(seed)
    creator_groups = {
        item.record.record_id: pseudonymize_creator(
            item.record.platform, item.record.creator_id, salt
        )
        for item in candidates
    }
    relative = _relative_performance(candidates, creator_groups)
    dimensions = {
        item.record.record_id: _candidate_dimensions(item, relative)
        for item in candidates
    }
    marginal = {
        dimension: Counter(values[dimension] for values in dimensions.values())
        for dimension in DIMENSIONS
    }
    quotas = {
        dimension: _quotas(marginal[dimension], target)
        for dimension in DIMENSIONS
    }

    shuffled = candidates[:]
    rng.shuffle(shuffled)
    creator_counts: Counter[str] = Counter()
    selected_counts = {dimension: Counter() for dimension in DIMENSIONS}
    remaining = shuffled[:]
    chosen: list[ValidatedCandidate] = []
    while remaining and len(chosen) < target:
        best_index = -1
        best_score = float("-inf")
        best_tie = -1.0
        for index, item in enumerate(remaining):
            creator = creator_groups[item.record.record_id]
            if max_per_creator > 0 and creator and creator_counts[creator] >= max_per_creator:
                continue
            score = 0.0
            for dimension in DIMENSIONS:
                value = dimensions[item.record.record_id][dimension]
                quota = quotas[dimension].get(value, 0)
                deficit = quota - selected_counts[dimension][value]
                if deficit > 0:
                    score += deficit / max(quota, 1)
            tie = rng.random()
            if score > best_score or (score == best_score and tie > best_tie):
                best_index, best_score, best_tie = index, score, tie
        if best_index < 0:
            break
        item = remaining.pop(best_index)
        chosen.append(item)
        creator = creator_groups[item.record.record_id]
        if creator:
            creator_counts[creator] += 1
        for dimension in DIMENSIONS:
            selected_counts[dimension][dimensions[item.record.record_id][dimension]] += 1

    selected: list[SelectedRecord] = []
    for item in chosen:
        record = item.record
        snapshot = record.performance
        relative_value = relative.get(record.record_id)
        selected.append(SelectedRecord(
            record_id=record.record_id,
            platform=record.platform,
            media_path=str(item.media_path),
            media_sha256=item.media_sha256,
            file_size_bytes=item.file_size_bytes,
            creator_group=creator_groups[record.record_id],
            rights_basis=record.rights.basis,
            rights_reference_hash=hashlib.sha256(
                record.rights.evidence_ref.encode("utf-8")
            ).hexdigest(),
            rights_expires_at=record.rights.expires_at,
            media_analysis_permitted=record.rights.media_analysis,
            temporary_processing_permitted=record.rights.temporary_processing,
            derived_artifact_retention_permitted=record.rights.derived_artifact_retention,
            model_training_permitted=record.rights.model_training,
            language=record.language,
            topic=record.topic,
            speech_mode=record.speech_mode,
            published_at=record.published_at,
            duration_seconds=item.duration_seconds,
            duration_band=duration_band(item.duration_seconds),
            age_band=age_band(record.published_at, snapshot.observed_at if snapshot else None),
            metric_name=snapshot.metric_name if snapshot else None,
            metric_value=snapshot.value if snapshot else None,
            observed_at=snapshot.observed_at if snapshot else None,
            creator_relative_log_score=relative_value[0] if relative_value else None,
            creator_relative_multiple=relative_value[1] if relative_value else None,
            performance_tier=relative_value[2] if relative_value else _performance_bucket(item, relative),
        ))

    coverage: dict[str, dict[str, dict[str, float | int]]] = {}
    for dimension in DIMENSIONS:
        categories: dict[str, dict[str, float | int]] = {}
        for category, population in sorted(marginal[dimension].items()):
            count = selected_counts[dimension].get(category, 0)
            categories[category] = {
                "candidate_count": population,
                "selected_count": count,
                "selected_share": round(count / max(len(chosen), 1), 4),
                "candidate_share": round(population / len(candidates), 4),
                "target_quota": quotas[dimension].get(category, 0),
            }
        coverage[dimension] = categories

    summary: dict[str, object] = {
        "target": target,
        "selected": len(selected),
        "shortfall": max(0, target - len(selected)),
        "seed": seed,
        "max_per_creator": max_per_creator,
        "candidate_pool": len(candidates),
        "unique_creator_groups_in_selection": len({
            item.creator_group for item in selected if item.creator_group
        }),
        "unscored_creator_relative_records": sum(
            1 for item in selected if item.creator_relative_multiple is None
        ),
        "training_permitted_records": sum(
            1 for item in selected if item.model_training_permitted
        ),
        "selected_record_ids": [item.record_id for item in selected],
        "coverage": coverage,
        "note": (
            "Marginal stratification is a coverage heuristic, not a probability sample. "
            "Retain candidate-pool counts and selection weights for population inference."
        ),
    }
    return selected, summary


def write_selection_outputs(
    output_dir: Path,
    selected: list[SelectedRecord],
    summary: dict[str, object],
    pairs: list[dict[str, object]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "selected_manifest.jsonl").open("w", encoding="utf-8") as handle:
        for item in selected:
            handle.write(item.model_dump_json(exclude_none=False) + "\n")
    write_json(output_dir / "selection_report.json", summary)

    coverage = summary.get("coverage", {})
    with (output_dir / "coverage.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "dimension", "category", "candidate_count", "selected_count",
            "candidate_share", "selected_share", "target_quota",
        ])
        for dimension, categories in coverage.items():  # type: ignore[union-attr]
            for category, counts in categories.items():
                writer.writerow([
                    dimension, category, counts["candidate_count"],
                    counts["selected_count"], counts["candidate_share"],
                    counts["selected_share"], counts["target_quota"],
                ])

    with (output_dir / "matched_pairs.csv").open("w", newline="", encoding="utf-8") as handle:
        columns = [
            "pair_id", "positive_record_id", "control_record_id", "creator_group",
            "platform", "language", "topic", "positive_relative_multiple",
            "control_relative_multiple", "publication_gap_days",
            "duration_gap_fraction", "matching_rule",
        ]
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for pair in pairs:
            writer.writerow(pair)

    with (output_dir / "review_queue.csv").open("w", newline="", encoding="utf-8") as handle:
        columns = [
            "record_id", "platform", "creator_group", "language", "topic",
            "duration_seconds", "performance_tier", "creator_relative_multiple",
            "hook_type", "hook_start_seconds", "hook_end_seconds",
            "editing_events", "ocr_correct", "asr_correct", "audio_mode",
            "summary_correct", "reviewer_id", "review_status", "review_notes",
        ]
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for item in selected:
            writer.writerow({
                "record_id": item.record_id,
                "platform": item.platform,
                "creator_group": item.creator_group,
                "language": item.language,
                "topic": item.topic,
                "duration_seconds": item.duration_seconds,
                "performance_tier": item.performance_tier,
                "creator_relative_multiple": item.creator_relative_multiple,
                "review_status": "not_started",
            })
