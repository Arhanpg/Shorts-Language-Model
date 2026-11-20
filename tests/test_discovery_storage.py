from pathlib import Path

from shorts_intelligence.discovery.models import DiscoveredCandidate
from shorts_intelligence.discovery.storage import DiscoveryStore


def _candidate(view_count: int | None = 1_300_000, *, source_id: str = "AbCdEfGh123"):
    return DiscoveredCandidate(
        platform="youtube",
        source_id=source_id,
        canonical_url=f"https://www.youtube.com/shorts/{source_id}",
        view_count=view_count,
        short_format_status="confirmed",
    )


def test_sqlite_deduplicates_platform_identity(tmp_path: Path):
    with DiscoveryStore(tmp_path / "discovery.sqlite3") as store:
        store.start_run("run-1", 100, 1_000_000)
        first = store.upsert_candidate(_candidate(), min_views=1_000_000, run_id="run-1")
        second = store.upsert_candidate(_candidate(), min_views=1_000_000, run_id="run-1")
        assert first == (True, True)
        assert second == (False, False)
        assert len(store.eligible_candidates()) == 1
        store.finish_run("run-1", {"scanned": 2, "new_eligible": 1, "duplicates": 1})


def test_view_threshold_filters_below_threshold(tmp_path: Path):
    with DiscoveryStore(tmp_path / "discovery.sqlite3") as store:
        store.start_run("run-2", 100, 1_000_000)
        store.upsert_candidate(_candidate(999_999), min_views=1_000_000, run_id="run-2")
        assert store.summary()["below_threshold"] == 1
        assert store.eligible_candidates() == []


def test_unknown_view_count_is_not_eligible(tmp_path: Path):
    with DiscoveryStore(tmp_path / "discovery.sqlite3") as store:
        store.start_run("run-3", 100, 1_000_000)
        store.upsert_candidate(_candidate(None), min_views=1_000_000, run_id="run-3")
        assert store.summary()["metric_unknown"] == 1
