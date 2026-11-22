from __future__ import annotations

import asyncio
from types import SimpleNamespace

from shorts_intelligence.discovery.engine import run_creator_graph
from shorts_intelligence.discovery.models import DiscoveredCandidate
from shorts_intelligence.discovery.storage import DiscoveryStore


def _candidate(video_id: str, channel_id: str, views: int) -> DiscoveredCandidate:
    return DiscoveredCandidate(
        platform="youtube", source_id=video_id,
        canonical_url=f"https://www.youtube.com/shorts/{video_id}",
        creator=channel_id, view_count=views, metric_source="fixture",
        short_format_status="confirmed",
        metadata={"channel_id": channel_id, "provider": "fixture"},
    )


def test_graph_engine_persists_seed_creator_and_related_video(monkeypatch, tmp_path):
    import shorts_intelligence.discovery.engine as engine

    class FakeYouTube:
        def __init__(self, **kwargs):
            self.requests = 0
        async def search_seed_videos(self, query, *, limit):
            self.requests += 1
            return [SimpleNamespace(video_id="SeedVideo123", channel_id="UC" + "a" * 22)]
        async def search_hashtag_videos(self, hashtag, *, limit):
            return []
        async def enrich_seed_videos(self, videos):
            if not videos:
                return []
            return [_candidate("SeedVideo123", "UC" + "a" * 22, 2_000_000)]
        async def harvest_creator(self, creator_id, *, limit):
            self.requests += 1
            return [_candidate("CreatorVideo12", creator_id, 3_000_000)]
        async def expand_related(self, video_id, *, limit):
            self.requests += 1
            return [_candidate("RelatedVideo12", "UC" + "b" * 22, 4_000_000)]
        async def close(self):
            return None

    monkeypatch.setattr(engine, "TubeScrapeProvider", FakeYouTube)
    with DiscoveryStore(tmp_path / "graph.sqlite3") as store:
        summary = asyncio.run(run_creator_graph(
            store, platform="youtube", target_new=3, min_metric=1_000_000,
            max_runtime_seconds=30, max_seed_queries=1, max_creators=3,
            max_expansions=2, max_depth=2,
        ))
        assert summary["eligible_new"] == 3
        assert summary["creator_edges"] == 1
        assert summary["candidate_observations"] == 3
        assert store.get_candidate("youtube", "RelatedVideo12") is not None
        assert summary["creators_pending"] >= 0


def test_instagram_force_rechecks_completed_creator_and_reports_capture(monkeypatch, tmp_path):
    import shorts_intelligence.discovery.engine as engine

    class FakeInstagram:
        calls = 0

        def __init__(self, **kwargs):
            self.requests_observed = 3
            self.responses_parsed = 1
            self.responses_unparsed = 2
            self.errors = []
            self.blocked = False
            self.creator_diagnostics = []
            self.hashtag_diagnostics = []

        async def harvest_creator(self, username, *, max_scrolls=8, max_reel_details=3):
            type(self).calls += 1
            self.creator_diagnostics.append({
                "handle": username,
                "http_json_responses": 3,
                "responses_with_reels": 1,
                "candidate_count": 1,
                "reason": None,
            })
            candidate = DiscoveredCandidate(
                platform="instagram",
                source_id="ReelCandidate123",
                canonical_url="https://www.instagram.com/reel/ReelCandidate123/",
                creator=username,
                play_count=2_000_000,
                metric_source="fixture",
                short_format_status="confirmed",
                metadata={"metric_kind": "plays"},
            )
            return [candidate], set()

    monkeypatch.setattr(engine, "InstagramPlaywrightProvider", FakeInstagram)
    with DiscoveryStore(tmp_path / "instagram-force.sqlite3") as store:
        first = asyncio.run(run_creator_graph(
            store, platform="instagram", target_new=10, min_metric=1_000_000,
            max_runtime_seconds=30, instagram_profile_dir=tmp_path / "profile",
            instagram_creators=["@creator"], max_creators=1,
        ))
        assert first["creator_harvest_batches"] == 1
        assert first["creators_completed"] == 1
        assert first["creators_with_candidates"] == 1
        assert first["provider_requests"]["instagram"]["json_responses_observed"] == 3

        second = asyncio.run(run_creator_graph(
            store, platform="instagram", target_new=10, min_metric=1_000_000,
            max_runtime_seconds=30, instagram_profile_dir=tmp_path / "profile",
            instagram_creators=["creator"], max_creators=1,
        ))
        assert second.get("creator_harvest_batches", 0) == 0

        third = asyncio.run(run_creator_graph(
            store, platform="instagram", target_new=10, min_metric=1_000_000,
            max_runtime_seconds=30, instagram_profile_dir=tmp_path / "profile",
            instagram_creators=["creator"], max_creators=1, force=True,
        ))
        assert third["creator_harvest_batches"] == 1
        assert third["candidates_observed"] == 1
        assert FakeInstagram.calls == 2


