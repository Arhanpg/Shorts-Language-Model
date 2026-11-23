"""Metadata-only URL collection for YouTube Shorts and Instagram Reels.

This workflow never downloads video/audio media. It uses the existing bounded
creator-graph providers, persists discovery state in SQLite, and exports
confirmed short-form canonical URLs into separate, Git-trackable text files.
"""
from __future__ import annotations

import asyncio
import csv
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from shorts_intelligence.discovery.engine import run_creator_graph
from shorts_intelligence.discovery.storage import DiscoveryStore
from shorts_intelligence.phase4 import catalogue

url_collection_app = typer.Typer(
    name="urls",
    help="Discover metadata and export Shorts/Reels URLs only; never download media.",
    no_args_is_help=True,
)
console = Console()
_CHANNEL_ID = re.compile(r"^UC[A-Za-z0-9_-]{22}$")


def _read_csv_values(path: Path, field: str) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {key: str(value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
            if str(row.get(field) or "").strip()
        ]


def _chunks(values: list[str], size: int):
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def _balanced_hashtags(path: Path) -> list[str]:
    buckets: dict[tuple[str, str], list[str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            tag = str(row.get("hashtag") or "").strip().lstrip("#").casefold()
            if not tag:
                continue
            key = (
                str(row.get("language") or "unspecified").strip().casefold(),
                str(row.get("domain") or "unspecified").strip().casefold(),
            )
            bucket = buckets.setdefault(key, [])
            if tag not in bucket:
                bucket.append(tag)
    ordered: list[str] = []
    keys = sorted(buckets)
    while keys:
        remaining = []
        for key in keys:
            ordered.append(buckets[key].pop(0))
            if buckets[key]:
                remaining.append(key)
        keys = remaining
    return ordered


def _youtube_source_url(reference: str) -> str:
    """Build the creator Shorts-tab URL; no channel-ID lookup is needed."""
    value = reference.strip()
    if value.startswith(("https://www.youtube.com/", "https://youtube.com/")):
        base = value.rstrip("/")
        return base if base.endswith("/shorts") else f"{base}/shorts"
    if _CHANNEL_ID.fullmatch(value):
        return f"https://www.youtube.com/channel/{value}/shorts"
    handle = value.lstrip("@")
    if not handle or any(char.isspace() for char in handle):
        raise ValueError(f"Invalid YouTube creator reference: {reference!r}")
    return f"https://www.youtube.com/@{handle}/shorts"


def _youtube_video_urls(info: Any, *, source: str) -> list[str]:
    """Extract video IDs from flat yt-dlp metadata without requesting media."""
    if not isinstance(info, dict):
        return []
    entries = info.get("entries")
    if entries is None:
        entries = [info]
    urls: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        video_id = str(entry.get("id") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            webpage_url = str(entry.get("webpage_url") or entry.get("url") or "")
            match = re.search(r"(?:youtu\\.be/|youtube\\.com/(?:shorts/|watch\\?v=))([A-Za-z0-9_-]{11})", webpage_url)
            if match:
                video_id = match.group(1)
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            continue
        # Creator Shorts tabs are already format-specific. Search results are
        # treated as potential Shorts when duration is unknown or <= 180 sec.
        duration = entry.get("duration")
        if source == "hashtag" and duration is not None:
            try:
                if float(duration) > 180:
                    continue
            except (TypeError, ValueError):
                pass
        urls.add(f"https://www.youtube.com/shorts/{video_id}")
    return sorted(urls)


def _collect_youtube_urls(
    *,
    creators: list[str],
    hashtags: list[str],
    destination: Path,
    creator_batch_size: int,
    hashtag_batch_size: int,
    per_surface_limit: int = 30,
) -> dict[str, int]:
    """Collect YouTube Shorts URLs through yt-dlp flat metadata extraction only."""
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError('Install yt-dlp with: pip install -e ".[discovery]"') from exc

    class QuietLogger:
        def debug(self, message: str) -> None:
            return None

        def warning(self, message: str) -> None:
            return None

        def error(self, message: str) -> None:
            return None

    options = {
        "quiet": True,
        "no_warnings": True,
        "logger": QuietLogger(),
        "skip_download": True,
        "extract_flat": "in_playlist",
        "playlistend": per_surface_limit,
        "socket_timeout": 15,
        "retries": 0,
        "extractor_retries": 0,
        "ignoreerrors": True,
        "noplaylist": False,
    }
    existing = set()
    if destination.exists():
        existing = {
            line.strip()
            for line in destination.read_text(encoding="utf-8-sig").splitlines()
            if line.strip().startswith("https://www.youtube.com/shorts/")
        }
    counts = Counter()
    destination.parent.mkdir(parents=True, exist_ok=True)

    def save_checkpoint() -> None:
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text("".join(f"{url}\\n" for url in sorted(existing)), encoding="utf-8")
        temporary.replace(destination)

    with YoutubeDL(options) as client:
        creator_batches = list(_chunks(creators, creator_batch_size))
        for batch_number, batch in enumerate(creator_batches, 1):
            for reference in batch:
                try:
                    url = _youtube_source_url(reference)
                    info = client.extract_info(url, download=False)
                    found = _youtube_video_urls(info, source="creator")
                    existing.update(found)
                    counts["creator_surfaces_processed"] += 1
                    counts["creator_urls_found"] += len(found)
                    if not found:
                        counts["creator_surfaces_without_results"] += 1
                except Exception as exc:
                    counts["creator_errors"] += 1
                    counts["creator_404_or_unavailable"] += int("404" in str(exc))
            save_checkpoint()
            console.print(
                f"[cyan]YouTube creator batch {batch_number}/{len(creator_batches)}[/cyan] "
                f"| URLs={len(existing)} | processed={counts['creator_surfaces_processed']} "
                f"| errors={counts['creator_errors']}"
            )

        hashtag_batches = list(_chunks(hashtags, hashtag_batch_size))
        for batch_number, batch in enumerate(hashtag_batches, 1):
            for tag in batch:
                try:
                    query = f"ytsearch{per_surface_limit}:#{tag} #shorts"
                    info = client.extract_info(query, download=False)
                    found = _youtube_video_urls(info, source="hashtag")
                    existing.update(found)
                    counts["hashtag_surfaces_processed"] += 1
                    counts["hashtag_urls_found"] += len(found)
                    if not found:
                        counts["hashtag_surfaces_without_results"] += 1
                except Exception as exc:
                    counts["hashtag_errors"] += 1
                    counts["hashtag_404_or_unavailable"] += int("404" in str(exc))
            save_checkpoint()
            console.print(
                f"[cyan]YouTube hashtag batch {batch_number}/{len(hashtag_batches)}[/cyan] "
                f"| URLs={len(existing)} | processed={counts['hashtag_surfaces_processed']} "
                f"| errors={counts['hashtag_errors']}"
            )

    save_checkpoint()
    counts["unique_urls"] = len(existing)
    return dict(counts)

def _load_resolution_cache(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            row["reference"]: row["channel_id"]
            for row in csv.DictReader(handle)
            if row.get("reference") and row.get("channel_id")
            and _CHANNEL_ID.fullmatch(row["channel_id"])
        }


def _save_resolution_cache(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["reference", "channel_id"])
        writer.writeheader()
        for reference, channel_id in sorted(values.items()):
            writer.writerow({"reference": reference, "channel_id": channel_id})
    temporary.replace(path)


def _export_urls(database: Path, platform: str, destination: Path) -> int:
    with DiscoveryStore(database) as store:
        rows = store.connection.execute(
            """SELECT canonical_url FROM candidates
               WHERE platform=? AND short_format_status='confirmed'
               ORDER BY discovered_at, source_id""",
            (platform,),
        ).fetchall()
    existing = set()
    if destination.exists():
        existing = {
            line.strip()
            for line in destination.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        }
    urls = {
        str(row["canonical_url"]).strip()
        for row in rows
        if row["canonical_url"] and str(row["canonical_url"]).strip().startswith("https://")
    }
    merged = sorted(existing | urls)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text("".join(f"{url}\n" for url in merged), encoding="utf-8")
    temporary.replace(destination)
    return len(merged)


def _run_batch(
    *,
    platform: str,
    creators: list[str],
    hashtags: list[str],
    database: Path,
    profile_dir: Path,
    runtime_seconds: int,
    report_path: Path,
) -> dict[str, Any]:
    with DiscoveryStore(database) as store:
        summary = asyncio.run(run_creator_graph(
            store,
            platform=platform,
            target_new=2000,
            min_metric=0,
            max_runtime_seconds=runtime_seconds,
            max_seed_queries=0,
            max_hashtag_queries=min(20, len(hashtags)) if platform == "youtube" else 0,
            max_creators=min(500, len(creators)),
            max_expansions=0,
            max_depth=0,
            instagram_profile_dir=profile_dir if platform == "instagram" else None,
            instagram_creators=creators if platform == "instagram" else None,
            instagram_hashtags=hashtags if platform == "instagram" else None,
            youtube_creators=creators if platform == "youtube" else None,
            youtube_hashtags=hashtags if platform == "youtube" else None,
            instagram_max_scrolls=8,
            instagram_max_reel_details=0,
            instagram_hashtag_max_reel_details=0,
            max_instagram_hashtags=min(100, len(hashtags)) if platform == "instagram" else 0,
            continue_graph_after_target=True,
        ))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    return summary


@url_collection_app.command("collect")
def collect_urls(
    catalogue_dir: Path = typer.Option(
        Path("data/seed_catalogue/v0.2"), "--catalogue-dir",
        exists=True, file_okay=False,
    ),
    database: Path = typer.Option(Path(".shortslm/url-discovery.sqlite3"), "--database"),
    output_dir: Path = typer.Option(Path("data/discovered_urls"), "--output-dir"),
    report_dir: Path = typer.Option(Path("outputs/url-collection"), "--report-dir"),
    instagram_profile_dir: Path = typer.Option(
        Path(".shortslm/browser/instagram"), "--instagram-profile-dir",
    ),
    creator_batch_size: int = typer.Option(100, "--creator-batch-size", min=1, max=500),
    instagram_hashtag_batch_size: int = typer.Option(50, "--instagram-hashtag-batch-size", min=1, max=100),
    youtube_hashtag_batch_size: int = typer.Option(20, "--youtube-hashtag-batch-size", min=1, max=100),
    runtime_seconds: int = typer.Option(900, "--runtime-seconds", min=30, max=900),
    platforms: str = typer.Option("all", "--platforms", help="all, instagram, or youtube."),
) -> None:
    """Discover metadata only and export deduplicated Instagram Reel/YouTube Shorts URLs."""
    selected = {part.strip().casefold() for part in platforms.split(",") if part.strip()}
    if selected == {"all"}:
        selected = {"instagram", "youtube"}
    if not selected or not selected.issubset({"instagram", "youtube"}):
        raise typer.BadParameter("--platforms must be all, instagram, youtube, or a comma-separated combination.")
    if "instagram" in selected and not instagram_profile_dir.exists():
        raise typer.BadParameter(
            f"Instagram browser profile not found: {instagram_profile_dir}. "
            "Run 'shorts-lm discover instagram-browser-login' and sign in manually first."
        )

    started = time.monotonic()
    catalogue_output = report_dir / "catalogue"
    catalogue(
        catalogue_dir=catalogue_dir,
        output_dir=catalogue_output,
        batch_size=creator_batch_size,
        hashtag_batch_size=instagram_hashtag_batch_size,
    )
    instagram_rows = _read_csv_values(catalogue_output / "instagram_creator_candidates.csv", "identity")
    youtube_rows = _read_csv_values(catalogue_output / "youtube_creator_candidates.csv", "identity")
    instagram_creators = [row["identity"] for row in instagram_rows]
    youtube_creators = [row["identity"] for row in youtube_rows]
    hashtags = _balanced_hashtags(catalogue_output / "hashtag_candidates.csv")

    output_dir.mkdir(parents=True, exist_ok=True)
    reports = report_dir / "runs"
    database.parent.mkdir(parents=True, exist_ok=True)
    totals: Counter[str] = Counter()
    ig_path = output_dir / "instagram_reels.txt"
    yt_path = output_dir / "youtube_shorts.txt"

    # YouTube collection is deliberately yt-dlp-only: no TubeScrape, no API
    # channel resolution, and no media download.
    if "youtube" in selected:
        console.print(
            f"[bold cyan]YouTube yt-dlp discovery[/bold cyan] | "
            f"creators={len(youtube_creators)} hashtags={len(hashtags)}"
        )
        try:
            totals.update(_collect_youtube_urls(
                creators=youtube_creators,
                hashtags=hashtags,
                destination=yt_path,
                creator_batch_size=creator_batch_size,
                hashtag_batch_size=youtube_hashtag_batch_size,
            ))
        except Exception as exc:
            totals["youtube_fatal_errors"] += 1
            console.print(f"[red]YouTube collection failed: {type(exc).__name__}: {exc}[/red]")

    # Instagram collection remains the user's chosen visible-browser workflow.
    if "instagram" in selected:
        jobs: list[tuple[list[str], list[str], str]] = []
        for index, chunk in enumerate(_chunks(instagram_creators, creator_batch_size), 1):
            jobs.append((chunk, [], f"instagram-creators-{index:04d}"))
        for index, chunk in enumerate(_chunks(hashtags, instagram_hashtag_batch_size), 1):
            jobs.append(([], chunk, f"instagram-hashtags-{index:04d}"))
        blocked = False
        for index, (creators, tags, label) in enumerate(jobs, 1):
            if blocked:
                break
            console.print(
                f"\\n[bold cyan]Instagram browser discovery {index}/{len(jobs)} · {label}[/bold cyan] "
                f"| creators={len(creators)} hashtags={len(tags)}"
            )
            try:
                summary = _run_batch(
                    platform="instagram",
                    creators=creators,
                    hashtags=tags,
                    database=database,
                    profile_dir=instagram_profile_dir,
                    runtime_seconds=runtime_seconds,
                    report_path=reports / f"{label}.json",
                )
            except Exception as exc:
                totals["instagram_failed_batches"] += 1
                console.print(f"[red]Instagram batch failed: {type(exc).__name__}: {exc}[/red]")
                blocked = True
                continue
            totals["instagram_batches_completed"] += 1
            totals["instagram_candidates_observed"] += int(summary.get("candidates_observed", 0))
            errors = summary.get("error_details", [])
            if any(
                any(token in str(error).casefold() for token in (
                    "captcha", "challenge", "rate limit", "429", "403", "forbidden",
                    "login required", "checkpoint", "temporarily blocked",
                ))
                for error in errors
            ):
                blocked = True
                console.print("[yellow]Instagram discovery stopped after an access restriction.[/yellow]")
            ig_count = _export_urls(database, "instagram", ig_path)
            console.print(f"[green]Instagram URL checkpoint saved[/green] | unique URLs={ig_count}")
        totals["instagram_unique_urls"] = _export_urls(database, "instagram", ig_path)

    ig_count = _export_urls(database, "instagram", ig_path) if "instagram" in selected else (
        sum(1 for line in ig_path.read_text(encoding="utf-8-sig").splitlines() if line.strip())
        if ig_path.exists() else 0
    )
    yt_count = sum(
        1 for line in yt_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()
    ) if yt_path.exists() else 0
    report = {
        "schema_version": "shortslm.url-collection.v2",
        "catalogue": {
            "instagram_creator_candidates": len(instagram_creators),
            "youtube_creator_candidates": len(youtube_creators),
            "hashtags": len(hashtags),
        },
        "youtube_provider": "yt-dlp flat metadata extraction",
        "instagram_provider": "Playwright visible browser session",
        "totals": dict(totals),
        "exported_urls": {"instagram_reels": ig_count, "youtube_shorts": yt_count},
        "files": {
            "instagram_reels": str(ig_path.resolve()),
            "youtube_shorts": str(yt_path.resolve()),
        },
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "media_downloaded": False,
        "feature_extraction_performed": False,
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "summary.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\\n", encoding="utf-8",
    )
    table = Table(title="ShortsLM URL collection")
    table.add_column("Output")
    table.add_column("Unique URLs", justify="right")
    table.add_row("Instagram Reels", str(ig_count))
    table.add_row("YouTube Shorts", str(yt_count))
    table.add_row("YouTube creator surfaces", str(totals.get("creator_surfaces_processed", 0)))
    table.add_row("YouTube hashtag surfaces", str(totals.get("hashtag_surfaces_processed", 0)))
    console.print(table)
    console.print("[green]Metadata-only run complete. No video or audio media was downloaded.[/green]")
    console.print(ig_path)
    console.print(yt_path)
