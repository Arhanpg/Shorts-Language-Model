"""CLI commands for resilient non-API discovery and authorized acquisition."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import random
import subprocess
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import typer
from rich.console import Console
from rich.table import Table

from shorts_intelligence.discovery.browser_session import find_chrome_executable
from shorts_intelligence.discovery.downloader import download_candidate
from shorts_intelligence.discovery.hashtag_loader import load_instagram_hashtags
from shorts_intelligence.discovery.legacy_providers import (
    InstagramSearchProvider,
    ProviderUnavailable,
    YouTubeSearchProvider,
    YouTubeShortsSurfaceProvider,
)
from shorts_intelligence.discovery.models import AcquisitionAuthorization, DiscoveredCandidate
from shorts_intelligence.discovery.query_planner import (
    SearchQuery,
    build_instagram_query_pool,
    build_youtube_hashtag_pool,
    build_youtube_query_pool,
    select_due_queries,
)
from shorts_intelligence.discovery.seed_loader import load_instagram_creator_seeds
from shorts_intelligence.discovery.storage import DiscoveryStore
from shorts_intelligence.media.probe import sha256_file

discovery_app = typer.Typer(
    name="discover",
    help="Search public web results for YouTube Shorts and Instagram Reels without platform API keys.",
    no_args_is_help=True,
)
console = Console()

_DEFAULT_YOUTUBE_QUERIES = [
    "viral YouTube Shorts India",
    "trending YouTube Shorts India",
    "Hindi comedy Shorts",
    "Indian cricket Shorts",
    "Indian education facts Shorts",
    "Indian technology facts Shorts",
    "Marathi comedy Shorts",
    "Kannada comedy Shorts",
    "Indian cooking recipe Shorts",
    "Indian travel Shorts",
    "Indian gaming Shorts",
    "Indian fitness Shorts",
]
_DEFAULT_INSTAGRAM_QUERIES = [
    "viral Instagram Reels India",
    "trending Reels India",
    "Hindi comedy Reels",
    "Indian cricket Reels",
    "Indian education facts Reels",
    "Indian technology Reels",
    "Marathi comedy Reels",
    "Kannada comedy Reels",
    "Indian cooking recipe Reels",
    "Indian travel Reels",
    "Indian gaming Reels",
    "Indian fitness Reels",
]


def _stage_deadlines(platform: str, *, started_at: float, budget_seconds: int) -> tuple[float, float]:
    """Return fair YouTube/Instagram deadlines for a bounded discovery run."""
    overall = started_at + budget_seconds
    youtube = overall if platform == "youtube" else started_at + budget_seconds * 0.62
    instagram = overall if platform == "instagram" else started_at + budget_seconds * 0.95
    return youtube, instagram


def _should_run_instagram_stage(platform: str, *, now: float, deadline: float) -> bool:
    """Run Instagram when selected and there is still shared runtime budget."""
    return platform in {"all", "instagram"} and now < deadline


def _write_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


def _add_provider_errors(
    provider_errors: Counter[str],
    errors: list[str],
    platform: str,
    provider_messages: list[str],
) -> None:
    if not provider_messages:
        return
    provider_errors[platform] += len(provider_messages)
    for message in provider_messages:
        errors.append(f"{platform}: {message[:300]}")
    provider_messages.clear()


@discovery_app.command("instagram-login")
def instagram_login(
    username: str = typer.Option(..., "--username", prompt=True),
    session_file: Path = typer.Option(
        Path(".shortslm/instagram.session"), "--session-file"
    ),
) -> None:
    """Create a local Instaloader session using its normal interactive login flow."""
    try:
        import instaloader
    except ImportError as exc:
        console.print('[red]Install discovery dependencies first: pip install -e ".[legacy-discovery]"[/red]')
        raise typer.Exit(code=2) from exc
    session_path = session_file.expanduser().resolve()
    session_path.parent.mkdir(parents=True, exist_ok=True)
    loader = instaloader.Instaloader(
        quiet=False,
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_comments=False,
        save_metadata=False,
        max_connection_attempts=1,
        request_timeout=12.0,
    )
    try:
        loader.interactive_login(username)
        authenticated_as = loader.test_login()
        if not authenticated_as or authenticated_as.casefold() != username.casefold():
            raise RuntimeError("Instagram did not confirm the requested account session.")
        loader.save_session_to_file(filename=str(session_path))
    except Exception as exc:
        message = str(exc)
        if "checkpoint" in message.casefold():
            console.print(
                "[yellow]Instagram requires an account checkpoint. Complete verification "
                "in Instagram's official app or browser, wait until the account is usable, "
                "then retry this login command. ShortsLM will not bypass the checkpoint.[/yellow]"
            )
        console.print(f"[red]Instagram login/session creation failed: {type(exc).__name__}: {message[:220]}[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        with contextlib.suppress(Exception):
            loader.close()
    console.print(f"[green]Local Instagram session saved:[/green] {session_path}")
    console.print("[yellow]Keep this file private. Never commit it, share it, or paste its contents into chat.[/yellow]")


@discovery_app.command("run")
def run_discovery(
    platform: Literal["all", "youtube", "instagram"] = typer.Option("all", "--platform"),
    query: list[str] = typer.Option(
        [],
        "--query",
        "-q",
        help="Custom search phrase. Repeat this option for multiple topics.",
    ),
    target_new: int = typer.Option(100, "--target-new", min=1, max=2000),
    min_views: int = typer.Option(1_000_000, "--min-views", min=0),
    max_candidates: int = typer.Option(1500, "--max-candidates", min=1, max=20000),
    results_per_query: int = typer.Option(
        30, "--results-per-query", min=1, max=50,
        help="Maximum bounded results consumed from each search query, including continuation pages.",
    ),
    max_runtime_seconds: int = typer.Option(
        180, "--max-runtime-seconds", min=30, max=600,
        help="Hard overall discovery-run budget. The command stops cleanly when it expires.",
    ),
    youtube_request_timeout: float = typer.Option(
        6.0, "--youtube-request-timeout", min=2.0, max=10.0,
        help="Per-request YouTube timeout. Retries are disabled in discovery mode.",
    ),
    youtube_request_interval: float = typer.Option(
        0.5, "--youtube-request-interval", min=0.25, max=5.0,
        help="Minimum interval between YouTube HTTP requests.",
    ),
    enrichment_budget_seconds: int = typer.Option(
        20, "--enrichment-budget-seconds", min=0, max=120,
        help="Maximum wall-clock time reserved for optional YouTube detail enrichment.",
    ),
    max_search_queries: int = typer.Option(
        24, "--max-search-queries", min=1, max=100,
        help="Maximum distinct YouTube text searches in this run.",
    ),
    max_hashtag_shelves: int = typer.Option(
        8, "--max-hashtag-shelves", min=0, max=30,
        help="Maximum independent YouTube hashtag Shorts shelves to inspect.",
    ),
    max_channel_expansion: int = typer.Option(
        8, "--max-channel-expansion", min=0, max=30,
        help="Maximum creator Shorts tabs to inspect after discovering their channels.",
    ),
    channel_shorts_per_channel: int = typer.Option(
        15, "--channel-shorts-per-channel", min=1, max=50,
        help="Bounded number of recent Shorts to inspect per discovered channel.",
    ),
    instagram_max_search_queries: int = typer.Option(
        8, "--instagram-max-search-queries", min=1, max=40,
        help="Maximum Instagram web searches in this run; each is time-bounded.",
    ),
    query_cooldown_days: int = typer.Option(
        1, "--query-cooldown-days", min=0, max=90,
        help="Minimum age before a query/locale combination is reused; 0 forces a refresh.",
    ),
    metadata_enrichment_limit: int = typer.Option(
        40, "--metadata-enrichment-limit", min=0, max=200,
        help="Maximum YouTube detail lookups for new candidates missing views or duration.",
    ),
    seed: int | None = typer.Option(
        None, "--seed",
        help="Optional reproducible shuffle seed. Without it, query selection is randomized.",
    ),
    database: Path = typer.Option(Path(".shortslm/discovery.sqlite3"), "--database"),
    report: Path = typer.Option(Path("outputs/discovery/latest.json"), "--report"),
    instagram_session_user: str | None = typer.Option(
        None,
        "--instagram-session-user",
        help="Optional Instaloader username with an existing local session file.",
    ),
    instagram_session_file: Path | None = typer.Option(
        Path(".shortslm/instagram.session"),
        "--instagram-session-file",
        help="Local Instaloader session file; never put it in Git.",
    ),
    instagram_hashtag: list[str] = typer.Option(
        [],
        "--instagram-hashtag",
        help="Optional hashtag target. Requires a valid local Instaloader session.",
    ),
    instagram_region: str = typer.Option(
        "in-en",
        "--instagram-region",
        help="Default DDGS region for custom Instagram queries, for example in-en or in-hi.",
    ),
    instagram_backend: str = typer.Option(
        "bing,brave,duckduckgo",
        "--instagram-backend",
        help="Comma-separated DDGS backend list. Avoids auto-selection of slow engines.",
    ),
    instagram_fallback_backend: str = typer.Option(
        "google",
        "--instagram-fallback-backend",
        help="One fallback DDGS engine used only after the primary backend list fails.",
    ),
    instagram_ytdlp_fallback: bool = typer.Option(
        False,
        "--instagram-ytdlp-fallback",
        help="Opt in to yt-dlp metadata-only fallback after non-access-related Instaloader parser errors.",
    ),
    instagram_pages: int = typer.Option(
        1,
        "--instagram-pages",
        min=1,
        max=1,
        help="Number of public indexed result pages to inspect per query (kept to one for bounded runs).",
    ),
    instagram_timeout: int = typer.Option(
        6, "--instagram-timeout", min=3, max=10,
        help="DDGS request timeout in seconds.",
    ),
    instagram_max_lookups: int = typer.Option(
        40, "--instagram-max-lookups", min=1, max=100,
        help="Maximum individual Instagram metadata lookups per run.",
    ),
    instagram_request_timeout: float = typer.Option(
        6.0, "--instagram-request-timeout", min=3.0, max=12.0,
        help="Instaloader per-request timeout in seconds; the discovery run also has a global deadline.",
    ),
    pause_seconds: float = typer.Option(1.0, "--pause-seconds", min=1.0, max=10.0),
) -> None:
    """Discover Shorts/Reels from multiple bounded public discovery surfaces.

    YouTube combines bounded paginated Shorts search, hashtag Shorts shelves and
    Shorts tabs for discovered channels. Instagram uses indexed Reel URLs and a
    user-owned Instaloader session when configured. This command discovers
    metadata only; it does not download media.
    """
    run_id = uuid.uuid4().hex
    run_started_at = datetime.now(UTC)
    run_started_monotonic = time.monotonic()
    run_deadline = run_started_monotonic + max_runtime_seconds
    # Fair stage windows in combined mode prevent a slow provider from
    # consuming the entire runtime before the other platform can run.
    youtube_deadline, instagram_deadline = _stage_deadlines(
        platform, started_at=run_started_monotonic, budget_seconds=max_runtime_seconds
    )
    stop_reason = "completed"
    enrichment_budget_exhausted = False
    rng: random.Random | random.SystemRandom = (
        random.Random(seed) if seed is not None else random.SystemRandom()
    )
    errors: list[str] = []
    provider_errors: Counter[str] = Counter()
    candidates: list[DiscoveredCandidate] = []
    query_count: Counter[str] = Counter()
    raw_by_platform: Counter[str] = Counter()
    query_records: list[tuple[str, SearchQuery, int, int]] = []
    youtube_provider: YouTubeSearchProvider | None = None
    youtube_surface_provider: YouTubeShortsSurfaceProvider | None = None
    instagram_provider: InstagramSearchProvider | None = None

    youtube_pool = build_youtube_query_pool(query)
    youtube_hashtag_pool = build_youtube_hashtag_pool(query)
    instagram_pool = build_instagram_query_pool(query, default_region=instagram_region)
    stats: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    status_by_platform: dict[str, Counter[str]] = {
        "youtube": Counter(),
        "instagram": Counter(),
    }
    unique_candidates: dict[tuple[str, str], DiscoveredCandidate] = {}
    provisional_new_eligible_ids: set[str] = set()

    with DiscoveryStore(database) as store:
        youtube_queries: list[SearchQuery] = []
        youtube_hashtag_queries: list[SearchQuery] = []
        instagram_queries: list[SearchQuery] = []
        if platform in {"all", "youtube"}:
            youtube_history = store.query_history("youtube")
            youtube_performance = store.query_performance("youtube")
            youtube_queries = select_due_queries(
                youtube_pool,
                youtube_history,
                limit=max_search_queries,
                cooldown_days=query_cooldown_days,
                rng=rng,
                performance=youtube_performance,
                now=run_started_at,
            )
            youtube_hashtag_queries = select_due_queries(
                youtube_hashtag_pool,
                youtube_history,
                limit=max_hashtag_shelves,
                cooldown_days=query_cooldown_days,
                rng=rng,
                performance=youtube_performance,
                now=run_started_at,
            )
        if platform in {"all", "instagram"}:
            instagram_queries = select_due_queries(
                instagram_pool,
                store.query_history("instagram"),
                limit=instagram_max_search_queries,
                cooldown_days=query_cooldown_days,
                rng=rng,
                performance=store.query_performance("instagram"),
                now=run_started_at,
            )

        store.start_run(run_id, target_new, min_views, started_at=run_started_at)

        try:
            if platform in {"all", "youtube"}:
                youtube_provider = YouTubeSearchProvider(
                    request_timeout=youtube_request_timeout,
                    request_interval=youtube_request_interval,
                    max_retries=1,
                    detail_enrichment_limit=metadata_enrichment_limit,
                )
                console.print(
                    f"[cyan]YouTube discovery: {len(youtube_queries)} text queries + "
                    f"{len(youtube_hashtag_queries)} hashtag shelves selected; "
                    f"up to {results_per_query} results/source; "
                    f"{max_runtime_seconds}s total run budget.[/cyan]"
                )
                for query_index, search_query in enumerate(youtube_queries, start=1):
                    if youtube_provider.circuit_open:
                        stop_reason = "youtube_circuit_open"
                        break
                    if time.monotonic() + (youtube_request_timeout * 4) + youtube_request_interval > youtube_deadline:
                        stop_reason = "runtime_budget_reached"
                        break
                    console.print(
                        f"[dim]YouTube {query_index}/{len(youtube_queries)} · "
                        f"{search_query.language}/{search_query.region} · "
                        f"{search_query.query}[/dim]"
                    )
                    query_started = time.monotonic()
                    before = youtube_provider.search_results_seen
                    query_candidates = list(
                        youtube_provider.search(
                            search_query.query,
                            limit=results_per_query,
                            language=search_query.language,
                            region=search_query.region,
                        )
                    )
                    raw_count = youtube_provider.search_results_seen - before
                    raw_by_platform["youtube"] += raw_count
                    query_count["youtube"] += 1
                    query_records.append(("youtube", search_query, raw_count, len(query_candidates)))
                    candidates.extend(query_candidates)
                    for item in query_candidates:
                        if item.short_format_status == "confirmed":
                            metric = item.qualifying_metric()
                            if metric is not None and metric >= min_views and not store.has_candidate(
                                item.platform, item.source_id
                            ):
                                provisional_new_eligible_ids.add(item.source_id)
                    console.print(
                        f"[dim]  -> {raw_count} bounded search hits, {len(query_candidates)} unique IDs "
                        f"in {time.monotonic() - query_started:.1f}s; "
                        f"{len(provisional_new_eligible_ids)} provisional new qualifying IDs[/dim]"
                    )
                    if len(provisional_new_eligible_ids) >= target_new:
                        stop_reason = "target_reached_during_search"
                        break
                    if youtube_provider.circuit_open:
                        stop_reason = "youtube_circuit_open"
                        break

            if (
                platform in {"all", "youtube"}
                and youtube_provider is not None
                and not youtube_provider.circuit_open
                and time.monotonic() < youtube_deadline
            ):
                youtube_surface_provider = YouTubeShortsSurfaceProvider(
                    request_timeout=youtube_request_timeout
                )
                for shelf_index, shelf_query in enumerate(youtube_hashtag_queries, start=1):
                    if time.monotonic() + youtube_request_timeout > youtube_deadline:
                        stop_reason = "runtime_budget_reached"
                        break
                    before = youtube_surface_provider.search_results_seen
                    shelf_candidates = youtube_surface_provider.search_hashtag(
                        shelf_query.query, limit=results_per_query
                    )
                    raw_count = youtube_surface_provider.search_results_seen - before
                    raw_by_platform["youtube"] += raw_count
                    query_count["youtube"] += 1
                    query_records.append(("youtube", shelf_query, raw_count, len(shelf_candidates)))
                    candidates.extend(shelf_candidates)
                    console.print(
                        f"[dim]YouTube hashtag shelf {shelf_index}/"
                        f"{len(youtube_hashtag_queries)} · #{shelf_query.query} "
                        f"-> {len(shelf_candidates)} Shorts[/dim]"
                    )

                discovered_channels: dict[str, DiscoveredCandidate] = {}
                for item in candidates:
                    if item.platform != "youtube":
                        continue
                    channel_id = item.metadata.get("channel_id")
                    if isinstance(channel_id, str) and channel_id.startswith("UC"):
                        previous = discovered_channels.get(channel_id)
                        if previous is None or (item.view_count or 0) > (previous.view_count or 0):
                            discovered_channels[channel_id] = item
                expansion_targets = sorted(
                    discovered_channels.items(),
                    key=lambda pair: pair[1].view_count or 0,
                    reverse=True,
                )[:max_channel_expansion]
                for channel_index, (channel_id, source_candidate) in enumerate(
                    expansion_targets, start=1
                ):
                    if time.monotonic() + youtube_request_timeout > youtube_deadline:
                        stop_reason = "runtime_budget_reached"
                        break
                    before = youtube_surface_provider.search_results_seen
                    channel_items = youtube_surface_provider.search_channel_shorts(
                        channel_id, limit=channel_shorts_per_channel
                    )
                    raw_count = youtube_surface_provider.search_results_seen - before
                    raw_by_platform["youtube"] += raw_count
                    query_count["youtube"] += 1
                    channel_query = SearchQuery(
                        platform="youtube",
                        query=channel_id,
                        language=str(source_candidate.metadata.get("search_language") or "en"),
                        region=str(source_candidate.metadata.get("search_region") or "IN"),
                        strategy="channel_shorts_tab",
                    )
                    query_records.append(("youtube", channel_query, raw_count, len(channel_items)))
                    candidates.extend(channel_items)
                    console.print(
                        f"[dim]YouTube channel Shorts {channel_index}/"
                        f"{len(expansion_targets)} · {channel_id} "
                        f"-> {len(channel_items)} Shorts[/dim]"
                    )

            # In combined mode, one platform's provisional target must not
            # silently prevent the other selected platform from running.
            if _should_run_instagram_stage(
                platform, now=time.monotonic(), deadline=instagram_deadline
            ):
                instagram_provider = InstagramSearchProvider(
                    session_username=instagram_session_user,
                    session_file=str(instagram_session_file) if instagram_session_file else None,
                    request_pause_seconds=pause_seconds,
                    region=instagram_region,
                    backend=instagram_backend,
                    fallback_backend=instagram_fallback_backend,
                    pages=instagram_pages,
                    search_timeout=instagram_timeout,
                    request_timeout=instagram_request_timeout,
                    max_lookups=instagram_max_lookups,
                    enable_ytdlp_fallback=instagram_ytdlp_fallback,
                )
                if instagram_session_user and not instagram_provider.preflight():
                    errors.extend(instagram_provider.errors)
                    console.print(
                        f"[yellow]Instagram authentication preflight failed: "
                        f"{instagram_provider.circuit_reason}[/yellow]"
                    )
                if not instagram_session_user:
                    console.print(
                        "[yellow]Instagram metadata mode: anonymous. A local user-owned session "
                        "may improve access but cannot guarantee metadata availability.[/yellow]"
                    )
                for query_index, search_query in enumerate(instagram_queries, start=1):
                    if instagram_provider.circuit_open:
                        stop_reason = "instagram_circuit_open"
                        break
                    if time.monotonic() >= instagram_deadline:
                        stop_reason = "runtime_budget_reached"
                        break
                    console.print(
                        f"[dim]Instagram {query_index}/{len(instagram_queries)} · "
                        f"{search_query.region} · {search_query.query}[/dim]"
                    )
                    instagram_provider.region = search_query.region
                    before = instagram_provider.search_results_seen
                    query_candidates = list(
                        instagram_provider.search(
                            search_query.query,
                            limit=min(results_per_query, 30),
                            deadline=instagram_deadline,
                        )
                    )
                    raw_count = instagram_provider.search_results_seen - before
                    raw_by_platform["instagram"] += raw_count
                    query_count["instagram"] += 1
                    query_records.append(("instagram", search_query, raw_count, len(query_candidates)))
                    candidates.extend(query_candidates)
                    if instagram_provider.circuit_open:
                        break

                for tag in instagram_hashtag:
                    if instagram_provider.circuit_open or time.monotonic() >= instagram_deadline:
                        stop_reason = "runtime_budget_reached" if time.monotonic() >= instagram_deadline else "instagram_circuit_open"
                        break
                    before = instagram_provider.search_results_seen
                    query_candidates = list(
                        instagram_provider.search_hashtag(
                            tag,
                            limit=min(results_per_query, instagram_max_lookups),
                            deadline=instagram_deadline,
                        )
                    )
                    raw_count = instagram_provider.search_results_seen - before
                    raw_by_platform["instagram"] += raw_count
                    candidates.extend(query_candidates)

        except ProviderUnavailable as exc:
            console.print(f"[bold red]Discovery dependency missing:[/bold red] {exc}")
            if youtube_provider:
                youtube_provider.close()
            if instagram_provider:
                instagram_provider.close()
            store.finish_run(
                run_id,
                {
                    "scanned": 0,
                    "new_eligible": 0,
                    "duplicates": 0,
                    "errors": 1,
                    "status": "dependency_missing",
                    "error": str(exc)[:300],
                },
            )
            raise typer.Exit(code=2) from exc
        except Exception as exc:
            stats["unexpected_errors"] += 1
            errors.append(f"Unexpected discovery error: {type(exc).__name__}: {str(exc)[:300]}")

        # Persist query history even when a query returned zero results. That
        # stops a failing phrase/backend from being retried 24 times next run.
        for query_platform, search_query, raw_count, candidate_count in query_records:
            store.record_query(
                platform=query_platform,
                query_key=search_query.key,
                query=search_query.query,
                language=search_query.language,
                region=search_query.region,
                strategy=search_query.strategy,
                raw_results=raw_count,
                candidate_count=candidate_count,
                run_at=run_started_at,
            )

        # Collapse cross-query repeats by platform/source ID. Prefer the record
        # with the stronger metrics and retain the query provenance that found it.
        for candidate in candidates:
            identity = (candidate.platform, candidate.source_id)
            previous = unique_candidates.get(identity)
            if previous is None:
                unique_candidates[identity] = candidate
                continue
            stats["duplicate_search_results"] += 1
            previous_metric = previous.qualifying_metric()
            candidate_metric = candidate.qualifying_metric()
            selected = candidate if (
                candidate_metric is not None
                and (previous_metric is None or candidate_metric > previous_metric)
            ) else previous
            query_variants = {
                str(value)
                for metadata_item in (previous.metadata, candidate.metadata)
                for value in (
                    [metadata_item.get("search_query")]
                    if isinstance(metadata_item.get("search_query"), str)
                    else metadata_item.get("discovery_query_variants", [])
                )
                if isinstance(value, str) and value
            }
            locale_variants = {
                f"{metadata_item.get('search_language', '')}-{metadata_item.get('search_region', '')}"
                for metadata_item in (previous.metadata, candidate.metadata)
                if metadata_item.get("search_language") and metadata_item.get("search_region")
            }
            metadata = {
                **previous.metadata,
                **candidate.metadata,
                "discovery_query_variants": sorted(query_variants),
                "discovery_locale_variants": sorted(locale_variants),
            }
            unique_candidates[identity] = selected.model_copy(update={"metadata": metadata})

        # New platform IDs are evaluated first. This makes max_candidates a
        # useful fresh-yield budget rather than spending the budget on old rows.
        fresh: list[DiscoveredCandidate] = []
        known: list[DiscoveredCandidate] = []
        for candidate in unique_candidates.values():
            if store.has_candidate(candidate.platform, candidate.source_id):
                known.append(candidate)
            else:
                fresh.append(candidate)
        rng.shuffle(fresh)
        rng.shuffle(known)
        ordered = fresh + known

        # Selectively hydrate new YouTube records whose search-page view count
        # or duration is missing. This is intentionally bounded and uses the
        # same client rate limiter; it never calls the downloader.
        if (
            youtube_provider
            and metadata_enrichment_limit > 0
            and enrichment_budget_seconds > 0
            and stop_reason != "target_reached_during_search"
        ):
            enriched: list[DiscoveredCandidate] = []
            remaining = metadata_enrichment_limit
            enrichment_deadline = min(
                run_deadline, time.monotonic() + enrichment_budget_seconds
            )
            console.print(
                f"[cyan]YouTube metadata enrichment: at most {remaining} lookups, "
                f"{max(0, enrichment_deadline - time.monotonic()):.0f}s budget.[/cyan]"
            )
            for candidate_index, candidate in enumerate(ordered):
                if remaining <= 0:
                    enriched.extend(ordered[candidate_index:])
                    break
                if time.monotonic() + youtube_request_timeout + youtube_request_interval > enrichment_deadline:
                    enrichment_budget_exhausted = True
                    enriched.extend(ordered[candidate_index:])
                    break
                if (
                    candidate.platform == "youtube"
                    and (candidate.view_count is None or candidate.duration_seconds is None)
                    and not store.has_candidate(candidate.platform, candidate.source_id)
                ):
                    language = str(candidate.metadata.get("search_language") or "en")
                    region = str(candidate.metadata.get("search_region") or "IN")
                    before = youtube_provider.enrichment_attempts
                    console.print(
                        f"[dim]YouTube detail lookup "
                        f"{before + 1}/{metadata_enrichment_limit} · {candidate.source_id}[/dim]"
                    )
                    candidate = youtube_provider.enrich(
                        candidate, language=language, region=region
                    )
                    remaining -= youtube_provider.enrichment_attempts - before
                enriched.append(candidate)
                if youtube_provider.circuit_open or time.monotonic() >= enrichment_deadline:
                    enrichment_budget_exhausted = True
                    break
            ordered = enriched + [c for c in ordered[len(enriched):]]

        for candidate in ordered:
            if stats["unique_evaluated"] >= max_candidates:
                break
            stats["unique_evaluated"] += 1

            is_new, became_eligible = store.upsert_candidate(
                candidate,
                min_views=min_views,
                run_id=run_id,
            )
            stored = store.get_candidate(candidate.platform, candidate.source_id)
            if stored is None:
                stats["storage_errors"] += 1
                continue

            if not is_new:
                stats["already_known_source_ids"] += 1
            status_counts[stored.status] += 1
            status_by_platform[candidate.platform][stored.status] += 1

            if stored.status == "eligible":
                if is_new:
                    stats["new_eligible"] += 1
                elif became_eligible:
                    stats["known_ids_became_eligible"] += 1
                else:
                    stats["already_eligible"] += 1
            elif stored.status == "metric_unknown":
                stats["missing_view_metric"] += 1
            elif stored.status == "below_threshold":
                stats["below_threshold"] += 1
            elif stored.status == "format_unknown":
                stats["format_uncertain"] += 1
            elif stored.status == "not_short":
                stats["not_short"] += 1

            if stats["new_eligible"] >= target_new:
                break

        # Collect provider diagnostics after metadata enrichment so any detail
        # lookup errors are included in the run totals. Close all network sessions.
        if youtube_provider:
            for message in youtube_provider.errors:
                errors.append(f"youtube: {message[:300]}")
            provider_errors["youtube"] += len(youtube_provider.errors)
            if youtube_provider.circuit_reason:
                errors.append(f"youtube circuit opened: {youtube_provider.circuit_reason}")
            youtube_provider.close()
        if youtube_surface_provider:
            for message in youtube_surface_provider.errors:
                errors.append(f"youtube_surface: {message[:300]}")
            provider_errors["youtube"] += len(youtube_surface_provider.errors)
        if instagram_provider:
            for message in instagram_provider.errors:
                errors.append(f"instagram: {message[:300]}")
            provider_errors["instagram"] += len(instagram_provider.errors)
            if instagram_provider.circuit_reason:
                errors.append(f"instagram circuit opened: {instagram_provider.circuit_reason}")
            instagram_provider.close()

        if time.monotonic() >= run_deadline and stop_reason == "completed":
            stop_reason = "runtime_budget_reached"

        # Include exact provider totals in durable run history.
        total_provider_errors = sum(provider_errors.values()) + stats["unexpected_errors"]
        run_summary: dict[str, object] = {
            **dict(stats),
            "scanned": stats["unique_evaluated"],
            "new_eligible": stats["new_eligible"],
            "duplicates": stats["duplicate_search_results"],
            "errors": total_provider_errors,
            "query_count": dict(query_count),
            "raw_search_results": dict(raw_by_platform),
            "query_status_counts": {
                name: dict(counts) for name, counts in status_by_platform.items()
            },
            "stop_reason": stop_reason,
            "elapsed_seconds": round(time.monotonic() - run_started_monotonic, 2),
        }
        store.finish_run(run_id, run_summary)
        database_counts = store.summary()
        database_by_platform = store.summary_by_platform()
        query_history_counts = store.query_summary()

    youtube_raw = raw_by_platform["youtube"]
    instagram_raw = raw_by_platform["instagram"]
    yt_enrichment_attempts = youtube_provider.enrichment_attempts if youtube_provider else 0
    yt_enrichment_successes = youtube_provider.enrichment_successes if youtube_provider else 0
    ig_metadata_lookups = instagram_provider.metadata_lookups if instagram_provider else 0
    ig_metadata_successes = instagram_provider.metadata_successes if instagram_provider else 0
    ig_metadata_failures = instagram_provider.metadata_failures if instagram_provider else 0
    ig_lookup_backlog = instagram_provider.lookup_backlog if instagram_provider else 0
    ig_ddgs_failures = instagram_provider.ddgs_failures if instagram_provider else 0

    if time.monotonic() >= run_deadline and stop_reason == "completed":
        stop_reason = "runtime_budget_reached"
    elapsed_seconds = round(time.monotonic() - run_started_monotonic, 2)
    payload: dict[str, object] = {
        "run_id": run_id,
        "started_at": run_started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "platform": platform,
        "platform_execution": {
            "youtube": {
                "selected": platform in {"all", "youtube"},
                "queries_selected": len(youtube_queries),
                "queries_executed": query_count["youtube"],
                "raw_results": youtube_raw,
                "status": (
                    "not_selected" if platform == "instagram"
                    else "circuit_open" if youtube_provider and youtube_provider.circuit_open
                    else "completed" if query_count["youtube"]
                    else "no_queries_due" if not youtube_queries
                    else "not_started"
                ),
                "circuit_reason": youtube_provider.circuit_reason if youtube_provider else None,
            },
            "instagram": {
                "selected": platform in {"all", "instagram"},
                "queries_selected": len(instagram_queries),
                "queries_executed": query_count["instagram"],
                "raw_results": instagram_raw,
                "status": (
                    "not_selected" if platform == "youtube"
                    else "circuit_open" if instagram_provider and instagram_provider.circuit_open
                    else "completed" if query_count["instagram"]
                    else "no_queries_due" if not instagram_queries
                    else "not_started"
                ),
                "circuit_reason": instagram_provider.circuit_reason if instagram_provider else None,
            },
        },
        "target_new": target_new,
        "runtime_budget_seconds": max_runtime_seconds,
        "elapsed_seconds": elapsed_seconds,
        "stop_reason": stop_reason,
        "youtube_search_pages_fetched": youtube_provider.search_pages_fetched if youtube_provider else 0,
        "youtube_queries_completed": youtube_provider.search_queries_completed if youtube_provider else 0,
        "youtube_duplicate_results_within_queries": youtube_provider.duplicate_results if youtube_provider else 0,
        "youtube_discovery_surfaces": {
            "text_search_queries": len(youtube_queries),
            "hashtag_shelves_selected": len(youtube_hashtag_queries),
            "hashtag_shelves_completed": youtube_surface_provider.hashtag_shelves_completed if youtube_surface_provider else 0,
            "channel_tabs_completed": youtube_surface_provider.channel_tabs_completed if youtube_surface_provider else 0,
            "raw_surface_results": youtube_surface_provider.search_results_seen if youtube_surface_provider else 0,
        },
        "youtube_request_timeout_seconds": youtube_request_timeout,
        "youtube_request_retries": 1,
        "youtube_stage_deadline_seconds_from_start": round(youtube_deadline - run_started_monotonic, 2),
        "min_views": min_views,
        "raw_search_results": {
            "youtube": youtube_raw,
            "instagram": instagram_raw,
            "total": youtube_raw + instagram_raw,
        },
        "queries_executed": dict(query_count),
        "query_history_counts": query_history_counts,
        "query_cooldown_days": query_cooldown_days,
        "query_rotation": {
            "youtube_selected": [q.query for q in youtube_queries],
            "instagram_selected": [q.query for q in instagram_queries],
        },
        "unique_candidates_evaluated": stats["unique_evaluated"],
        "duplicate_search_results": stats["duplicate_search_results"],
        "already_known_source_ids": stats["already_known_source_ids"],
        "new_eligible": stats["new_eligible"],
        "already_eligible": stats["already_eligible"],
        "known_ids_became_eligible": stats["known_ids_became_eligible"],
        "missing_view_metric": stats["missing_view_metric"],
        "below_threshold": stats["below_threshold"],
        "format_uncertain": stats["format_uncertain"],
        "not_short": stats["not_short"],
        "youtube_metadata_enrichment": {
            "attempted": yt_enrichment_attempts,
            "succeeded": yt_enrichment_successes,
            "limit": metadata_enrichment_limit,
            "budget_seconds": enrichment_budget_seconds,
            "budget_exhausted": enrichment_budget_exhausted,
        },
        "instagram_metadata": {
            "lookups": ig_metadata_lookups,
            "succeeded": ig_metadata_successes,
            "failed": ig_metadata_failures,
            "not_attempted_due_to_lookup_cap": ig_lookup_backlog,
            "ddgs_failures": ig_ddgs_failures,
            "circuit_open": instagram_provider.circuit_open if instagram_provider else False,
            "circuit_reason": instagram_provider.circuit_reason if instagram_provider else None,
            "lookup_limit": instagram_max_lookups,
            "request_timeout_seconds": instagram_request_timeout,
            "ddgs_timeout_seconds": instagram_timeout,
            "stage_deadline_seconds_from_start": round(instagram_deadline - run_started_monotonic, 2),
            "stage_budget_policy": "reserved_stage_window",
            "auth_mode": instagram_provider.auth_mode if instagram_provider else (
                "session_configured_not_started" if instagram_session_user else "anonymous"
            ),
            "session_authenticated": instagram_provider.session_authenticated if instagram_provider else False,
            "session_username_configured": bool(instagram_session_user),
        },
        "storage_errors": stats["storage_errors"],
        "provider_errors": total_provider_errors,
        "provider_errors_by_platform": dict(provider_errors),
        "provider_error_details": errors[:60],
        "run_status_counts": dict(status_counts),
        "run_status_counts_by_platform": {
            name: dict(counts) for name, counts in status_by_platform.items()
        },
        "database_status_counts": database_counts,
        "database_status_counts_by_platform": database_by_platform,
        "database_path": str(database.expanduser()),
        "sampling_note": (
            "YouTube combines bounded ytscrape Shorts-filtered search with yt-dlp hashtag "
            "Shorts shelves and discovered-channel Shorts tabs. Instagram URLs are indexed "
            "by public web search and metadata is resolved with Instaloader, anonymously unless "
            "a user-owned local session is configured. Both remain best-effort, non-uniform "
            "samples; only new unique IDs with confirmed format and observed view_count >= "
            "the threshold count."
        ),
        "media_downloaded": 0,
    }
    _write_report(report, payload)

    table = Table(title="ShortsLM discovery diagnostics")
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    metrics = [
        ("YouTube Shorts search hits", youtube_raw),
        ("Instagram indexed Reel links", instagram_raw),
        ("YouTube queries used", query_count["youtube"]),
        ("YouTube first pages fetched", youtube_provider.search_pages_fetched if youtube_provider else 0),
        ("Elapsed seconds", elapsed_seconds),
        ("Instagram queries used", query_count["instagram"]),
        ("Unique source IDs evaluated", stats["unique_evaluated"]),
        ("Repeated IDs in this run", stats["duplicate_search_results"]),
        ("Already known in SQLite", stats["already_known_source_ids"]),
        ("New eligible IDs (1M+)", stats["new_eligible"]),
        ("Known IDs newly eligible", stats["known_ids_became_eligible"]),
        ("Already eligible IDs", stats["already_eligible"]),
        ("Missing view metric", stats["missing_view_metric"]),
        ("Below view threshold", stats["below_threshold"]),
        ("Short format uncertain", stats["format_uncertain"]),
        ("Not a Short/Reel", stats["not_short"]),
        ("YT metadata enrichment attempted", yt_enrichment_attempts),
        ("YT metadata enrichment succeeded", yt_enrichment_successes),
        ("Instagram metadata lookups", ig_metadata_lookups),
        ("Instagram metadata failures", ig_metadata_failures),
        ("Instagram links not resolved (lookup cap)", ig_lookup_backlog),
        ("Provider / metadata errors", total_provider_errors),
    ]
    for label, value in metrics:
        table.add_row(label, str(value))
    console.print(table)

    platform_table = Table(title="Candidate status by platform (this run)")
    platform_table.add_column("Platform")
    platform_table.add_column("Eligible", justify="right")
    platform_table.add_column("Missing metric", justify="right")
    platform_table.add_column("Below threshold", justify="right")
    platform_table.add_column("Format uncertain", justify="right")
    for name in ("youtube", "instagram"):
        counts = status_by_platform[name]
        platform_table.add_row(
            name,
            str(counts.get("eligible", 0)),
            str(counts.get("metric_unknown", 0)),
            str(counts.get("below_threshold", 0)),
            str(counts.get("format_unknown", 0)),
        )
    console.print(platform_table)
    console.print(f"Database: {database.expanduser().resolve()}")
    console.print(f"Report: {report.expanduser().resolve()}")
    console.print(f"Runtime: {elapsed_seconds:.1f}s / {max_runtime_seconds}s · Stop reason: {stop_reason}")
    if enrichment_budget_exhausted:
        console.print("[yellow]Optional metadata enrichment stopped at its time budget; all discovered search results are still processed.[/yellow]")
    if platform == "youtube":
        console.print("[dim]Instagram was not selected in this run (--platform youtube).[/dim]")
    elif platform == "instagram":
        console.print("[dim]YouTube was not selected in this run (--platform instagram).[/dim]")
    if instagram_provider and instagram_provider.circuit_open:
        console.print(
            f"[yellow]Instagram circuit breaker opened: {instagram_provider.circuit_reason}[/yellow]"
        )
    if errors:
        console.print(f"[yellow]Provider errors collected: {len(errors)} (first five shown below)[/yellow]")
        for error in errors[:5]:
            console.print(f"[yellow]- {error}[/yellow]")
    if stats["new_eligible"] < target_new:
        console.print(
            f"[yellow]Partial yield: {stats['new_eligible']} new eligible of {target_new} requested. "
            "Check the provider error/circuit diagnostics and metric coverage. The target is not guaranteed.[/yellow]"
        )


def _load_rights_manifest(path: Path) -> dict[tuple[str, str], AcquisitionAuthorization]:
    rights: dict[tuple[str, str], AcquisitionAuthorization] = {}
    with path.expanduser().resolve(strict=True).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            try:
                item = AcquisitionAuthorization.model_validate_json(text)
            except Exception as exc:
                raise ValueError(f"Invalid rights row {line_number}: {exc}") from exc
            key = (item.platform, item.source_id)
            if key in rights:
                raise ValueError(f"Duplicate rights entry at row {line_number}: {key}")
            rights[key] = item
    return rights


@discovery_app.command("download")
def download_eligible(
    rights_manifest: Path = typer.Option(..., "--rights-manifest", exists=True, readable=True),
    limit: int = typer.Option(25, "--limit", min=1, max=500),
    database: Path = typer.Option(Path(".shortslm/discovery.sqlite3"), "--database"),
    output_dir: Path = typer.Option(Path("data/private/acquired"), "--output-dir"),
    instagram_session_user: str | None = typer.Option(None, "--instagram-session-user"),
    instagram_session_file: Path | None = typer.Option(None, "--instagram-session-file"),
) -> None:
    """Download queued candidates only when the private rights manifest grants training."""
    try:
        permissions = _load_rights_manifest(rights_manifest)
    except Exception as exc:
        console.print(f"[bold red]Cannot read rights manifest:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    success = failed = blocked = duplicate_media = 0
    errors: list[str] = []
    with DiscoveryStore(database) as store:
        queued = store.eligible_candidates(limit=limit)
        for candidate in queued:
            authorization = permissions.get((candidate.platform, candidate.source_id))
            if authorization is None:
                blocked += 1
                continue
            try:
                media_path = download_candidate(
                    candidate,
                    authorization,
                    output_dir,
                    instagram_session_username=instagram_session_user,
                    instagram_session_file=str(instagram_session_file) if instagram_session_file else None,
                )
                media_hash = sha256_file(media_path)
                duplicate = store.find_media_hash(media_hash)
                if duplicate:
                    media_path.unlink(missing_ok=True)
                    media_path.with_suffix(".metadata.json").unlink(missing_ok=True)
                    duplicate_of = f"{duplicate['platform']}:{duplicate['source_id']}"
                    store.mark_duplicate_media(
                        candidate.platform,
                        candidate.source_id,
                        duplicate_of=duplicate_of,
                        media_sha256=media_hash,
                    )
                    duplicate_media += 1
                    continue
                store.mark_download(
                    candidate.platform,
                    candidate.source_id,
                    path=str(media_path),
                    media_sha256=media_hash,
                )
                success += 1
            except Exception as exc:
                store.mark_download_failure(
                    candidate.platform,
                    candidate.source_id,
                    error=str(exc)[:500],
                )
                failed += 1
                errors.append(
                    f"{candidate.platform}:{candidate.source_id}: {str(exc)[:250]}"
                )

    table = Table(title="ShortsLM authorized download run")
    table.add_column("Result")
    table.add_column("Count", justify="right")
    for label, count in [
        ("Downloaded MP4", success),
        ("Failed", failed),
        ("Blocked (no matching permission)", blocked),
        ("Duplicate media files (same SHA-256)", duplicate_media),
    ]:
        table.add_row(label, str(count))
    console.print(table)
    for error in errors[:20]:
        console.print(f"[red]{error}[/red]")
    console.print(f"Output: {output_dir.expanduser().resolve()}")
    if blocked:
        console.print(
            "[yellow]Blocked items remain queued. Add a matching private rights-manifest row "
            "only after the required rights have actually been obtained.[/yellow]"
        )


@discovery_app.command("graph-run")
def graph_run(
    platform: Literal["youtube", "instagram", "all"] = typer.Option("youtube", "--platform"),
    target_new: int = typer.Option(100, "--target-new", min=1, max=2000),
    min_metric: int = typer.Option(1_000_000, "--min-metric", min=0),
    max_runtime_seconds: int = typer.Option(600, "--max-runtime-seconds", min=30, max=900),
    max_seed_queries: int = typer.Option(8, "--max-seed-queries", min=0, max=20),
    max_hashtag_queries: int = typer.Option(4, "--max-hashtag-queries", min=0, max=20),
    max_creators: int = typer.Option(80, "--max-creators", min=0, max=500),
    max_expansions: int = typer.Option(80, "--max-expansions", min=0, max=1000),
    max_depth: int = typer.Option(3, "--max-depth", min=0, max=10),
    instagram_creator: list[str] = typer.Option([], "--instagram-creator"),
    instagram_seeds_file: Path = typer.Option(
        Path("data/instagram_creator_seeds.txt"), "--instagram-seeds-file"
    ),
    instagram_hashtag: list[str] = typer.Option(
        [], "--instagram-hashtag", help="Repeatable hashtag seed, with or without #."
    ),
    instagram_hashtags_file: Path = typer.Option(
        Path("data/instagram_hashtags.txt"), "--instagram-hashtags-file"
    ),
    instagram_max_hashtags: int = typer.Option(8, "--instagram-max-hashtags", min=0, max=100),
    instagram_max_scrolls: int = typer.Option(8, "--instagram-max-scrolls", min=0, max=20),
    instagram_max_reel_details: int = typer.Option(
        3, "--instagram-max-reel-details", min=0, max=30,
        help="Maximum unknown-metric Reel detail pages to inspect per creator."
    ),
    instagram_hashtag_max_reel_details: int = typer.Option(
        8, "--instagram-hashtag-max-reel-details", min=0, max=30,
        help="Maximum unknown-metric Reel detail pages to inspect per hashtag."
    ),
    force: bool = typer.Option(
        False, "--force",
        help="Requeue supplied Instagram seed handles even if previously completed, empty, failed, exhausted, or blocked."
    ),
    continue_graph_after_target: bool = typer.Option(
        False, "--continue-graph-after-target",
        help="Continue bounded creator/related-video expansion after the new-eligible target is reached."
    ),
    instagram_profile_dir: Path = typer.Option(
        Path(".shortslm/browser/instagram"), "--instagram-profile-dir"
    ),
    database: Path = typer.Option(Path(".shortslm/discovery.sqlite3"), "--database"),
    report: Path = typer.Option(Path("outputs/discovery/graph-latest.json"), "--report"),
) -> None:
    """Run bounded creator + hashtag discovery; does not download media."""
    from shorts_intelligence.discovery.engine import run_creator_graph

    try:
        instagram_enabled = platform in {"instagram", "all"}
        creator_seeds = (
            load_instagram_creator_seeds(
                instagram_seeds_file, explicit_handles=instagram_creator
            ) if instagram_enabled else []
        )
        hashtag_seeds = (
            load_instagram_hashtags(
                instagram_hashtags_file, explicit_hashtags=instagram_hashtag
            ) if instagram_enabled else []
        )
        if instagram_enabled and not creator_seeds and not hashtag_seeds:
            raise ValueError(
                "No Instagram creator or hashtag seeds found. Supply --instagram-creator, "
                "--instagram-hashtag, or populate the configured seed files."
            )
        with DiscoveryStore(database) as store:
            summary = asyncio.run(run_creator_graph(
                store,
                platform=platform,
                target_new=target_new,
                min_metric=min_metric,
                max_runtime_seconds=max_runtime_seconds,
                max_seed_queries=max_seed_queries,
                max_hashtag_queries=max_hashtag_queries,
                max_creators=max_creators,
                max_expansions=max_expansions,
                max_depth=max_depth,
                instagram_profile_dir=instagram_profile_dir if instagram_enabled else None,
                instagram_creators=creator_seeds,
                instagram_hashtags=hashtag_seeds,
                force=force,
                instagram_max_scrolls=instagram_max_scrolls,
                instagram_max_reel_details=instagram_max_reel_details,
                instagram_hashtag_max_reel_details=instagram_hashtag_max_reel_details,
                max_instagram_hashtags=instagram_max_hashtags,
                continue_graph_after_target=continue_graph_after_target,
            ))
        _write_report(report, summary)
    except Exception as exc:
        console.print(f"[bold red]Graph discovery failed:[/bold red] {type(exc).__name__}: {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="Creator + hashtag discovery")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key in (
        "eligible_new", "candidates_observed", "new_inventory_candidates",
        "metric_observed_candidates", "metric_unknown_candidates",
        "metric_above_threshold_candidates", "youtube_creator_candidates",
        "youtube_related_candidates", "instagram_hashtag_requests",
        "hashtags_with_candidates", "creators_with_candidates", "creators_empty",
        "creators_completed", "creators_pending", "creators_exhausted",
        "creators_blocked", "creators_failed", "creator_edges", "elapsed_seconds",
    ):
        table.add_row(key.replace("_", " ").title(), str(summary.get(key, 0)))
    console.print(table)

    discovery_stages = summary.get("discovery_stage_counts", {})
    if discovery_stages:
        console.print(
            "Discovery stages: "
            f"YouTube seed details {discovery_stages.get('youtube_seed_detail_candidates', 0)}, "
            f"creator Shorts {discovery_stages.get('youtube_creator_candidates', 0)}, "
            f"related Shorts {discovery_stages.get('youtube_related_candidates', 0)}, "
            f"Instagram hashtag Reels {discovery_stages.get('instagram_hashtag_candidates', 0)}, "
            f"Instagram creator Reels {discovery_stages.get('instagram_creator_candidates', 0)}."
        )
        if summary.get("new_eligible", 0) >= summary.get("target_new", 0) and summary.get("target_new", 0) > 0 and not summary.get("continue_graph_after_target"):
            console.print(
                "[yellow]The new-eligible target was reached during seed discovery; "
                "creator/related-video expansion was skipped. Use --continue-graph-after-target "
                "to continue bounded graph exploration in the same run.[/yellow]"
            )

    instagram_requests = summary.get("provider_requests", {}).get("instagram", {})
    if instagram_requests:
        console.print(
            "Instagram capture: "
            f"{instagram_requests.get('json_responses_observed', 0)} JSON responses, "
            f"{instagram_requests.get('responses_parsed', 0)} with Reel records, "
            f"{instagram_requests.get('responses_unparsed', 0)} without recognized Reel records."
        )
        hashtag_diags = instagram_requests.get("hashtag_diagnostics", [])
        creator_diags = instagram_requests.get("creator_diagnostics", [])
        all_diags = [*hashtag_diags, *creator_diags]
        console.print(
            "Instagram surfaces: "
            f"{len(hashtag_diags)} hashtag pages, {len(creator_diags)} creator pages; "
            f"{sum(int(d.get('candidate_count', 0)) for d in all_diags)} Reel links; "
            f"{sum(int(d.get('metric_count', 0)) for d in all_diags)} with numeric metrics; "
            f"{sum(int(d.get('detail_pages_with_metrics', 0)) for d in all_diags)} detail pages enriched."
        )
        for item in summary.get("hashtag_results", []):
            if item.get("candidates_observed", 0) == 0:
                provider = item.get("provider", {})
                console.print(
                    f"[yellow]#{item.get('hashtag')}: "
                    f"{provider.get('reason') or item.get('error') or 'No Reel candidates captured'}[/yellow]"
                )
        for item in summary.get("creator_results", []):
            if item.get("candidates_observed", 0) == 0:
                provider = item.get("provider", {})
                console.print(
                    f"[yellow]@{item.get('handle')}: "
                    f"{provider.get('reason') or item.get('error') or 'No Reel candidates captured'}[/yellow]"
                )

        for label, diagnostics in (
            ("hashtag", hashtag_diags),
            ("creator", creator_diags),
        ):
            for diagnostic in diagnostics:
                shapes = diagnostic.get("response_shapes", [])
                for shape in shapes[:2]:
                    keys = shape.get("top_level_keys", [])
                    media = shape.get("media_like_objects", [])
                    media_keys = [
                        "/".join(item.get("signals", []))
                        for item in media[:2]
                    ]
                    console.print(
                        f"[dim]Instagram {label} response shape "
                        f"{diagnostic.get('hashtag') or diagnostic.get('handle')}: "
                        f"path={shape.get('path')}; top-level={keys}; media-signals={media_keys}[/dim]"
                    )
    console.print(f"Creator seed file: {instagram_seeds_file.expanduser().resolve()}")
    console.print(f"Hashtag seed file: {instagram_hashtags_file.expanduser().resolve()}")
    console.print(f"Report: {report.expanduser().resolve()}")
    console.print("[yellow]Instagram plays and YouTube views remain separate platform metrics.[/yellow]")


@discovery_app.command("instagram-browser-login")
def instagram_browser_login(
    profile_dir: Path = typer.Option(
        Path(".shortslm/browser/instagram"), "--profile-dir"
    ),
    chrome_path: Path | None = typer.Option(
        None, "--chrome-path", help="Optional path to chrome.exe / Google Chrome binary."
    ),
) -> None:
    """Open a normal system Google Chrome window for fully manual Instagram sign-in.

    The login window is intentionally NOT controlled by Playwright. This lets the
    user complete any platform verification in an ordinary browser session.
    """
    try:
        executable = find_chrome_executable(chrome_path)
        resolved_profile = profile_dir.expanduser().resolve()
        resolved_profile.mkdir(parents=True, exist_ok=True)
        command = [
            str(executable),
            f"--user-data-dir={resolved_profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "https://www.instagram.com/",
        ]
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
        console.print("[green]Opened regular Google Chrome (not Playwright Chromium).[/green]")
        console.print("[yellow]Sign in and complete any CAPTCHA/verification manually. This tool does not solve or bypass verification.[/yellow]")
        console.print(f"Profile: {resolved_profile}")
        console.print("[bold]After sign-in, close every Chrome window using this profile before running graph discovery.[/bold]")
    except Exception as exc:
        console.print(f"[bold red]Instagram browser setup failed:[/bold red] {type(exc).__name__}: {exc}")
        raise typer.Exit(code=1) from exc