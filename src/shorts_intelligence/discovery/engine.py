"""Async persistent creator-graph discovery orchestration."""
from __future__ import annotations

import asyncio
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from shorts_intelligence.discovery.frontier import CreatorFrontier
from shorts_intelligence.discovery.providers.instagram_playwright import InstagramPlaywrightProvider
from shorts_intelligence.discovery.providers.youtube_tubescrape import TubeScrapeProvider
from shorts_intelligence.discovery.storage import DiscoveryStore

async def run_creator_graph(
    store: DiscoveryStore, *, platform: str = "youtube", target_new: int = 100,
    min_metric: int = 1_000_000, max_runtime_seconds: int = 240,
    max_seed_queries: int = 8, max_creators: int = 40, max_expansions: int = 80,
    max_depth: int = 3, youtube_concurrency: int = 5,
    instagram_profile_dir: Path | None = None,
    instagram_creators: list[str] | None = None,
) -> dict[str, Any]:
    """Run bounded graph discovery. This function never downloads media."""
    if platform not in {"youtube", "instagram", "all"}:
        raise ValueError("platform must be youtube, instagram or all")
    run_id = uuid.uuid4().hex
    store.start_run(run_id, target_new, min_metric)
    frontier = CreatorFrontier(store.connection)
    loop = asyncio.get_running_loop()
    started = loop.time()
    deadline = started + max(30, min(max_runtime_seconds, 900))
    stats: Counter[str] = Counter()
    errors: list[str] = []
    providers: dict[str, Any] = {}
    new_eligible = 0

    async def within_budget(awaitable: Any) -> Any:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError("overall graph-discovery budget expired")
        return await asyncio.wait_for(awaitable, timeout=remaining)

    try:
        if platform in {"youtube", "all"}:
            providers["youtube"] = TubeScrapeProvider(concurrency=youtube_concurrency)
        if platform in {"instagram", "all"}:
            if instagram_profile_dir is None:
                raise ValueError("Instagram graph discovery requires a local browser profile directory.")
            providers["instagram"] = InstagramPlaywrightProvider(profile_dir=instagram_profile_dir)

        if "youtube" in providers:
            yt = providers["youtube"]
            queries = [
                "viral youtube shorts", "most viewed shorts", "cricket shorts",
                "comedy shorts", "cooking shorts", "travel shorts",
                "education shorts", "technology shorts",
            ][:max_seed_queries]
            for query in queries:
                if loop.time() >= deadline or yt.blocked:
                    break
                try:
                    listed = await within_budget(yt.search_seed_videos(query, limit=20))
                    stats["seed_search_requests"] += 1
                    stats["seed_search_results"] += len(listed)
                    details = await within_budget(yt.enrich_seed_videos(listed))
                    stats["seed_detail_batches"] += 1
                    for candidate in details:
                        stats["candidates_observed"] += 1
                        channel_id = candidate.metadata.get("channel_id")
                        metric = candidate.qualifying_metric()
                        qualifies = (
                            metric is not None and metric >= min_metric
                            and candidate.short_format_status == "confirmed"
                        )
                        if qualifies and channel_id:
                            frontier.enqueue_creator(
                                "youtube", str(channel_id), handle=candidate.creator,
                                discovered_via="seed_search", priority_score=float(metric or 1),
                                depth=0)
                            frontier.enqueue_seed("youtube", candidate.source_id,
                                                   creator_id=str(channel_id), depth=0)
                        _, became = store.upsert_candidate(
                            candidate, min_views=min_metric, run_id=run_id)
                        if became:
                            new_eligible += 1
                            stats["eligible_new"] += 1
                except Exception as exc:
                    stats["seed_search_failures"] += 1
                    errors.append(f"seed search {query!r}: {type(exc).__name__}: {str(exc)[:180]}")

        if "instagram" in providers:
            for username in instagram_creators or []:
                frontier.enqueue_creator(
                    "instagram", username.casefold().lstrip("@"), handle=username.lstrip("@"),
                    discovered_via="manual_seed", priority_score=1.0, depth=0)

        creators_claimed = {"youtube": 0, "instagram": 0}
        expansions_done = 0
        while loop.time() < deadline and new_eligible < target_new:
            progressed = False
            for current_platform in (["youtube", "instagram"] if platform == "all" else [platform]):
                provider = providers.get(current_platform)
                if provider is None or creators_claimed[current_platform] >= max_creators:
                    continue
                batch = frontier.claim_creators(current_platform, limit=1)
                if not batch:
                    continue
                progressed = True
                creator = batch[0]
                creators_claimed[current_platform] += 1
                try:
                    if current_platform == "youtube":
                        candidates = await within_budget(provider.harvest_creator(creator.creator_id, limit=48))
                        stats["creator_harvest_batches"] += 1
                    else:
                        candidates, coauthors = await within_budget(provider.harvest_creator(creator.handle or creator.creator_id))
                        stats["creator_harvest_batches"] += 1
                        for handle in coauthors:
                            frontier.enqueue_creator(
                                "instagram", handle, handle=handle, discovered_via="coauthor",
                                priority_score=1.2, depth=creator.depth + 1)
                            frontier.add_edge("instagram", creator.creator_id, handle,
                                              edge_type="coauthor")
                    creator_yield = 0
                    for candidate in candidates:
                        stats["candidates_observed"] += 1
                        _, became = store.upsert_candidate(
                            candidate, min_views=min_metric, run_id=run_id)
                        if became:
                            new_eligible += 1
                            creator_yield += 1
                            stats["eligible_new"] += 1
                        if current_platform == "youtube":
                            metric = candidate.qualifying_metric()
                            if (metric is not None and metric >= min_metric
                                    and candidate.short_format_status == "confirmed"):
                                frontier.enqueue_seed(
                                    "youtube", candidate.source_id, creator_id=creator.creator_id,
                                    depth=creator.depth)
                    frontier.finish_creator(
                        current_platform, creator.creator_id,
                        eligible_yield=creator_yield, exhausted=True)
                except Exception as exc:
                    message = f"{type(exc).__name__}: {str(exc)[:180]}"
                    errors.append(f"{current_platform} creator {creator.creator_id}: {message}")
                    stats["creator_failures"] += 1
                    frontier.finish_creator(current_platform, creator.creator_id, error=message)

            if "youtube" in providers and expansions_done < max_expansions and loop.time() < deadline:
                seeds = frontier.claim_seeds("youtube", limit=1)
                if seeds:
                    progressed = True
                    seed = seeds[0]
                    if int(seed["depth"]) >= max_depth:
                        frontier.finish_seed("youtube", str(seed["video_id"]))
                    else:
                        try:
                            related = await within_budget(providers["youtube"].expand_related(str(seed["video_id"]), limit=9))
                            stats["related_sequence_requests"] += 1
                            for candidate in related:
                                stats["related_candidates"] += 1
                                channel_id = candidate.metadata.get("channel_id")
                                metric = candidate.qualifying_metric()
                                qualifies = (
                                    metric is not None and metric >= min_metric
                                    and candidate.short_format_status == "confirmed"
                                )
                                if qualifies and channel_id and int(seed["depth"]) < max_depth:
                                    frontier.enqueue_creator(
                                        "youtube", str(channel_id), handle=candidate.creator,
                                        discovered_via="related_graph",
                                        priority_score=float(metric or 1),
                                        depth=int(seed["depth"]) + 1)
                                    if seed["creator_id"]:
                                        frontier.add_edge(
                                            "youtube", str(seed["creator_id"]), str(channel_id),
                                            edge_type="related_short", source_video_id=str(seed["video_id"]))
                                if qualifies:
                                    frontier.enqueue_seed(
                                        "youtube", candidate.source_id,
                                        creator_id=str(channel_id) if channel_id else None,
                                        depth=int(seed["depth"]) + 1)
                                _, became = store.upsert_candidate(
                                    candidate, min_views=min_metric, run_id=run_id)
                                if became:
                                    new_eligible += 1
                                    stats["eligible_new"] += 1
                            frontier.finish_seed("youtube", str(seed["video_id"]))
                        except Exception as exc:
                            frontier.finish_seed("youtube", str(seed["video_id"]), error=str(exc))
                            stats["expansion_failures"] += 1
                            errors.append(f"related seed {seed['video_id']}: {type(exc).__name__}: {str(exc)[:180]}")
                    expansions_done += 1
            if not progressed:
                break

        elapsed = round(loop.time() - started, 2)
        graph_summary = frontier.summary()
        request_counts = {
            name: (
                {"json_responses_observed": provider.requests_observed,
                 "responses_parsed": provider.responses_parsed,
                 "responses_unparsed": provider.responses_unparsed}
                if name == "instagram" else {"library_calls": provider.requests}
            )
            for name, provider in providers.items()
        }
        summary = {
            **dict(stats), **graph_summary, "run_id": run_id, "platform": platform,
            "elapsed_seconds": elapsed, "new_eligible": new_eligible,
            "min_metric": min_metric, "max_depth": max_depth,
            "metric_policy": {
                "youtube": "numeric views",
                "instagram": "numeric plays; retained separately from views",
            },
            "provider_requests": request_counts, "errors": errors[:100],
        }
        store.finish_run(run_id, {
            "scanned": stats["candidates_observed"] + stats["related_candidates"],
            "new_eligible": new_eligible, "duplicates": 0,
            "errors": stats["creator_failures"] + stats["seed_search_failures"] + stats["expansion_failures"],
            **summary})
        return summary
    finally:
        for provider in providers.values():
            close = getattr(provider, "close", None)
            if close:
                result = close()
                if asyncio.iscoroutine(result):
                    await result
