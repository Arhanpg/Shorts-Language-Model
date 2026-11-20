"""CLI commands for non-API public video discovery and authorized acquisition."""

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

_DEFAULT_QUERIES = [
    "viral short videos India",
    "trending shorts 2026",
    "viral reels India",
    "cricket comedy edits",
    "educational facts short video",
]


def _write_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    temporary.replace(path)


@discovery_app.command("run")
def run_discovery(
    platform: Literal["all", "youtube", "instagram"] = typer.Option("all", "--platform"),
    query: list[str] = typer.Option([], "--query", "-q", help="Search phrase. Repeat this option for more query coverage."),
    target_new: int = typer.Option(100, "--target-new", min=1, max=2000),
    min_views: int = typer.Option(1_000_000, "--min-views", min=0),
    max_candidates: int = typer.Option(1500, "--max-candidates", min=1, max=20000),
    results_per_query: int = typer.Option(50, "--results-per-query", min=1, max=100),
    seed: int = typer.Option(42, "--seed"),
    database: Path = typer.Option(Path(".shortslm/discovery.sqlite3"), "--database"),
    report: Path = typer.Option(Path("outputs/discovery/latest.json"), "--report"),
    instagram_session_user: str | None = typer.Option(
        None, "--instagram-session-user",
        help="Optional Instaloader username with an existing local session file. No password is accepted here.",
    ),
    instagram_session_file: Path | None = typer.Option(
        None, "--instagram-session-file",
        help="Optional local Instaloader session file path; never put it in Git.",
    ),
    instagram_hashtag: list[str] = typer.Option(
        [], "--instagram-hashtag",
        help="Optional hashtag target. Requires a valid local Instaloader session.",
    ),
    instagram_use_play_count: bool = typer.Option(
        False, "--instagram-use-play-count",
        help="Use Instagram video_play_count only when view_count is absent; stored as a distinct metric.",
    ),
    pause_seconds: float = typer.Option(1.5, "--pause-seconds", min=0.0, max=60.0),
) -> None:
    """Search, normalize, filter and deduplicate candidates into local SQLite.

    This command performs discovery only. It never downloads media. Platform API
    keys are not used; yt-dlp and DDGS search public web results, while Instaloader
    resolves public Reel metadata.
    """
    queries = list(query) if query else list(_DEFAULT_QUERIES)
    rng = random.Random(seed)
    rng.shuffle(queries)
    run_id = uuid.uuid4().hex
    stats: Counter[str] = Counter()
    encountered: set[tuple[str, str]] = set()
    errors: list[str] = []
    candidates: list[DiscoveredCandidate] = []

    youtube = YouTubeSearchProvider() if platform in {"all", "youtube"} else None
    instagram = (
        InstagramSearchProvider(
            session_username=instagram_session_user,
            session_file=str(instagram_session_file) if instagram_session_file else None,
            request_pause_seconds=pause_seconds,
        )
        if platform in {"all", "instagram"} else None
    )

    try:
        if youtube:
            for phrase in queries:
                if len(candidates) >= max_candidates:
                    break
                search_phrase = phrase if "short" in phrase.casefold() else f"shorts {phrase}"
                try:
                    results = list(youtube.search(search_phrase, limit=results_per_query))
                    candidates.extend(results)
                    stats["youtube_results"] += len(results)
                    stats["queries"] += 1
                except ProviderUnavailable:
                    raise
                except Exception as exc:
                    stats["errors"] += 1
                    errors.append(f"YouTube query '{phrase}': {str(exc)[:250]}")

        if instagram and len(candidates) < max_candidates:
            for phrase in queries:
                if len(candidates) >= max_candidates:
                    break
                try:
                    results = list(instagram.search(phrase, limit=results_per_query))
                    candidates.extend(results)
                    stats["instagram_results"] += len(results)
                    stats["queries"] += 1
                    stats["errors"] += len(instagram.errors)
                    errors.extend(instagram.errors[:100])
                    instagram.errors.clear()
                except ProviderUnavailable:
                    raise
                except Exception as exc:
                    stats["errors"] += 1
                    errors.append(f"Instagram query '{phrase}': {str(exc)[:250]}")

            for tag in instagram_hashtag:
                if len(candidates) >= max_candidates:
                    break
                try:
                    results = list(instagram.search_hashtag(tag, limit=results_per_query))
                    candidates.extend(results)
                    stats["instagram_hashtag_results"] += len(results)
                except Exception as exc:
                    stats["errors"] += 1
                    errors.append(f"Instagram hashtag '#{tag}': {str(exc)[:250]}")

    except ProviderUnavailable as exc:
        console.print(f"[bold red]Discovery dependency missing:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    # Shuffle provider outputs so the target isn't systematically filled by
    # the first platform/query only. Search engines are ranked; this is not a
    # statistically uniform sample of every platform post.
    rng.shuffle(candidates)
    with DiscoveryStore(database) as store:
        store.start_run(run_id, target_new, min_views)
        for candidate in candidates[:max_candidates]:
            stats["scanned"] += 1
            identity = (candidate.platform, candidate.source_id)
            if identity in encountered:
                stats["duplicates"] += 1
                continue
            encountered.add(identity)
            is_new, became_eligible = store.upsert_candidate(
                candidate,
                min_views=min_views,
                run_id=run_id,
                accept_instagram_play_count=instagram_use_play_count,
            )
            stored = store.get_candidate(candidate.platform, candidate.source_id)
            if not is_new:
                stats["duplicates"] += 1
            if stored and stored.status == "eligible" and (is_new or became_eligible):
                stats["new_eligible"] += 1
            if stats["new_eligible"] >= target_new:
                break
        store.finish_run(run_id, dict(stats))
        database_counts = store.summary()

    payload: dict[str, object] = {
        "run_id": run_id,
        "started_at": datetime.now(UTC).isoformat(),
        "platform": platform,
        "target_new": target_new,
        "min_views": min_views,
        "scanned": stats["scanned"],
        "new_eligible": stats["new_eligible"],
        "duplicates": stats["duplicates"],
        "errors": stats["errors"],
        "database_status_counts": database_counts,
        "error_details": errors[:50],
        "database_path": str(database.expanduser()),
        "sampling_note": "Search results are indexed/ranked. Query order is seeded and shuffled; the result is not a uniform random sample.",
        "media_downloaded": 0,
    }
    _write_report(report, payload)

    table = Table(title="ShortsLM public-web discovery")
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    for label, value in [
        ("Candidates scanned", stats["scanned"]),
        ("New unique 1M+ eligible", stats["new_eligible"]),
        ("Duplicate source IDs", stats["duplicates"]),
        ("Provider errors", stats["errors"]),
        ("Previously known / database eligible", database_counts.get("eligible", 0)),
        ("Media downloaded", 0),
    ]:
        table.add_row(label, str(value))
    console.print(table)
    console.print(f"Database: {database.expanduser().resolve()}")
    console.print(f"Report: {report.expanduser().resolve()}")
    console.print("[yellow]Unknown view counts are not treated as zero or as 1M+. "
                  "Instagram play counts are opt-in and kept distinct from view counts.[/yellow]")
    if stats["new_eligible"] < target_new:
        console.print(
            f"[yellow]Partial yield: found {stats['new_eligible']} of {target_new} requested. "
            "Search coverage, rate limits and unique qualifying results determine actual yield.[/yellow]"
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
                        candidate.platform, candidate.source_id,
                        duplicate_of=duplicate_of, media_sha256=media_hash,
                    )
                    duplicate_media += 1
                    continue
                store.mark_download(
                    candidate.platform, candidate.source_id,
                    path=str(media_path), media_sha256=media_hash,
                )
                success += 1
            except Exception as exc:
                store.mark_download_failure(candidate.platform, candidate.source_id, error=str(exc)[:500])
                failed += 1
                errors.append(f"{candidate.platform}:{candidate.source_id}: {str(exc)[:250]}")

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
        console.print("[yellow]Blocked items remain queued. Add a matching private rights-manifest row "
                      "only after the required rights have actually been obtained.[/yellow]")