def test_instagram_hashtag_harvest_persists_reels_and_reports_metrics(monkeypatch, tmp_path):
    import shorts_intelligence.discovery.engine as engine

    class FakeInstagram:
        def __init__(self, **kwargs):
            self.requests_observed = 2
            self.responses_parsed = 1
            self.responses_unparsed = 1
            self.errors = []
            self.blocked = False
            self.creator_diagnostics = []
            self.hashtag_diagnostics = []

        async def harvest_hashtag(
            self, hashtag, *, max_scrolls=8, max_reel_details=8
        ):
            self.hashtag_diagnostics.append({
                "surface": "hashtag_page",
                "hashtag": hashtag,
                "candidate_count": 1,
                "metric_count": 1,
                "detail_pages_attempted": 1,
                "detail_pages_with_metrics": 1,
            })
            return [DiscoveredCandidate(
                platform="instagram",
                source_id="HashtagReel123",
                canonical_url="https://www.instagram.com/reel/HashtagReel123/",
                creator="hashtag:cricket",
                play_count=2_500_000,
                metric_source="fixture",
                short_format_status="confirmed",
                hashtags=["cricket"],
                metadata={"discovery_surface": "hashtag_page", "metric_kind": "plays"},
            )]

    monkeypatch.setattr(engine, "InstagramPlaywrightProvider", FakeInstagram)
    with DiscoveryStore(tmp_path / "instagram-hashtag.sqlite3") as store:
        summary = asyncio.run(run_creator_graph(
            store,
            platform="instagram",
            target_new=10,
            min_metric=1_000_000,
            max_runtime_seconds=30,
            instagram_profile_dir=tmp_path / "profile",
            instagram_creators=[],
            instagram_hashtags=["#Cricket"],
            max_instagram_hashtags=5,
            max_creators=0,
        ))
        assert summary["instagram_hashtag_requests"] == 1
        assert summary["hashtags_with_candidates"] == 1
        assert summary["eligible_new"] == 1
        assert summary.get("creator_harvest_batches", 0) == 0
        assert summary["hashtag_results"][0]["hashtag"] == "cricket"
        saved = store.get_candidate("instagram", "HashtagReel123")
        assert saved is not None
        assert saved.play_count == 2_500_000
        assert saved.metadata["discovery_surface"] == "hashtag_page"


def test_youtube_run_reports_candidates_by_discovery_stage(monkeypatch, tmp_path):
    import shorts_intelligence.discovery.engine as engine

    class FakeYouTube:
        def __init__(self, **kwargs):
            self.requests = 0

        async def search_seed_videos(self, query, *, limit):
            return [SimpleNamespace(video_id="SeedCandidate123", channel_id=None)]

        async def search_hashtag_videos(self, hashtag, *, limit):
            return []

        async def enrich_seed_videos(self, videos):
            if not videos:
                return []
            return [_candidate("SeedCandidate123", "UC" + "c" * 22, 2_000_000)]

        async def harvest_creator(self, creator_id, *, limit):
            return [_candidate("CreatorCandidate123", creator_id, 3_000_000)]

        async def expand_related(self, video_id, *, limit):
            return []

        async def close(self):
            return None

    monkeypatch.setattr(engine, "TubeScrapeProvider", FakeYouTube)
    with DiscoveryStore(tmp_path / "stage-counts.sqlite3") as store:
        summary = asyncio.run(run_creator_graph(
            store,
            platform="youtube",
            target_new=50,
            min_metric=1_000_000,
            max_runtime_seconds=30,
            max_seed_queries=1,
            max_hashtag_queries=0,
            max_creators=0,
            max_expansions=0,
        ))
    counts = summary["discovery_stage_counts"]
    assert counts["youtube_seed_search_results"] == 1
    assert counts["youtube_seed_detail_candidates"] == 1
    assert counts["youtube_creator_candidates"] == 0
    assert counts["youtube_related_candidates"] == 0
    assert counts["all_candidates_observed"] == 1


