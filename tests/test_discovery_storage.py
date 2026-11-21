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
        assert store.eligible_candidates(limit=10) == []


def test_failed_download_remains_retryable(tmp_path: Path):
    with DiscoveryStore(tmp_path / "retry.sqlite3") as store:
        store.start_run("run-retry", 10, 1_000_000)
        store.upsert_candidate(_candidate(), min_views=1_000_000, run_id="run-retry")
        store.mark_download_failure("youtube", "AbCdEfGh123", error="temporary network failure")
        candidates = store.eligible_candidates(limit=10)
        assert len(candidates) == 1
        assert candidates[0].source_id == "AbCdEfGh123"


def test_partial_repeat_does_not_downgrade_previous_metrics(tmp_path: Path):
    candidate = _candidate(1_500_000)
    incomplete_repeat = DiscoveredCandidate(
        platform="youtube",
        source_id="AbCdEfGh123",
        canonical_url="https://www.youtube.com/watch?v=AbCdEfGh123",
        view_count=None,
        duration_seconds=None,
        short_format_status="unknown",
    )
    with DiscoveryStore(tmp_path / "metadata-preserve.sqlite3") as store:
        store.start_run("run-initial", 10, 1_000_000)
        is_new, became_eligible = store.upsert_candidate(
            candidate, min_views=1_000_000, run_id="run-initial"
        )
        assert is_new is True
        assert became_eligible is True
        store.start_run("run-repeat", 10, 1_000_000)
        is_new, became_eligible = store.upsert_candidate(
            incomplete_repeat, min_views=1_000_000, run_id="run-repeat"
        )
        saved = store.get_candidate("youtube", "AbCdEfGh123")
        assert is_new is False
        assert became_eligible is False
        assert saved is not None
        assert saved.view_count == 1_500_000
        assert saved.short_format_status == "confirmed"
        assert saved.status == "eligible"


def test_summary_by_platform_separates_youtube_and_instagram(tmp_path: Path):
    instagram = DiscoveredCandidate(
        platform="instagram",
        source_id="ReelCode123",
        canonical_url="https://www.instagram.com/reel/ReelCode123/",
        view_count=None,
        short_format_status="confirmed",
    )
    with DiscoveryStore(tmp_path / "platform-summary.sqlite3") as store:
        store.start_run("run-summary", 10, 1_000_000)
        store.upsert_candidate(_candidate(), min_views=1_000_000, run_id="run-summary")
        store.upsert_candidate(instagram, min_views=1_000_000, run_id="run-summary")
        counts = store.summary_by_platform()
        assert counts["youtube"]["eligible"] == 1
        assert counts["instagram"]["metric_unknown"] == 1


def test_query_history_is_persisted_and_updated_by_query_key(tmp_path: Path):
    from datetime import UTC, datetime

    with DiscoveryStore(tmp_path / "query-history.sqlite3") as store:
        store.record_query(
            platform="youtube",
            query_key="query-abc",
            query="cricket shorts",
            language="en",
            region="IN",
            strategy="localized_topic",
            raw_results=50,
            candidate_count=42,
            run_at=datetime(2026, 11, 1, tzinfo=UTC),
        )
        history = store.query_history("youtube")
        assert "query-abc" in history
        first_run = history["query-abc"]

        store.record_query(
            platform="youtube",
            query_key="query-abc",
            query="cricket shorts",
            language="en",
            region="IN",
            strategy="localized_topic",
            raw_results=50,
            candidate_count=35,
            run_at=datetime(2026, 11, 21, tzinfo=UTC),
        )
        refreshed = store.query_history("youtube")
        assert refreshed["query-abc"] != first_run
        assert store.query_summary() == {"youtube": 1}
        performance = store.query_performance("youtube")
        assert performance["query-abc"]["run_count"] == 2
        assert performance["query-abc"]["raw_results"] == 50
        assert performance["query-abc"]["candidate_count"] == 38


def test_candidate_format_is_not_eligible_until_confirmed(tmp_path: Path):
    uncertain = DiscoveredCandidate(
        platform="youtube",
        source_id="Uncertain123",
        canonical_url="https://www.youtube.com/watch?v=Uncertain123",
        view_count=2_500_000,
        short_format_status="candidate",
    )
    with DiscoveryStore(tmp_path / "strict-format.sqlite3") as store:
        store.start_run("run-format", 10, 1_000_000)
        store.upsert_candidate(
            uncertain, min_views=1_000_000, run_id="run-format"
        )
        saved = store.get_candidate("youtube", "Uncertain123")
        assert saved is not None
        assert saved.status == "format_unknown"
        assert store.eligible_candidates() == []


def test_legacy_eligible_uncertain_format_is_migrated(tmp_path: Path):
    path = tmp_path / "legacy.sqlite3"
    with DiscoveryStore(path) as store:
        store.start_run("run-legacy", 10, 1_000_000)
        candidate = DiscoveredCandidate(
            platform="youtube",
            source_id="Legacy12345",
            canonical_url="https://www.youtube.com/watch?v=Legacy12345",
            view_count=2_000_000,
            short_format_status="candidate",
        )
        store.upsert_candidate(
            candidate, min_views=1_000_000, run_id="run-legacy"
        )
        store.connection.execute(
            "UPDATE candidates SET status='eligible' WHERE source_id='Legacy12345'"
        )
        store.connection.commit()
    with DiscoveryStore(path) as migrated:
        saved = migrated.get_candidate("youtube", "Legacy12345")
        assert saved is not None
        assert saved.status == "format_unknown"
        assert migrated.eligible_candidates() == []


def test_instagram_play_count_never_substitutes_for_view_count(tmp_path: Path):
    instagram = DiscoveredCandidate(
        platform="instagram",
        source_id="PlayCount123",
        canonical_url="https://www.instagram.com/reel/PlayCount123/",
        view_count=None,
        play_count=3_000_000,
        metric_source="instaloader_video_play_count",
        short_format_status="confirmed",
    )
    with DiscoveryStore(tmp_path / "play-count-is-not-views.sqlite3") as store:
        store.start_run("run-play-count", 10, 1_000_000)
        store.upsert_candidate(
            instagram, min_views=1_000_000, run_id="run-play-count"
        )
        saved = store.get_candidate("instagram", "PlayCount123")
        assert saved is not None
        assert saved.play_count == 3_000_000
        assert saved.view_count is None
        assert saved.status == "metric_unknown"
        assert store.eligible_candidates() == []
