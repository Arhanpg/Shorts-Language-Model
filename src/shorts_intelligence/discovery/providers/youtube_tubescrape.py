"""TubeScrape adapter for Shorts-first, creator-graph discovery."""
from __future__ import annotations
import asyncio
from typing import Any
from shorts_intelligence.discovery.models import DiscoveredCandidate

class TubeScrapeProvider:
    """Use TubeScrape's public async client; no official API credentials."""
    def __init__(self, *, timeout: float = 10.0, concurrency: int = 5) -> None:
        try:
            from tubescrape import YouTube
        except ImportError as exc:
            raise RuntimeError('Install discovery dependencies: pip install -e ".[discovery]"') from exc
        self.client = YouTube(timeout=timeout, max_retries=1)
        self.timeout = max(3.0, min(timeout, 15.0))
        self.concurrency = max(1, min(concurrency, 5))
        self.requests = 0

    async def search_seed_videos(self, query: str, *, limit: int = 20) -> list[Any]:
        self.requests += 1
        result = await asyncio.wait_for(
            self.client.asearch(query, max_results=limit, type="short", sort_by="view_count"),
            timeout=self.timeout * 3)
        return list(result.videos)

    async def harvest_creator(self, creator_id: str, *, limit: int = 48) -> list[DiscoveredCandidate]:
        self.requests += 1
        result = await asyncio.wait_for(
            self.client.aget_channel_shorts(creator_id, max_results=limit, sort_by="popular"),
            timeout=self.timeout * 4)
        shorts = list(result.shorts)
        if not shorts:
            return []
        ids = [item.video_id for item in shorts]
        self.requests += 1
        details = await asyncio.wait_for(
            self.client.aget_videos_info(ids, enrich=False, concurrency=self.concurrency),
            timeout=self.timeout * max(2, (len(ids) + self.concurrency - 1) // self.concurrency + 1))
        candidates = []
        for listed, info in zip(shorts, details, strict=False):
            if info is None:
                continue
            candidate = self._candidate(info, evidence="channel_shorts_tab")
            candidate.metadata.update({
                "listed_views_hint": listed.views,
                "popular_sort": "popular",
                "creator_frontier_id": creator_id,
            })
            candidates.append(candidate)
        return candidates

    async def expand_related(self, video_id: str, *, limit: int = 9) -> list[DiscoveredCandidate]:
        self.requests += 1
        related = await asyncio.wait_for(
            self.client.aget_related_shorts(video_id, max_results=limit),
            timeout=self.timeout * 3)
        return [self._candidate(item, evidence="related_shorts_sequence") for item in related]

    async def enrich_seed_videos(self, videos: list[Any]) -> list[DiscoveredCandidate]:
        ids = [getattr(item, "video_id", "") for item in videos if getattr(item, "video_id", "")]
        if not ids:
            return []
        self.requests += 1
        details = await asyncio.wait_for(
            self.client.aget_videos_info(ids, enrich=False, concurrency=self.concurrency),
            timeout=self.timeout * max(2, (len(ids) + self.concurrency - 1) // self.concurrency + 1))
        return [self._candidate(item, evidence="shorts_search_seed") for item in details if item]

    @staticmethod
    def _candidate(info: Any, *, evidence: str) -> DiscoveredCandidate:
        video_id = str(getattr(info, "video_id", ""))
        is_short = getattr(info, "is_short", None)
        channel_id = getattr(info, "channel_id", None)
        return DiscoveredCandidate(
            platform="youtube",
            source_id=video_id,
            canonical_url=f"https://www.youtube.com/shorts/{video_id}",
            title=getattr(info, "title", None),
            description=getattr(info, "description", None),
            creator=getattr(info, "channel", None),
            view_count=int(info.view_count) if getattr(info, "view_count", None) is not None else None,
            metric_source="tubescrape_video_info.view_count",
            duration_seconds=float(info.duration_seconds) if getattr(info, "duration_seconds", None) else None,
            upload_date=getattr(info, "upload_date", None),
            short_format_status=(
                "unknown" if is_short is False else
                "confirmed" if is_short is True or evidence in {
                    "channel_shorts_tab", "related_shorts_sequence", "shorts_search_seed"
                } else "unknown"
            ),
            metadata={
                "provider": "tubescrape",
                "provider_version": "0.6.0",
                "format_evidence": evidence,
                "is_short_field": is_short,
                "channel_id": channel_id,
            })

    async def close(self) -> None:
        await self.client.aclose()
