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
    provider_errors: list[str],
    errors: list[str],
    platform: str,
    provider_messages: list[str],
) -> None:
    if not provider_messages:
        return
    for message in provider_messages:
        provider_errors.append(platform)
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
    seed: int = typer.Option(42, "--seed"),
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
        help="DDGS region, for example in-en, in-hi or us-en.",
    ),
    instagram_backend: str = typer.Option(
        "auto",
        "--instagram-backend",
        help="DDGS search backend: auto or a supported backend name.",
    ),
    instagram_pages: int = typer.Option(
        2,
        "--instagram-pages",
        min=1,
        max=5,
        help="Number of indexed search pages to inspect per Instagram query.",
    ),
    instagram_use_play_count: bool = typer.Option(
        False,
        "--instagram-use-play-count",
        help="Explicitly allow Instagram play_count when view_count is absent.",
    ),
    pause_seconds: float = typer.Option(1.5, "--pause-seconds", min=0.0, max=60.0),
) -> None:
    """Search, normalize, filter and deduplicate candidates into local SQLite.

    YouTube search uses yt-dlp's flat playlist mode, preserving the metadata
    returned by the search page without opening every video. Instagram uses
    DDGS-indexed Reel URLs and Instaloader metadata. This command never
    downloads media.
    """
    run_id = uuid.uuid4().hex
    run_started_at = datetime.now(UTC)
    rng = random.Random(seed)
    errors: list[str] = []
    warnings: list[str] = []
    candidates: list[DiscoveredCandidate] = []
    provider_errors: list[str] = []
    raw_by_platform: Counter[str] = Counter()
    query_count: Counter[str] = Counter()

    if query:
        youtube_queries = list(query)
        instagram_queries = list(query)
    else:
        youtube_queries = list(_DEFAULT_YOUTUBE_QUERIES)
        instagram_queries = list(_DEFAULT_INSTAGRAM_QUERIES)
    rng.shuffle(youtube_queries)
    rng.shuffle(instagram_queries)

    active_platforms = ["youtube", "instagram"] if platform == "all" else [platform]
    per_platform_budget = (
        max_candidates if len(active_platforms) == 1 else max(1, max_candidates // 2)
    )

    try:
        if platform in {"all", "youtube"}:
            youtube = YouTubeSearchProvider()
            for phrase in youtube_queries:
                if raw_by_platform["youtube"] >= per_platform_budget:
                    break
                search_phrase = (
                    phrase if "short" in phrase.casefold() else f"YouTube Shorts {phrase}"
                )
                remaining = min(
                    results_per_query,
                    per_platform_budget - raw_by_platform["youtube"],
                )
                results = list(youtube.search(search_phrase, limit=remaining))
                candidates.extend(results)
                raw_by_platform["youtube"] += len(results)
                query_count["youtube"] += 1
                _add_provider_errors(
                    provider_errors, errors, "youtube", youtube.errors
                )
                warnings.extend(youtube.warnings[:20])
                youtube.warnings.clear()

        if platform in {"all", "instagram"}:
            instagram = InstagramSearchProvider(
                session_username=instagram_session_user,
                session_file=str(instagram_session_file) if instagram_session_file else None,
                request_pause_seconds=pause_seconds,
                region=instagram_region,
                backend=instagram_backend,
                pages=instagram_pages,
            )
            for phrase in instagram_queries:
                if raw_by_platform["instagram"] >= per_platform_budget:
                    break
                remaining = min(
                    results_per_query,
                    per_platform_budget - raw_by_platform["instagram"],
                )
                results = list(instagram.search(phrase, limit=remaining))
                candidates.extend(results)
                raw_by_platform["instagram"] += len(results)
                query_count["instagram"] += 1
                _add_provider_errors(
                    provider_errors, errors, "instagram", instagram.errors
                )

            for tag in instagram_hashtag:
                if raw_by_platform["instagram"] >= per_platform_budget:
                    break
                results = list(
                    instagram.search_hashtag(
                        tag,
                        limit=min(
                            results_per_query,
                            per_platform_budget - raw_by_platform["instagram"],
                        ),
                    )
                )
                candidates.extend(results)
                raw_by_platform["instagram"] += len(results)
                _add_provider_errors(
                    provider_errors, errors, "instagram", instagram.errors
                )

    except ProviderUnavailable as exc:
        console.print(f"[bold red]Discovery dependency missing:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        errors.append(f"Unexpected discovery error: {str(exc)[:300]}")

    # Randomize the interleaving, but never claim search-engine results are a
    # statistically uniform sample.
    rng.shuffle(candidates)
    stats: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    status_by_platform: dict[str, Counter[str]] = {
        "youtube": Counter(),
        "instagram": Counter(),
    }
    encountered: set[tuple[str, str]] = set()

    with DiscoveryStore(database) as store:
        store.start_run(run_id, target_new, min_views)
        for candidate in candidates:
            identity = (candidate.platform, candidate.source_id)
            if identity in encountered:
                stats["duplicate_search_results"] += 1
                continue
            encountered.add(identity)

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
                if is_new or became_eligible:
                    stats["new_eligible"] += 1
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

        run_summary: dict[str, object] = {
            **dict(stats),
            "status_counts": dict(status_counts),
            "status_counts_by_platform": {
                name: dict(counts) for name, counts in status_by_platform.items()
            },
        }
        store.finish_run(run_id, run_summary)
        database_counts = store.summary()
        database_by_platform = store.summary_by_platform()

    youtube_raw = raw_by_platform["youtube"]
    instagram_raw = raw_by_platform["instagram"]
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
        "unique_candidates_evaluated": stats["unique_evaluated"],
        "duplicate_search_results": stats["duplicate_search_results"],
        "already_known_source_ids": stats["already_known_source_ids"],
        "new_eligible": stats["new_eligible"],
        "already_eligible": stats["already_eligible"],
        "missing_view_metric": stats["missing_view_metric"],
        "below_threshold": stats["below_threshold"],
        "format_uncertain": stats["format_uncertain"],
        "not_short": stats["not_short"],
        "storage_errors": stats["storage_errors"],
        "provider_errors": len(provider_errors) + len(errors),
        "provider_error_details": errors[:50],
        "yt_dlp_warnings": warnings[:30],
        "run_status_counts": dict(status_counts),
        "run_status_counts_by_platform": {
            name: dict(counts) for name, counts in status_by_platform.items()
        },
        "database_status_counts": database_counts,
        "database_status_counts_by_platform": database_by_platform,
        "database_path": str(database.expanduser()),
        "sampling_note": (
            "Search-engine results are indexed/ranked, not a uniform sample. "
            "The target is best-effort; only unique new qualifying records count."
        ),
        "media_downloaded": 0,
    }
    _write_report(report, payload)

    table = Table(title="ShortsLM discovery diagnostics")
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    metrics = [
        ("Raw YouTube search results", youtube_raw),
        ("Raw Instagram Reel results", instagram_raw),
        ("Unique candidates evaluated", stats["unique_evaluated"]),
        ("Repeated results in this run", stats["duplicate_search_results"]),
        ("Already in SQLite", stats["already_known_source_ids"]),
        ("New eligible candidates", stats["new_eligible"]),
        ("Already eligible candidates", stats["already_eligible"]),
        ("Missing view metric", stats["missing_view_metric"]),
        ("Below view threshold", stats["below_threshold"]),
        ("Format uncertain", stats["format_uncertain"]),
        ("Not a Short/Reel", stats["not_short"]),
        ("Provider / metadata errors", len(provider_errors) + len(errors)),
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
    if warnings:
        console.print(f"[dim]yt-dlp warnings collected quietly: {len(warnings)}[/dim]")
    if errors:
        console.print(f"[yellow]Provider error details: {len(errors)} (first five shown below)[/yellow]")
        for error in errors[:5]:
            console.print(f"[yellow]- {error}[/yellow]")
    if stats["new_eligible"] < target_new:
        console.print(
            f"[yellow]Partial yield: {stats['new_eligible']} new eligible of {target_new} requested. "
            "Use the status table to see whether the limiting factor is search coverage, "
            "missing metrics, threshold, or previously known IDs.[/yellow]"
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
