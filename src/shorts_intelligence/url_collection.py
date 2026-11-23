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


def _resolve_youtube_channel_id(reference: str) -> str | None:
    """Resolve a public YouTube @handle to a stable UC channel ID via yt-dlp metadata."""
    value = reference.strip()
    if _CHANNEL_ID.fullmatch(value):
        return value
    handle = value.lstrip("@")
    if not handle:
        return None
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError('Install YouTube discovery dependencies: pip install -e ".[discovery]"') from exc
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "playlistend": 1,
        "socket_timeout": 12,
        "retries": 0,
        "extractor_retries": 0,
        "ignoreerrors": True,
    }
    with YoutubeDL(options) as client:
        info = client.extract_info(f"https://www.youtube.com/@{handle}", download=False)
    if not isinstance(info, dict):
        return None
    candidates = [info.get("channel_id"), info.get("id")]
    for entry in info.get("entries") or []:
        if isinstance(entry, dict):
            candidates.extend((entry.get("channel_id"), entry.get("channel")))
    return next(
        (str(item) for item in candidates if isinstance(item, str) and _CHANNEL_ID.fullmatch(item)),
        None,
    )


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
    youtube_hashtag_batch_size: int = typer.Option(20, "--youtube-hashtag-batch-size", min=1, max=20),
    runtime_seconds: int = typer.Option(900, "--runtime-seconds", min=30, max=900),
    resolve_delay_seconds: float = typer.Option(0.25, "--resolve-delay-seconds", min=0.0, max=10.0),
    platforms: str = typer.Option("all", "--platforms", help="all, instagram, or youtube."),
) -> None:
    """Discover metadata only and export separate deduplicated Reel/Short URL lists."""
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
    youtube_references = [row["identity"] for row in youtube_rows]
    hashtags = _balanced_hashtags(catalogue_output / "hashtag_candidates.csv")

    totals: Counter[str] = Counter()
    reports = report_dir / "runs"
    database.parent.mkdir(parents=True, exist_ok=True)

    if "youtube" in selected:
        cache_path = Path(".shortslm/youtube_channel_resolution.csv")
        resolved = _load_resolution_cache(cache_path)
        unresolved = [value for value in youtube_references if value not in resolved]
        console.print(
            f"[bold cyan]YouTube channel resolution[/bold cyan] | cached={len(resolved)} "
            f"| pending={len(unresolved)}"
        )
        for index, reference in enumerate(unresolved, 1):
            try:
                channel_id = _resolve_youtube_channel_id(reference)
                if channel_id:
                    resolved[reference] = channel_id
                    totals["youtube_handles_resolved_this_run"] += 1
                else:
                    totals["youtube_handles_unresolved_this_run"] += 1
            except Exception as exc:
                message = f"{type(exc).__name__}: {str(exc)[:180]}"
                console.print(f"[yellow]Could not resolve @{reference}: {message}[/yellow]")
                totals["youtube_resolution_errors"] += 1
                if any(token in message.casefold() for token in ("429", "403", "captcha", "bot", "rate limit")):
                    console.print("[yellow]YouTube access restriction detected; stopping handle resolution without retries or bypass.[/yellow]")
                    break
            if index % 25 == 0:
                _save_resolution_cache(cache_path, resolved)
                console.print(f"[dim]Resolved {index}/{len(unresolved)} pending handles; cached={len(resolved)}[/dim]")
            if resolve_delay_seconds:
                time.sleep(resolve_delay_seconds)
        _save_resolution_cache(cache_path, resolved)
        youtube_channel_ids = list(dict.fromkeys(resolved.values()))
    else:
        youtube_channel_ids = []

    jobs: list[tuple[str, list[str], list[str], str]] = []
    if "instagram" in selected:
        for index, chunk in enumerate(_chunks(instagram_creators, creator_batch_size), 1):
            jobs.append(("instagram", chunk, [], f"instagram-creators-{index:04d}"))
        for index, chunk in enumerate(_chunks(hashtags, instagram_hashtag_batch_size), 1):
            jobs.append(("instagram", [], chunk, f"instagram-hashtags-{index:04d}"))
    if "youtube" in selected:
        for index, chunk in enumerate(_chunks(youtube_channel_ids, creator_batch_size), 1):
            jobs.append(("youtube", chunk, [], f"youtube-creators-{index:04d}"))
        for index, chunk in enumerate(_chunks(hashtags, youtube_hashtag_batch_size), 1):
            jobs.append(("youtube", [], chunk, f"youtube-hashtags-{index:04d}"))

    blocked: set[str] = set()
    for index, (platform, creators, tags, label) in enumerate(jobs, 1):
        if platform in blocked:
            continue
        console.print(
            f"\n[bold cyan]URL discovery {index}/{len(jobs)} · {label}[/bold cyan] "
            f"| creators={len(creators)} hashtags={len(tags)}"
        )
        try:
            summary = _run_batch(
                platform=platform,
                creators=creators,
                hashtags=tags,
                database=database,
                profile_dir=instagram_profile_dir,
                runtime_seconds=runtime_seconds,
                report_path=reports / f"{label}.json",
            )
        except Exception as exc:
            console.print(f"[red]Batch failed: {type(exc).__name__}: {exc}[/red]")
            totals["failed_batches"] += 1
            blocked.add(platform)
            continue
        totals["batches_completed"] += 1
        totals[f"{platform}_candidates_observed"] += int(summary.get("candidates_observed", 0))
        errors = summary.get("error_details", [])
        if any(
            any(token in str(error).casefold() for token in (
                "captcha", "challenge", "rate limit", "429", "403", "forbidden",
                "login required", "checkpoint", "temporarily blocked",
            ))
            for error in errors
        ):
            blocked.add(platform)
            console.print(f"[yellow]{platform} discovery stopped after an access restriction. Resume after normal access is restored.[/yellow]")
        ig_count = _export_urls(database, "instagram", output_dir / "instagram_reels.txt")
        yt_count = _export_urls(database, "youtube", output_dir / "youtube_shorts.txt")
        console.print(
            f"[green]URL checkpoint saved[/green] | Instagram={ig_count} | YouTube={yt_count}"
        )

    ig_count = _export_urls(database, "instagram", output_dir / "instagram_reels.txt")
    yt_count = _export_urls(database, "youtube", output_dir / "youtube_shorts.txt")
    report = {
        "schema_version": "shortslm.url-collection.v1",
        "catalogue": {
            "instagram_creator_candidates": len(instagram_creators),
            "youtube_creator_candidates": len(youtube_references),
            "youtube_channel_ids_resolved": len(youtube_channel_ids),
            "hashtags": len(hashtags),
        },
        "totals": dict(totals),
        "exported_urls": {"instagram_reels": ig_count, "youtube_shorts": yt_count},
        "files": {
            "instagram_reels": str((output_dir / "instagram_reels.txt").resolve()),
            "youtube_shorts": str((output_dir / "youtube_shorts.txt").resolve()),
        },
        "blocked_platforms": sorted(blocked),
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "media_downloaded": False,
        "feature_extraction_performed": False,
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "summary.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    table = Table(title="ShortsLM URL collection")
    table.add_column("Output")
    table.add_column("Unique URLs", justify="right")
    table.add_row("Instagram Reels", str(ig_count))
    table.add_row("YouTube Shorts", str(yt_count))
    table.add_row("Discovery batches", str(totals["batches_completed"]))
    table.add_row("Blocked platforms", ", ".join(sorted(blocked)) or "none")
    console.print(table)
    console.print("[green]Metadata-only run complete. No video or audio media was downloaded.[/green]")
    console.print("[bold]Git-trackable URL files:[/bold]")
    console.print(output_dir / "instagram_reels.txt")
    console.print(output_dir / "youtube_shorts.txt")
