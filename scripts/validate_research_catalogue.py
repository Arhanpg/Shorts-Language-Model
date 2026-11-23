#!/usr/bin/env python3
"""Validate a locally installed Shorts-LM research catalogue release."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


REQUIRED = (
    "languages.csv",
    "categories.csv",
    "creators.csv",
    "regional_creators.csv",
    "gemini_regional_handle_leads.csv",
    "hashtags.csv",
    "discovery_queries.csv",
    "diversity_matrix.csv",
    "gemini_diversity_strata.csv",
    "acquisition_priorities.csv",
    "research_sources.csv",
    "source_reconciliation.csv",
    "rights-provenance.schema.json",
    "discovery_sampling_policy.json",
    "phase4_phase5_synthetic_test_cases.jsonl",
    "QA_SUMMARY.json",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def validate_catalogue(root: Path) -> list[str]:
    errors: list[str] = []
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    if missing:
        return [f"Missing required files: {', '.join(missing)}"]

    try:
        summary = json.loads((root / "QA_SUMMARY.json").read_text(encoding="utf-8"))
        rights_schema = json.loads(
            (root / "rights-provenance.schema.json").read_text(encoding="utf-8")
        )
        policy = json.loads((root / "discovery_sampling_policy.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Invalid JSON or unreadable file: {exc}"]

    table_names = (
        "languages",
        "categories",
        "creators",
        "regional_creators",
        "hashtags",
        "discovery_queries",
        "diversity_matrix",
    )
    tables: dict[str, list[dict[str, str]]] = {}
    for name in table_names:
        try:
            tables[name] = read_csv(root / f"{name}.csv")
        except (OSError, csv.Error, UnicodeDecodeError) as exc:
            errors.append(f"{name}.csv cannot be read as UTF-8 CSV: {exc}")

    def check_unique(rows: list[dict[str, str]], field: str, label: str) -> None:
        values = [row.get(field, "") for row in rows]
        if any(not value for value in values):
            errors.append(f"{label} has blank {field} values")
        if len(values) != len(set(values)):
            errors.append(f"{label} has duplicate {field} values")

    if "languages" in tables:
        check_unique(tables["languages"], "language_id", "languages.csv")
    if "categories" in tables:
        category_ids = {row.get("category_id", "") for row in tables["categories"]}
        if len(category_ids) != 30:
            errors.append(f"Expected 30 canonical category IDs, found {len(category_ids)}")
    if "creators" in tables:
        check_unique(tables["creators"], "creator_id", "creators.csv")
        if any(
            row.get("rights_status") != "NOT_ASSESSED_DISCOVERY_ONLY"
            for row in tables["creators"]
        ):
            errors.append("Creator records must remain NOT_ASSESSED_DISCOVERY_ONLY")
        if any(row.get("verification_state") == "VERIFIED" for row in tables["creators"]):
            errors.append("Unreviewed creator claims cannot be promoted to VERIFIED")
    if "hashtags" in tables:
        check_unique(tables["hashtags"], "hashtag_id", "hashtags.csv")
        if any(row.get("verification_state") == "VERIFIED" for row in tables["hashtags"]):
            errors.append("Unreviewed hashtag candidates cannot be promoted to VERIFIED")
    if "discovery_queries" in tables:
        check_unique(tables["discovery_queries"], "query_id", "discovery_queries.csv")
        if any(row.get("executed_at") for row in tables["discovery_queries"]):
            errors.append("Generated query candidates must not be marked as executed")

    permissions = rights_schema.get("default_record_policy", {}).get("permissions", {})
    if not permissions or any(value is not False for value in permissions.values()):
        errors.append("Rights schema must default every permission to false")
    if policy.get("rights_gate", {}).get("public_visibility_is_permission") is not False:
        errors.append("Public visibility must not be treated as permission")

    try:
        cases = [
            json.loads(line)
            for line in (root / "phase4_phase5_synthetic_test_cases.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"Synthetic test cases are invalid JSONL: {exc}")
        cases = []
    if not cases:
        errors.append("Synthetic test cases are empty")
    else:
        ids = [case.get("test_case_id") for case in cases]
        if len(ids) != len(set(ids)):
            errors.append("Synthetic test case IDs are not unique")
        for case in cases:
            if case.get("fixture_type") != "SYNTHETIC_METADATA_ONLY_CONTRACT_FIXTURE":
                errors.append(f"{case.get('test_case_id')}: unexpected fixture type")
            if case.get("media_asset_included") is not False:
                errors.append(f"{case.get('test_case_id')}: fixture unexpectedly includes media")
            if case.get("model_evaluation_eligible") is not False:
                errors.append(f"{case.get('test_case_id')}: fixture cannot be a model benchmark")

    counts = summary.get("counts", {})
    actual = {
        "languages": len(tables.get("languages", [])),
        "categories_subcategory_rows": len(tables.get("categories", [])),
        "creators_normalized_leads": len(tables.get("creators", [])),
        "hashtags_deduplicated_candidates": len(tables.get("hashtags", [])),
        "discovery_query_candidates": len(tables.get("discovery_queries", [])),
        "diversity_matrix_proposed_cells": len(tables.get("diversity_matrix", [])),
        "synthetic_test_cases": len(cases),
    }
    for key, value in actual.items():
        if counts.get(key) != value:
            errors.append(f"QA count mismatch for {key}: summary={counts.get(key)}, actual={value}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/research_catalogue/v0.1"))
    args = parser.parse_args()
    errors = validate_catalogue(args.root)
    if errors:
        print("Catalogue validation FAILED:")
        for error in errors:
            print(f" - {error}")
        return 1
    print(f"Catalogue validation passed: {args.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
