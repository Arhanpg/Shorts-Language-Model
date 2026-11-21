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