def test_youtube_seed_stage_updates_metric_and_inventory_counters(monkeypatch, tmp_path):
    import shorts_intelligence.discovery.engine as engine

    class FakeYouTube:
        def __init__(self, **kwargs):
            pass

        async def search_seed_videos(self, query, *, limit):
            return [SimpleNamespace(video_id="SeedMetrics123", channel_id=None)]

        async def search_hashtag_videos(self, hashtag, *, limit):
            return []

        async def enrich_seed_videos(self, videos):
            return [_candidate("SeedMetrics123", "UC" + "d" * 22, 2_000_000)]

        async def close(self):
            return None

    monkeypatch.setattr(engine, "TubeScrapeProvider", FakeYouTube)
    with DiscoveryStore(tmp_path / "seed-metrics.sqlite3") as store:
        summary = asyncio.run(run_creator_graph(
            store, platform="youtube", target_new=50, min_metric=1_000_000,
            max_runtime_seconds=30, max_seed_queries=1, max_hashtag_queries=0,
            max_creators=0, max_expansions=0,
        ))
    assert summary["new_inventory_candidates"] == 1
    assert summary["metric_observed_candidates"] == 1
    assert summary["metric_unknown_candidates"] == 0
    assert summary["metric_above_threshold_candidates"] == 1
    assert summary["discovery_stage_counts"]["youtube_seed_detail_candidates"] == 1


def test_continue_graph_after_target_processes_creator_frontier(monkeypatch, tmp_path):
    import shorts_intelligence.discovery.engine as engine

    class FakeYouTube:
        def __init__(self, **kwargs):
            self.harvested = 0

        async def search_seed_videos(self, query, *, limit):
            return [SimpleNamespace(video_id="SeedGraph123", channel_id="UC" + "e" * 22)]

        async def search_hashtag_videos(self, hashtag, *, limit):
            return []

        async def enrich_seed_videos(self, videos):
            return [_candidate("SeedGraph123", "UC" + "e" * 22, 2_000_000)]

        async def harvest_creator(self, creator_id, *, limit):
            self.harvested += 1
            return [_candidate("CreatorGraph123", creator_id, 3_000_000)]

        async def expand_related(self, video_id, *, limit):
            return []

        async def close(self):
            return None

    monkeypatch.setattr(engine, "TubeScrapeProvider", FakeYouTube)
    with DiscoveryStore(tmp_path / "continue-graph.sqlite3") as store:
        summary = asyncio.run(run_creator_graph(
            store, platform="youtube", target_new=1, min_metric=1_000_000,
            max_runtime_seconds=30, max_seed_queries=1, max_hashtag_queries=0,
            max_creators=1, max_expansions=0, continue_graph_after_target=True,
        ))
    assert summary["eligible_new"] == 2
    assert summary["youtube_creator_candidates"] == 1
    assert summary["continue_graph_after_target"] is True


def test_related_video_candidates_are_included_in_total_observed_count(monkeypatch, tmp_path):
    import shorts_intelligence.discovery.engine as engine

    class FakeYouTube:
        def __init__(self, **kwargs):
            self.requests = 0

        async def search_seed_videos(self, query, *, limit):
            return [SimpleNamespace(video_id="SeedTotal123", channel_id="UC" + "f" * 22)]

        async def search_hashtag_videos(self, hashtag, *, limit):
            return []

        async def enrich_seed_videos(self, videos):
            return [_candidate("SeedTotal123", "UC" + "f" * 22, 2_000_000)]

        async def harvest_creator(self, creator_id, *, limit):
            return []

        async def expand_related(self, video_id, *, limit):
            return [_candidate("RelatedTotal123", "UC" + "g" * 22, 3_000_000)]

        async def close(self):
            return None

    monkeypatch.setattr(engine, "TubeScrapeProvider", FakeYouTube)
    with DiscoveryStore(tmp_path / "related-total.sqlite3") as store:
        summary = asyncio.run(run_creator_graph(
            store,
            platform="youtube",
            target_new=50,
            min_metric=1_000_000,
            max_runtime_seconds=30,
            max_seed_queries=1,
            max_hashtag_queries=0,
            max_creators=0,
            max_expansions=1,
            max_depth=1,
        ))
    assert summary["related_candidates"] == 1
    assert summary["candidates_observed"] == 2
    assert summary["discovery_stage_counts"]["all_candidates_observed"] == 2
