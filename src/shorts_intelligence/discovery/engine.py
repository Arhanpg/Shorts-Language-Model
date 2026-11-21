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
    max_seed_queries: int = 8, max_hashtag_queries: int = 4,
    max_creators: int = 40, max_expansions: int = 80,
    max_depth: int = 3, youtube_concurrency: int = 5,
    instagram_profile_dir: Path | None = None,
    instagram_creators: list[str] | None = None,
    instagram_hashtags: list[str] | None = None,
    force: bool = False,
    instagram_max_scrolls: int = 8,
    instagram_max_reel_details: int = 3,
    instagram_hashtag_max_reel_details: int = 8,
    max_instagram_hashtags: int = 20,
    continue_graph_after_target: bool = False,
) -> dict[str, Any]:
    """Run bounded graph discovery. This function never downloads media."""
    if platform not in {"youtube", "instagram", "all"}:
        raise ValueError("platform must be youtube, instagram or all")
    run_id = uuid.uuid4().hex
    store.start_run(run_id, target_new, min_metric)
    frontier = CreatorFrontier(store.connection)
    loop = asyncio.get_running_loop()
    started = loop.time()
    bounded_runtime = max(30, min(max_runtime_seconds, 900))
    deadline = started + bounded_runtime
    combined_with_instagram = platform == "all" and bool(
        instagram_creators or instagram_hashtags
    )
    youtube_deadline = (
        started + bounded_runtime * 0.62 if combined_with_instagram else deadline
    )
    instagram_deadline = (
        started + bounded_runtime * 0.95 if platform == "all" else deadline
    )
    youtube_seed_deadline = (
        min(youtube_deadline, started + bounded_runtime * 0.35)
        if combined_with_instagram else youtube_deadline
    )
    stats: Counter[str] = Counter()
    errors: list[str] = []
    providers: dict[str, Any] = {}
    creator_results: list[dict[str, Any]] = []
    hashtag_results: list[dict[str, Any]] = []
    new_eligible = 0

    async def within_budget(awaitable: Any, stage_deadline: float = deadline) -> Any:
        remaining = min(deadline, stage_deadline) - loop.time()
        if remaining <= 0:
            raise TimeoutError("provider stage budget expired")
        return await asyncio.wait_for(awaitable, timeout=remaining)

    def record_candidate_metrics(candidate: Any, *, is_new: bool) -> None:
        if is_new:
            stats["new_inventory_candidates"] += 1
        metric = candidate.qualifying_metric()
        if metric is None:
            stats["metric_unknown_candidates"] += 1
        else:
            stats["metric_observed_candidates"] += 1
            if metric >= min_metric:
                stats["metric_above_threshold_candidates"] += 1

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
                if loop.time() >= youtube_seed_deadline or getattr(yt, "blocked", False):
                    break
                try:
                    listed = await within_budget(yt.search_seed_videos(query, limit=20), youtube_seed_deadline)
                    stats["seed_search_requests"] += 1
                    stats["seed_search_results"] += len(listed)
                    details = await within_budget(yt.enrich_seed_videos(listed), youtube_seed_deadline)
                    stats["seed_detail_batches"] += 1
                    stats["seed_detail_candidates"] += len(details)
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
                        is_new, became = store.upsert_candidate(
                            candidate, min_views=min_metric, run_id=run_id)
                        record_candidate_metrics(candidate, is_new=is_new)
                        frontier.record_candidate_observation(
                            candidate.platform, candidate.source_id, run_id=run_id,
                            metric_kind=candidate.qualifying_metric_kind(),
                            metric_value=candidate.qualifying_metric(),
                            metric_source=candidate.metric_source,
                            format_status=candidate.short_format_status,
                            evidence=candidate.metadata,
                        )
                        if became:
                            new_eligible += 1
                            stats["eligible_new"] += 1
                except Exception as exc:
                    stats["seed_search_failures"] += 1
                    errors.append(f"seed search {query!r}: {type(exc).__name__}: {str(exc)[:180]}")

            hashtags = ["shorts", "viralshorts", "comedyshorts", "cricketshorts",
                        "cooking", "education", "travel", "technology"][:max_hashtag_queries]
            for hashtag in hashtags:
                if loop.time() >= youtube_seed_deadline or getattr(yt, "blocked", False):
                    break
                try:
                    listed = await within_budget(yt.search_hashtag_videos(hashtag, limit=20), youtube_seed_deadline)
                    details = await within_budget(yt.enrich_seed_videos(listed))
                    stats["hashtag_search_requests"] += 1
                    stats["hashtag_search_results"] += len(listed)
                    stats["hashtag_detail_candidates"] += len(details)
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
                                discovered_via="hashtag_seed", priority_score=float(metric or 1),
                                depth=0)
                            frontier.enqueue_seed(
                                "youtube", candidate.source_id, creator_id=str(channel_id), depth=0)
                        is_new, became = store.upsert_candidate(
                            candidate, min_views=min_metric, run_id=run_id)
                        record_candidate_metrics(candidate, is_new=is_new)
                        frontier.record_candidate_observation(
                            candidate.platform, candidate.source_id, run_id=run_id,
                            metric_kind=candidate.qualifying_metric_kind(),
                            metric_value=candidate.qualifying_metric(),
                            metric_source=candidate.metric_source,
                            format_status=candidate.short_format_status,
                            evidence=candidate.metadata,
                        )
                        if became:
                            new_eligible += 1
                            stats["eligible_new"] += 1
                except Exception as exc:
                    stats["hashtag_search_failures"] += 1
                    errors.append(f"hashtag search #{hashtag}: {type(exc).__name__}: {str(exc)[:180]}")

        if "instagram" in providers:
            instagram_provider = providers["instagram"]
            selected_hashtags = list(dict.fromkeys(
                tag.strip().lstrip("#").casefold()
                for tag in (instagram_hashtags or [])
                if tag.strip()
            ))[:max(0, min(max_instagram_hashtags, 100))]
            for hashtag in selected_hashtags:
                if loop.time() >= deadline or getattr(instagram_provider, "blocked", False):
                    break
                try:
                    candidates = await within_budget(
                        instagram_provider.harvest_hashtag(
                            hashtag,
                            max_scrolls=instagram_max_scrolls,
                            max_reel_details=instagram_hashtag_max_reel_details,
                        )
                    )
                    stats["instagram_hashtag_requests"] += 1
                    stats["instagram_hashtag_candidates"] += len(candidates)
                    hashtag_eligible = 0
                    for candidate in candidates:
                        stats["candidates_observed"] += 1
                        is_new, became = store.upsert_candidate(
                            candidate, min_views=min_metric, run_id=run_id
                        )
                        record_candidate_metrics(candidate, is_new=is_new)
                        frontier.record_candidate_observation(
                            candidate.platform, candidate.source_id, run_id=run_id,
                            metric_kind=candidate.qualifying_metric_kind(),
                            metric_value=candidate.qualifying_metric(),
                            metric_source=candidate.metric_source,
                            format_status=candidate.short_format_status,
                            evidence=candidate.metadata,
                        )
                        if became:
                            new_eligible += 1
                            hashtag_eligible += 1
                            stats["eligible_new"] += 1
                    diagnostic = (
                        instagram_provider.hashtag_diagnostics[-1]
                        if instagram_provider.hashtag_diagnostics else {}
                    )
                    hashtag_results.append({
                        "hashtag": hashtag,
                        "candidates_observed": len(candidates),
                        "eligible_new": hashtag_eligible,
                        "status": "completed" if candidates else "empty",
                        "provider": diagnostic,
                    })
                except Exception as exc:
                    message = f"{type(exc).__name__}: {str(exc)[:180]}"
                    stats["instagram_hashtag_failures"] += 1
                    errors.append(f"instagram hashtag #{hashtag}: {message}")
                    hashtag_results.append({
                        "hashtag": hashtag,
                        "candidates_observed": 0,
                        "eligible_new": 0,
                        "status": "blocked" if getattr(instagram_provider, "blocked", False) else "failed",
                        "error": message,
                        "provider": (
                            instagram_provider.hashtag_diagnostics[-1]
                            if getattr(instagram_provider, "hashtag_diagnostics", [])
                            else {}
                        ),
                    })

            for username in instagram_creators or []:
                frontier.enqueue_creator(
                    "instagram", username.casefold().lstrip("@"), handle=username.lstrip("@"),
                    discovered_via="seed_file" if not force else "forced_seed",
                    priority_score=10_000.0, depth=0, force=force)

        creators_claimed = {"youtube": 0, "instagram": 0}
        expansions_done = 0
        while loop.time() < deadline and (
            new_eligible < target_new or continue_graph_after_target
        ):
            progressed = False
            for current_platform in (["youtube", "instagram"] if platform == "all" else [platform]):
                provider = providers.get(current_platform)
                stage_deadline = youtube_deadline if current_platform == "youtube" else instagram_deadline
                if loop.time() >= stage_deadline:
                    continue
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
                        candidates = await within_budget(provider.harvest_creator(creator.creator_id, limit=48), stage_deadline)
                        stats["creator_harvest_batches"] += 1
                    else:
                        candidates, coauthors = await within_budget(
                            provider.harvest_creator(
                                creator.handle or creator.creator_id,
                                max_scrolls=instagram_max_scrolls,
                                max_reel_details=instagram_max_reel_details,
                            ),
                            stage_deadline,
                        )
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
                        is_new, became = store.upsert_candidate(
                            candidate, min_views=min_metric, run_id=run_id)
                        record_candidate_metrics(candidate, is_new=is_new)
                        if current_platform == "youtube":
                            stats["youtube_creator_candidates"] += 1
                        elif current_platform == "instagram":
                            stats["instagram_creator_candidates"] += 1
                        frontier.record_candidate_observation(
                            candidate.platform, candidate.source_id, run_id=run_id,
                            metric_kind=candidate.qualifying_metric_kind(),
                            metric_value=candidate.qualifying_metric(),
                            metric_source=candidate.metric_source,
                            format_status=candidate.short_format_status,
                            evidence=candidate.metadata,
                        )
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
                    if current_platform == "instagram":
                        provider_diag = (
                            provider.creator_diagnostics[-1]
                            if provider.creator_diagnostics else {}
                        )
                        creator_results.append({
                            "platform": current_platform,
                            "creator_id": creator.creator_id,
                            "handle": creator.handle or creator.creator_id,
                            "candidates_observed": len(candidates),
                            "eligible_new": creator_yield,
                            "status": "completed" if candidates else "empty",
                            "provider": provider_diag,
                        })
                    if candidates:
                        frontier.finish_creator(
                            current_platform, creator.creator_id,
                            eligible_yield=creator_yield, exhausted=False)
                    else:
                        frontier.finish_creator(
                            current_platform, creator.creator_id,
                            error="empty_harvest")
                except Exception as exc:
                    message = f"{type(exc).__name__}: {str(exc)[:180]}"
                    errors.append(f"{current_platform} creator {creator.creator_id}: {message}")
                    stats["creator_failures"] += 1
                    frontier.finish_creator(current_platform, creator.creator_id, error=message)
                    if current_platform == "instagram":
                        creator_results.append({
                            "platform": current_platform,
                            "creator_id": creator.creator_id,
                            "handle": creator.handle or creator.creator_id,
                            "candidates_observed": 0,
                            "eligible_new": 0,
                            "status": "blocked" if getattr(provider, "blocked", False) else "failed",
                            "error": message,
                            "provider": (
                                provider.creator_diagnostics[-1]
                                if getattr(provider, "creator_diagnostics", [])
                                else {}
                            ),
                        })

            if ("youtube" in providers and expansions_done < max_expansions
                    and loop.time() < youtube_deadline):
                seeds = frontier.claim_seeds("youtube", limit=1)
                if seeds:
                    progressed = True
                    seed = seeds[0]
                    if int(seed["depth"]) >= max_depth:
                        frontier.finish_seed("youtube", str(seed["video_id"]))
                    else:
                        try:
                            related = await within_budget(providers["youtube"].expand_related(str(seed["video_id"]), limit=9), youtube_deadline)
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
                                is_new, became = store.upsert_candidate(
                                    candidate, min_views=min_metric, run_id=run_id)
                                record_candidate_metrics(candidate, is_new=is_new)
                                frontier.record_candidate_observation(
                                    candidate.platform, candidate.source_id, run_id=run_id,
                                    metric_kind=candidate.qualifying_metric_kind(),
                                    metric_value=candidate.qualifying_metric(),
                                    metric_source=candidate.metric_source,
                                    format_status=candidate.short_format_status,
                                    evidence=candidate.metadata,
                                )
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
        graph_summary = frontier.summary(
            "instagram" if platform == "instagram"
            else "youtube" if platform == "youtube"
            else None
        )
        request_counts = {
            name: (
                {"json_responses_observed": provider.requests_observed,
                 "responses_parsed": provider.responses_parsed,
                 "responses_unparsed": provider.responses_unparsed,
                 "creator_diagnostics": provider.creator_diagnostics,
                 "hashtag_diagnostics": provider.hashtag_diagnostics,
                 "provider_errors": provider.errors}
                if name == "instagram" else {"library_calls": provider.requests}
            )
            for name, provider in providers.items()
        }
        summary = {
            **dict(stats), **graph_summary, "run_id": run_id, "platform": platform,
            "elapsed_seconds": elapsed, "new_eligible": new_eligible,
            "target_new": target_new,
            "youtube_creator_candidates": stats["youtube_creator_candidates"],
            "youtube_related_candidates": stats["related_candidates"],
            "min_metric": min_metric, "max_depth": max_depth,
            "stage_deadlines_seconds_from_start": {
                "youtube": round(youtube_deadline - started, 2),
                "youtube_seed": round(youtube_seed_deadline - started, 2),
                "instagram": round(instagram_deadline - started, 2),
            },
            "metric_policy": {
                "youtube": "numeric views",
                "instagram": "numeric plays; retained separately from views",
            },
            "provider_requests": request_counts,
            "discovery_stage_counts": {
                "youtube_seed_search_results": stats["seed_search_results"],
                "youtube_seed_detail_candidates": stats["seed_detail_candidates"],
                "youtube_hashtag_search_results": stats["hashtag_search_results"],
                "youtube_hashtag_detail_candidates": stats["hashtag_detail_candidates"],
                "youtube_creator_candidates": stats["youtube_creator_candidates"],
                "youtube_related_candidates": stats["related_candidates"],
                "instagram_hashtag_candidates": stats["instagram_hashtag_candidates"],
                "instagram_creator_candidates": stats["instagram_creator_candidates"],
                "all_candidates_observed": (
                    stats["candidates_observed"] + stats["related_candidates"]
                ),
            },
            "continue_graph_after_target": continue_graph_after_target,
            },
            "creator_results": creator_results,
            "hashtag_results": hashtag_results,
            "hashtags_with_candidates": sum(
                item["candidates_observed"] > 0 for item in hashtag_results
            ),
            "creators_with_candidates": sum(
                item["candidates_observed"] > 0 for item in creator_results
            ),
            "creators_empty": sum(
                item["status"] == "empty" for item in creator_results
            ),
            "errors": len(errors),
            "error_details": errors[:100],
        }
        store.finish_run(run_id, {
            "scanned": stats["candidates_observed"] + stats["related_candidates"],
            "new_eligible": new_eligible, "duplicates": 0,
            "errors": (
                stats["creator_failures"] + stats["seed_search_failures"]
                + stats["expansion_failures"] + stats["instagram_hashtag_failures"]
            ),
            **summary})
        return summary
    finally:
        for provider_name, provider in providers.items():
            close = getattr(provider, "close", None)
            if close:
                try:
                    result = close()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as exc:
                    # Shutdown of a browser process can race with Chrome being
                    # closed by the user. Never replace a useful run summary or
                    # the original provider failure with a teardown traceback.
                    errors.append(
                        f"{provider_name} provider cleanup: "
                        f"{type(exc).__name__}: {str(exc)[:160]}"
                    )
