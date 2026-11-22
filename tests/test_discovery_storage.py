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


def test_query_performance_returns_per_platform_average_yield(tmp_path: Path):
    from datetime import UTC, datetime

    with DiscoveryStore(tmp_path / "query-performance.sqlite3") as store:
        for raw, candidates, day in [(50, 42, 1), (50, 35, 21)]:
            store.record_query(
                platform="youtube",
                query_key="query-abc",
                query="cricket shorts",
                language="en",
                region="IN",
                strategy="localized_topic",
                raw_results=raw,
                candidate_count=candidates,
                run_at=datetime(2026, 11, day, tzinfo=UTC),
            )
        store.record_query(
            platform="instagram",
            query_key="reels-abc",
            query="cricket reels",
            language="en",
            region="IN",
            strategy="localized_topic",
            raw_results=12,
            candidate_count=3,
            run_at=datetime(2026, 11, 21, tzinfo=UTC),
        )

        assert store.query_performance("youtube") == {
            "query-abc": {
                "run_count": 2,
                "raw_results": 50,
                "candidate_count": 38,
            }
        }
        assert store.query_performance("instagram") == {
            "reels-abc": {
                "run_count": 1,
                "raw_results": 12,
                "candidate_count": 3,
            }
        }
        assert store.query_performance("tiktok") == {}


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


def test_instagram_play_count_qualifies_as_plays_without_becoming_views(tmp_path: Path):
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
        assert saved.status == "eligible"
        assert saved.qualifying_metric() == 3_000_000
        assert saved.qualifying_metric_kind() == "plays"
        assert saved.view_count is None
        assert store.eligible_candidates()[0].source_id == "PlayCount123"


def _training_rights(
    platform: str,
    source_id: str,
    *,
    revoked: bool = False,
    expires_at=None,
):
    from shorts_intelligence.discovery.models import AcquisitionAuthorization

    return AcquisitionAuthorization(
        platform=platform,
        source_id=source_id,
        basis="creator_permission",
        evidence_ref=f"private-consent:{platform}:{source_id}",
        media_retrieval=True,
        media_analysis=True,
        temporary_processing=True,
        derived_artifact_retention=True,
        model_training=True,
        revoked=revoked,
        expires_at=expires_at,
    )


