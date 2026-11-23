#!/usr/bin/env python3
"""Materialize a completed discovery-seed build as Git-tracked CSV datasets."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ARTIFACT_CSVS = (
    "youtube_channel_candidates.csv",
    "instagram_account_candidates.csv",
    "instagram_person_candidates.csv",
    "instagram_organization_publisher_candidates.csv",
    "hashtags_generated_candidates.csv",
)
CREATOR_SOURCE = "creators_ai_research_leads_v0.1.csv"
HASHTAG_SOURCE = "hashtags_ai_research_candidates_v0.1.csv"
MASTER_FIELDS = [
    "hashtag_id", "hashtag", "normalized_hashtag", "language", "language_code",
    "region", "category", "subcategory", "candidate_platform_scope", "generation_rule",
    "related_hashtags", "search_urls", "source_records", "source_dataset",
    "source_reported_verification_status", "verification_state", "frequency_measured_at",
    "native_speaker_review_status", "priority_reported", "notes",
]


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        return rows, list(reader.fieldnames)


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def normalize_tag(row: dict[str, str]) -> str:
    value = (row.get("normalized_hashtag") or row.get("hashtag") or "").strip().casefold()
    return value.removeprefix("#").strip()


def map_generated(row: dict[str, str]) -> dict[str, str]:
    return {
        "hashtag_id": row.get("hashtag_id", ""),
        "hashtag": row.get("hashtag", ""),
        "normalized_hashtag": normalize_tag(row),
        "language": row.get("language", ""),
        "language_code": row.get("language_code", ""),
        "region": "",
        "category": row.get("category", ""),
        "subcategory": "",
        "candidate_platform_scope": row.get("candidate_platform_scope", ""),
        "generation_rule": row.get("generation_rule", ""),
        "related_hashtags": "",
        "search_urls": row.get("source_url", ""),
        "source_records": "",
        "source_dataset": "Shorts-LM 71-language x 30-domain composition v0.2",
        "source_reported_verification_status": "",
        "verification_state": row.get("verification_state", "GENERATED_UNVERIFIED_COMPOSITIONAL_CANDIDATE"),
        "frequency_measured_at": row.get("frequency_measured_at", ""),
        "native_speaker_review_status": row.get("native_speaker_review_status", "PENDING"),
        "priority_reported": "",
        "notes": row.get("notes", ""),
    }


def map_ai(row: dict[str, str]) -> dict[str, str]:
    return {
        "hashtag_id": row.get("hashtag_id", ""),
        "hashtag": row.get("hashtag", ""),
        "normalized_hashtag": normalize_tag(row),
        "language": row.get("language", ""),
        "language_code": row.get("language_code", ""),
        "region": row.get("region", ""),
        "category": row.get("category", ""),
        "subcategory": row.get("subcategory", ""),
        "candidate_platform_scope": row.get("candidate_platform_scope", ""),
        "generation_rule": "",
        "related_hashtags": row.get("related_hashtags", ""),
        "search_urls": row.get("search_urls", ""),
        "source_records": row.get("source_records", ""),
        "source_dataset": row.get("source_dataset", "submitted_AI_research"),
        "source_reported_verification_status": row.get("source_reported_verification_status", ""),
        "verification_state": row.get("verification_state", "UNVERIFIED_CANDIDATE_NO_MEASURED_FREQUENCY"),
        "frequency_measured_at": row.get("frequency_measured_at", ""),
        "native_speaker_review_status": row.get("native_speaker_review_status", "PENDING"),
        "priority_reported": row.get("priority_reported", ""),
        "notes": row.get("notes", ""),
    }


def row_count(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return sum(1 for _ in csv.DictReader(stream))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def materialize(artifact_dir: Path, research_dir: Path, output_dir: Path, source_run_id: int) -> dict[str, Any]:
    required = [artifact_dir / name for name in ARTIFACT_CSVS]
    required += [
        artifact_dir / "QA_SUMMARY.json",
        research_dir / CREATOR_SOURCE,
        research_dir / HASHTAG_SOURCE,
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing required source files:\n" + "\n".join(missing))

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for name in ARTIFACT_CSVS:
        shutil.copy2(artifact_dir / name, output_dir / name)
    shutil.copy2(research_dir / CREATOR_SOURCE, output_dir / CREATOR_SOURCE)
    shutil.copy2(research_dir / HASHTAG_SOURCE, output_dir / "hashtags_ai_research_candidates.csv")
    shutil.copy2(artifact_dir / "QA_SUMMARY.json", output_dir / "SOURCE_BUILD_QA_SUMMARY.json")

    instagram, instagram_fields = read_csv(output_dir / "instagram_account_candidates.csv")
    unknown = [
        row for row in instagram
        if (row.get("entity_type") or "").casefold() not in {"person", "organization"}
    ]
    write_csv(output_dir / "instagram_unknown_entity_leads.csv", unknown, instagram_fields)

    generated, _ = read_csv(output_dir / "hashtags_generated_candidates.csv")
    ai, _ = read_csv(output_dir / "hashtags_ai_research_candidates.csv")
    union: OrderedDict[str, dict[str, str]] = OrderedDict()
    for source_row in generated:
        mapped = map_generated(source_row)
        key = normalize_tag(mapped)
        if key:
            union.setdefault(key, mapped)
    for source_row in ai:
        mapped = map_ai(source_row)
        key = normalize_tag(mapped)
        if not key:
            continue
        current = union.get(key)
        if current is None or mapped.get("source_records") or mapped.get("frequency_measured_at"):
            union[key] = mapped
    write_csv(output_dir / "hashtags_master_candidates.csv", list(union.values()), MASTER_FIELDS)

    with (output_dir / "SOURCE_BUILD_QA_SUMMARY.json").open("r", encoding="utf-8") as stream:
        source_summary = json.load(stream)
    creators, _ = read_csv(output_dir / CREATOR_SOURCE)
    ai_norms = {normalize_tag(row) for row in ai if normalize_tag(row)}
    generated_norms = {normalize_tag(row) for row in generated if normalize_tag(row)}

    counts = {
        "youtube_channel_candidates": row_count(output_dir / "youtube_channel_candidates.csv"),
        "instagram_account_candidates": len(instagram),
        "instagram_person_candidates": sum((r.get("entity_type") or "").casefold() == "person" for r in instagram),
        "instagram_organization_publisher_candidates": sum((r.get("entity_type") or "").casefold() == "organization" for r in instagram),
        "instagram_unknown_entity_leads": len(unknown),
        "submitted_ai_creator_platform_leads": len(creators),
        "generated_hashtag_candidates": len(generated),
        "submitted_ai_hashtag_rows": len(ai),
        "submitted_ai_hashtag_unique_normalized": len(ai_norms),
        "generated_hashtag_unique_normalized": len(generated_norms),
        "unique_normalized_hashtag_union": len(union),
    }
    inventory: dict[str, Any] = {}
    for path in sorted(output_dir.glob("*.csv")):
        inventory[path.name] = {
            "rows": row_count(path),
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        }

    summary = {
        "release": "Shorts-LM Git-tracked seed catalogue v0.2",
        "materialized_at": datetime.now(UTC).isoformat(),
        "source_github_actions_run_id": source_run_id,
        "source_github_actions_artifact": "shorts-lm-large-seed-catalogue-v0.2",
        "source_build_generated_at": source_summary.get("generated_at"),
        "counts": counts,
        "files": inventory,
        "source_datasets": source_summary.get("sources", {}),
        "limitations": [
            "Account rows are discovery candidates, not confirmed active Shorts/Reels publishers.",
            "YouTube channel entity type is not reliably classified as person or organization.",
            "Instagram person, organization and unknown-entity rows are kept separate.",
            "Cross-platform account rows are not equivalent to unique human identities.",
            "AI creator and hashtag verification labels are source-reported, not independently confirmed.",
            "Generated hashtags have no measured popularity or retrieval-yield evidence until tested.",
            "Public profile visibility and dataset compilation licences do not grant video-download, retention or model-training rights.",
        ],
    }
    (output_dir / "QA_SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--research-dir", type=Path, default=Path("data/research_catalogue"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/seed_catalogue/v0.2"))
    parser.add_argument("--source-run-id", type=int, default=45203258030)
    args = parser.parse_args()
    try:
        result = materialize(args.artifact_dir, args.research_dir, args.output_dir, args.source_run_id)
    except (OSError, ValueError, csv.Error, json.JSONDecodeError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")
    print(json.dumps({"counts": result["counts"], "files": list(result["files"])}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
