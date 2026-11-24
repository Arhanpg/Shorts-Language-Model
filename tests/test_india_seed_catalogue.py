import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_india_seed_catalogue.py"
SPEC = importlib.util.spec_from_file_location("build_india_seed_catalogue", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

LANGUAGES = MODULE.LANGUAGES
hashtag_rows = MODULE.hashtag_rows


def test_india_hashtag_target_is_exact_and_unique():
    rows = hashtag_rows(1500)
    assert len(rows) == 1500
    assert len({row["normalized_hashtag"] for row in rows}) == 1500
    assert len({row["hashtag_id"] for row in rows}) == 1500


def test_hashtag_scope_covers_all_configured_languages():
    rows = hashtag_rows(1500)
    present = {row["language_code"] for row in rows}
    expected = {language[1] for language in LANGUAGES}
    assert expected.issubset(present)


def test_hashtags_are_unverified_candidates_not_popularity_claims():
    rows = hashtag_rows(100)
    assert all(row["verification_state"] == "GENERATED_UNVERIFIED_CANDIDATE" for row in rows)
    assert all(row["frequency_measured_at"] == "" for row in rows)
