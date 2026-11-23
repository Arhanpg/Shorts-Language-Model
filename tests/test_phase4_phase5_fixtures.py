"""Contract tests for synthetic Phase 4/5 annotation fixtures (not model scoring)."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "phase4_phase5_synthetic_test_cases.jsonl"


def load_cases() -> list[dict]:
    return [
        json.loads(line)
        for line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_fixture_inventory_is_well_formed_and_synthetic() -> None:
    cases = load_cases()
    assert len(cases) == 15
    assert len({case["test_case_id"] for case in cases}) == len(cases)
    assert all(
        case["fixture_type"] == "SYNTHETIC_METADATA_ONLY_CONTRACT_FIXTURE"
        for case in cases
    )
    assert all(case["media_asset_included"] is False for case in cases)
    assert all(case["human_annotated"] is False for case in cases)
    assert all(case["model_evaluation_eligible"] is False for case in cases)


def test_fixture_pack_covers_required_annotation_groups() -> None:
    counts = Counter(case["test_group"] for case in load_cases())
    required = {
        "language_and_script",
        "asr_ocr_audio_quality",
        "editing_and_temporal_grounding",
        "hook_and_narrative",
        "metrics_and_rights",
        "deduplication",
        "safety_and_governance",
    }
    assert required.issubset(counts)


def test_language_fixtures_preserve_native_script_and_code_switching() -> None:
    cases = load_cases()
    assert any(
        case["language"] == "kn"
        and "ಕನ್ನಡ" in case["inputs"].get("synthetic_transcript", "")
        for case in cases
    )
    assert any(
        case["language"] == "kn-Latn"
        and "lets go" in case["inputs"].get("synthetic_transcript", "")
        for case in cases
    )


def test_instagram_metric_is_not_collapsed_into_youtube_views() -> None:
    case = next(
        case for case in load_cases() if case["inputs"].get("metric_kind") == "plays"
    )
    assert case["platform"] == "instagram"
    assert case["expected"]["do_not_rename_as_views"] is True


def test_rights_fixtures_enforce_default_deny_and_scope_separation() -> None:
    rights_cases = [
        case
        for case in load_cases()
        if case["test_group"] == "metrics_and_rights"
        and "rights_gate" in case["expected"]
    ]
    gates = {case["expected"]["rights_gate"] for case in rights_cases}
    assert "BLOCK_DOWNLOAD_AND_TRAINING" in gates
    assert "BLOCK_MEDIA_ACQUISITION" in gates


def test_child_content_and_access_restrictions_are_safe() -> None:
    cases = [case for case in load_cases() if case["test_group"] == "safety_and_governance"]
    assert all(case["expected"].get("minor_pii_collected", False) is False for case in cases)
    assert all(case["expected"].get("bypass_attempt", False) is False for case in cases)
    assert all(case["expected"].get("proxy_or_identity_rotation", False) is False for case in cases)
