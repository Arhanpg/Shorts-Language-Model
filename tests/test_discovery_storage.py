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


def test_download_sha256_detects_cross_platform_duplicate(tmp_path: Path):
    instagram = DiscoveredCandidate(
        platform="instagram",
        source_id="ReelCode123",
        canonical_url="https://www.instagram.com/reel/ReelCode123/",
        view_count=2_000_000,
        short_format_status="confirmed",
    )
    with DiscoveryStore(tmp_path / "dedup.sqlite3") as store:
        store.start_run("run-youtube", 10, 1_000_000)
        store.start_run("run-instagram", 10, 1_000_000)
        store.upsert_candidate(_candidate(), min_views=1_000_000, run_id="run-youtube")
        store.upsert_candidate(instagram, min_views=1_000_000, run_id="run-instagram")
        store.mark_download(
            "youtube", "AbCdEfGh123",
            path=str(tmp_path / "youtube.mp4"),
            media_sha256="a" * 64,
        )
        duplicate = store.find_media_hash("a" * 64)
        assert duplicate is not None
        assert duplicate["platform"] == "youtube"
        store.mark_duplicate_media(
            "instagram", "ReelCode123",
            duplicate_of="youtube:AbCdEfGh123",
            media_sha256="a" * 64,
        )
        assert store.eligible_candidates(limit=10) == [
            candidate for candidate in store.eligible_candidates(limit=10)
            if candidate.platform == "youtube"
        ]


def test_failed_download_remains_retryable(tmp_path: Path):
    with DiscoveryStore(tmp_path / "retry.sqlite3") as store:
        store.start_run("run-retry", 10, 1_000_000)
        store.upsert_candidate(_candidate(), min_views=1_000_000, run_id="run-retry")
        store.mark_download_failure("youtube", "AbCdEfGh123", error="temporary network failure")
        candidates = store.eligible_candidates(limit=10)
        assert len(candidates) == 1
        assert candidates[0].source_id == "AbCdEfGh123"
