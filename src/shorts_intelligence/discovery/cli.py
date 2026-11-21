"""CLI commands for resilient non-API discovery and authorized acquisition."""

from __future__ import annotations

import json
import random
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import typer
from rich.console import Console
from rich.table import Table

from shorts_intelligence.discovery.downloader import download_candidate
from shorts_intelligence.discovery.models import AcquisitionAuthorization, DiscoveredCandidate
from shorts_intelligence.discovery.query_planner import (
    SearchQuery,
    build_instagram_query_pool,
    build_youtube_query_pool,
    select_due_queries,
)
from shorts_intelligence.discovery.providers import (
    InstagramSearchProvider,
    ProviderUnavailable,
    YouTubeSearchProvider,
)
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
    results_per_query: int = typer.Option(50, "--results-per-query", min=1, max=100),
    max_search_queries: int = typer.Option(
        24, "--max-search-queries", min=1, max=100,
        help="Maximum distinct YouTube searches in this run.",
    ),
    instagram_max_search_queries: int = typer.Option(
        8, "--instagram-max-search-queries", min=1, max=40,
        help="Maximum Instagram web searches in this run; each is time-bounded.",
    ),
    query_cooldown_days: int = typer.Option(
        7, "--query-cooldown-days", min=0, max=90,
        help="Do not reuse the same query/locale combination within this many days.",
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
        None,
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
    instagram_pages: int = typer.Option(
        1,
        "--instagram-pages",
        min=1,
        max=3,
        help="Number of public indexed result pages to inspect per query.",
    ),
    instagram_timeout: int = typer.Option(
        8, "--instagram-timeout", min=3, max=15,
        help="DDGS request timeout in seconds.",
    ),
    instagram_max_lookups: int = typer.Option(
        15, "--instagram-max-lookups", min=1, max=100,
        help="Maximum individual Instagram metadata lookups per run.",
    ),
    instagram_request_timeout: float = typer.Option(
        12.0, "--instagram-request-timeout", min=5.0, max=30.0,
        help="Instaloader per-request timeout in seconds (not its 300-second default).",
    ),
    instagram_use_play_count: bool = typer.Option(
        False,
        "--instagram-use-play-count",
        help="Explicitly allow Instagram play_count when view_count is absent.",
    ),
    pause_seconds: float = typer.Option(2.5, "--pause-seconds", min=1.0, max=60.0),
) -> None:
    """Discover new Shorts/Reels with rotating queries, local dedup and bounded metadata lookup.

    YouTube uses the dedicated Shorts result filter in ytscrape. Query/locale
    history is persisted in SQLite, so repeated runs rotate into unused topics,
    languages and regions before revisiting recently used searches. Instagram
    web search and metadata lookups have explicit timeouts and a circuit breaker.
    This command discovers metadata only; it does not download media.
    """
    run_id = uuid.uuid4().hex
    run_started_at = datetime.now(UTC)
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
    instagram_provider: InstagramSearchProvider | None = None

    youtube_pool = build_youtube_query_pool(query)
    instagram_pool = build_instagram_query_pool(query, default_region=instagram_region)
    stats: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    status_by_platform: dict[str, Counter[str]] = {
        "youtube": Counter(),
        "instagram": Counter(),
    }
    unique_candidates: dict[tuple[str, str], DiscoveredCandidate] = {}

    with DiscoveryStore(database) as store:
        youtube_queries: list[SearchQuery] = []
        instagram_queries: list[SearchQuery] = []
        if platform in {"all", "youtube"}:
            youtube_queries = select_due_queries(
                youtube_pool,
                store.query_history("youtube"),
                limit=max_search_queries,
                cooldown_days=query_cooldown_days,
                rng=rng,
                now=run_started_at,
            )
        if platform in {"all", "instagram"}:
            instagram_limit = instagram_max_search_queries
            instagram_queries = select_due_queries(
                instagram_pool,
                store.query_history("instagram"),
                limit=instagram_limit,
                cooldown_days=query_cooldown_days,
                rng=rng,
                now=run_started_at,
            )

        store.start_run(run_id, target_new, min_views, started_at=run_started_at)

        try:
            if platform in {"all", "youtube"}:
                youtube_provider = YouTubeSearchProvider(
                    detail_enrichment_limit=metadata_enrichment_limit
                )
                for search_query in youtube_queries:
                    if youtube_provider.circuit_open:
                        break
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
                    if youtube_provider.circuit_open:
                        break

            if platform in {"all", "instagram"}:
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
                )
                for search_query in instagram_queries:
                    if instagram_provider.circuit_open:
                        break
                    instagram_provider.region = search_query.region
                    before = instagram_provider.search_results_seen
                    query_candidates = list(
                        instagram_provider.search(
                            search_query.query,
                            limit=min(results_per_query, 30),
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
                    if instagram_provider.circuit_open:
                        break
                    before = instagram_provider.search_results_seen
                    query_candidates = list(
                        instagram_provider.search_hashtag(
                            tag,
                            limit=min(results_per_query, instagram_max_lookups),
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
            previous_metric = previous.qualifying_metric(
                accept_instagram_play_count=instagram_use_play_count
            )
            candidate_metric = candidate.qualifying_metric(
                accept_instagram_play_count=instagram_use_play_count
            )
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
        if youtube_provider and metadata_enrichment_limit > 0:
            enriched: list[DiscoveredCandidate] = []
            remaining = metadata_enrichment_limit
            for candidate in ordered:
                if remaining <= 0:
                    enriched.append(candidate)
                    continue
                if (
                    candidate.platform == "youtube"
                    and (candidate.view_count is None or candidate.duration_seconds is None)
                    and not store.has_candidate(candidate.platform, candidate.source_id)
                ):
                    language = str(candidate.metadata.get("search_language") or "en")
                    region = str(candidate.metadata.get("search_region") or "IN")
                    before = youtube_provider.enrichment_attempts
                    candidate = youtube_provider.enrich(
                        candidate, language=language, region=region
                    )
                    remaining -= youtube_provider.enrichment_attempts - before
                enriched.append(candidate)
                if youtube_provider.circuit_open:
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
                accept_instagram_play_count=instagram_use_play_count,
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
        if instagram_provider:
            for message in instagram_provider.errors:
                errors.append(f"instagram: {message[:300]}")
            provider_errors["instagram"] += len(instagram_provider.errors)
            if instagram_provider.circuit_reason:
                errors.append(f"instagram circuit opened: {instagram_provider.circuit_reason}")
            instagram_provider.close()

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
    ig_ddgs_failures = instagram_provider.ddgs_failures if instagram_provider else 0

    payload: dict[str, object] = {
        "run_id": run_id,
        "started_at": run_started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "platform": platform,
        "target_new": target_new,
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
        },
        "instagram_metadata": {
            "lookups": ig_metadata_lookups,
            "succeeded": ig_metadata_successes,
            "failed": ig_metadata_failures,
            "ddgs_failures": ig_ddgs_failures,
            "circuit_open": instagram_provider.circuit_open if instagram_provider else False,
            "circuit_reason": instagram_provider.circuit_reason if instagram_provider else None,
            "lookup_limit": instagram_max_lookups,
            "request_timeout_seconds": instagram_request_timeout,
            "ddgs_timeout_seconds": instagram_timeout,
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
            "YouTube uses ytscrape's Shorts-only filter and rotating query/locale strata. "
            "Instagram results are indexed by public web search. Both remain best-effort, "
            "non-uniform samples; only new unique IDs passing the observed view threshold count."
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