def test_processing_queue_requires_current_complete_item_rights(tmp_path: Path):
    from datetime import UTC, datetime

    with DiscoveryStore(tmp_path / "rights-gate.sqlite3") as store:
        store.start_run("rights-gate", 10, 1_000_000)
        candidate = _candidate(1_500_000)
        store.upsert_candidate(candidate, min_views=1_000_000, run_id="rights-gate")

        assert store.processing_candidates(limit=10) == []
        assert store.count_processing_blocked() == 1

        expired = _training_rights(
            "youtube",
            candidate.source_id,
            expires_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
        store.replace_rights_authorizations([expired])
        assert store.processing_candidates(limit=10) == []
        assert store.count_processing_blocked() == 1

        valid = _training_rights("youtube", candidate.source_id)
        store.replace_rights_authorizations([valid])
        queued = store.processing_candidates(limit=10)
        assert len(queued) == 1
        assert queued[0][0].source_id == candidate.source_id
        assert queued[0][1].evidence_ref == valid.evidence_ref
        assert store.count_processing_blocked() == 0

        revoked = _training_rights("youtube", candidate.source_id, revoked=True)
        store.replace_rights_authorizations([revoked])
        assert store.processing_candidates(limit=10) == []
        assert store.count_processing_blocked() == 1


def test_processing_queue_excludes_estimates_unless_explicitly_allowed(tmp_path: Path):
    estimate = DiscoveredCandidate(
        platform="instagram",
        source_id="EstimatedReel123",
        canonical_url="https://www.instagram.com/reel/EstimatedReel123/",
        view_count=None,
        play_count=None,
        metric_source="instagram_rendered_reel_card.plays",
        short_format_status="confirmed",
        metadata={
            "metric_kind": "plays",
            "metric_is_estimate": True,
            "metric_display_value": "1.2M",
            "metric_conservative_lower_bound": 1_150_000,
        },
    )
    with DiscoveryStore(tmp_path / "estimate-gate.sqlite3") as store:
        store.start_run("estimate-gate", 10, 1_000_000)
        store.upsert_candidate(
            estimate, min_views=1_000_000, run_id="estimate-gate"
        )
        store.replace_rights_authorizations([
            _training_rights("instagram", estimate.source_id)
        ])

        assert store.processing_candidates(limit=10) == []
        opted_in = store.processing_candidates(
            limit=10, allow_estimated_metrics=True
        )
        assert len(opted_in) == 1
        candidate = opted_in[0][0]
        assert candidate.view_count is None
        assert candidate.play_count is None
        assert candidate.qualifying_metric() == 1_150_000
        assert candidate.metadata["metric_is_estimate"] is True


def test_processing_queue_honours_custom_threshold_and_zero_limit(tmp_path: Path):
    with DiscoveryStore(tmp_path / "processing-threshold.sqlite3") as store:
        store.start_run("processing-threshold", 10, 1_000_000)
        candidate = _candidate(1_500_000)
        store.upsert_candidate(
            candidate, min_views=1_000_000, run_id="processing-threshold"
        )
        store.replace_rights_authorizations([
            _training_rights("youtube", candidate.source_id)
        ])

        assert store.processing_candidates(limit=0) == []
        assert store.processing_candidates(min_metric=2_000_000, limit=10) == []
        assert store.count_processing_blocked(min_metric=2_000_000) == 0


def test_processing_manifest_is_review_required_and_rechecks_rights(tmp_path: Path):
    import json

    from shorts_intelligence.discovery.processing import _export_processing_manifest

    candidate = _candidate(1_500_000)
    authorization = _training_rights("youtube", candidate.source_id)
    with DiscoveryStore(tmp_path / "processing-manifest.sqlite3") as store:
        store.start_run("processing-manifest", 10, 1_000_000)
        store.upsert_candidate(
            candidate, min_views=1_000_000, run_id="processing-manifest"
        )
        store.replace_rights_authorizations([authorization])
        store.mark_processing_started(candidate, authorization)
        store.mark_processing_complete(
            "youtube",
            candidate.source_id,
            media_path=str(tmp_path / "asset.mp4"),
            media_sha256="a" * 64,
            analysis_path=str(tmp_path / "analysis.json"),
            transcript_path=str(tmp_path / "transcript.json"),
            ocr_path=str(tmp_path / "ocr.json"),
            transcript_segments=3,
            ocr_spans=2,
            detected_language="en",
            asr_engine="vidtrace-faster-whisper",
            ocr_engine="vidtrace-paddleocr",
            quality_flags=[],
        )

        manifest = tmp_path / "dataset" / "training-candidates.jsonl"
        assert _export_processing_manifest(
            store, manifest, min_metric=1_000_000
        ) == 1
        record = json.loads(manifest.read_text(encoding="utf-8").strip())
        assert record["metric"]["threshold_met"] is True
        assert record["review"]["status"] == "review_required"
        assert record["review"]["training_approved"] is False
        assert record["training_ready"] is False
        assert record["telemetry"]["transcript_segments"] == 3

        store.replace_rights_authorizations([
            _training_rights("youtube", candidate.source_id, revoked=True)
        ])
        assert _export_processing_manifest(
            store, manifest, min_metric=1_000_000
        ) == 0
        assert manifest.read_text(encoding="utf-8") == ""


def test_exact_metric_refresh_clears_previous_instagram_estimate_flag(tmp_path: Path):
    estimate = DiscoveredCandidate(
        platform="instagram",
        source_id="RefreshExact123",
        canonical_url="https://www.instagram.com/reel/RefreshExact123/",
        short_format_status="confirmed",
        metadata={
            "metric_kind": "plays",
            "metric_is_estimate": True,
            "metric_display_value": "1.2M",
            "metric_conservative_lower_bound": 1_150_000,
        },
    )
    exact = DiscoveredCandidate(
        platform="instagram",
        source_id="RefreshExact123",
        canonical_url="https://www.instagram.com/reel/RefreshExact123/",
        play_count=1_234_567,
        metric_source="instagram_response.video_play_count",
        short_format_status="confirmed",
        metadata={"metric_kind": "plays"},
    )
    with DiscoveryStore(tmp_path / "exact-refresh.sqlite3") as store:
        store.start_run("estimate-first", 10, 1_000_000)
        store.upsert_candidate(
            estimate, min_views=1_000_000, run_id="estimate-first"
        )
        store.replace_rights_authorizations([
            _training_rights("instagram", estimate.source_id)
        ])
        assert store.processing_candidates(limit=10) == []

        store.start_run("exact-refresh", 10, 1_000_000)
        store.upsert_candidate(
            exact, min_views=1_000_000, run_id="exact-refresh"
        )
        saved = store.get_candidate("instagram", estimate.source_id)
        assert saved is not None
        assert saved.play_count == 1_234_567
        assert saved.metadata["metric_is_estimate"] is False
        assert saved.metadata["metric_precision"] == "exact_numeric"
        assert "metric_conservative_lower_bound" not in saved.metadata
        assert len(store.processing_candidates(limit=10)) == 1
