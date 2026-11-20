"""Combine pilot preparation and extraction metrics into a reproducible report."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from shorts_intelligence.pilot.manifest import write_json


def _csv_data_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", newline="", encoding="utf-8") as handle:
        return max(0, sum(1 for _ in csv.reader(handle)) - 1)


def build_pilot_report(pilot_dir: Path, output_path: Path) -> dict[str, Any]:
    selection_path = pilot_dir / "selection_report.json"
    processing_path = pilot_dir / "processing_summary.json"
    if not selection_path.exists():
        raise FileNotFoundError(f"Missing {selection_path.name}; run pilot sample first.")
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    processing = (
        json.loads(processing_path.read_text(encoding="utf-8"))
        if processing_path.exists() else None
    )
    pair_count = _csv_data_rows(pilot_dir / "matched_pairs.csv")
    review_count = _csv_data_rows(pilot_dir / "review_queue.csv")

    report = {
        "schema_version": "1.0.0",
        "pilot_target": selection.get("target"),
        "selected_records": selection.get("selected"),
        "candidate_pool": selection.get("candidate_pool"),
        "selection_seed": selection.get("seed"),
        "creator_groups": selection.get("unique_creator_groups_in_selection"),
        "creator_relative_unscored": selection.get("unscored_creator_relative_records"),
        "matched_pairs": pair_count,
        "human_review_queue_records": review_count,
        "coverage": selection.get("coverage", {}),
        "processing": processing,
        "interpretation": [
            "Marginal stratification is a selection heuristic, not a probability sample.",
            "Creator-relative outcomes are observational associations, not causal effects.",
            "Raw views/plays are not directly comparable across platforms or metric definitions.",
            "Only records with model_training_permitted=true may enter model training.",
            "Review queue rows are drafts; annotations are not gold labels until human-approved.",
        ],
        "phase_2_exit_status": (
            "awaiting_local_300_video_validation"
            if not processing or processing.get("processed_records", 0) < selection.get("target", 300)
            else "processing_complete_human_review_and_quality_audit_required"
        ),
    }
    write_json(output_path, report)
    return report
