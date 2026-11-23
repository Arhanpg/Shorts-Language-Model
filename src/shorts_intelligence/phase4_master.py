"""One-command, resumable Phase 4 discovery and sequential feature extraction."""

from __future__ import annotations

import asyncio
import csv
import json
import random
import time
from collections import Counter
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from shorts_intelligence.discovery.engine import run_creator_graph
from shorts_intelligence.discovery.processing import run_processing_batch
from shorts_intelligence.discovery.storage import DiscoveryStore
from shorts_intelligence.phase4 import catalogue

console = Console()


def _read_values(path: Path, field: str) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            value.strip()
            for row in csv.DictReader(handle)
            if (value := str(row.get(field) or "").strip())
        ]


def _chunks(values: list[str], size: int):
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def _write_lines(path: Path, values: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{value}\n" for value in values), encoding="utf-8")


def _blocked(summary: dict[str, Any]) -> bool:
    results = [*summary.get("creator_results", []), *summary.get("hashtag_results", [])]
    if any(item.get("status") == "blocked" for item in results):
        return True
    messages = summary.get("error_details", [])
    return any(
        any(token in str(message).casefold() for token in (
            "captcha", "challenge", "rate limit", "429", "403", "forbidden",
            "login required", "checkpoint", "temporarily blocked",
        ))
        for message in messages
    )


def _discover(
    *,
    platform: str,
    creators: list[str],
    hashtags: list[str],
    database: Path,
    profile_dir: Path,
    runtime_seconds: int,
    min_metric: int,
    target_new: int,
    report_path: Path,
    creator_limit: int | None = None,
) -> dict[str, Any]:
    with DiscoveryStore(database) as store:
        summary = asyncio.run(run_creator_graph(
            store,
            platform=platform,
            target_new=target_new,
            min_metric=min_metric,
            max_runtime_seconds=runtime_seconds,
            max_seed_queries=0,
            max_hashtag_queries=min(20, len(hashtags)) if platform == "youtube" else 0,
            max_creators=min(500, len(creators)) if creator_limit is None else creator_limit,
            max_expansions=0,
            max_depth=0,
            instagram_profile_dir=profile_dir if platform == "instagram" else None,
            instagram_creators=creators if platform == "instagram" else None,
            instagram_hashtags=hashtags if platform == "instagram" else None,
            youtube_creators=creators if platform == "youtube" else None,
            youtube_hashtags=hashtags if platform == "youtube" else None,
            instagram_max_scrolls=8,
            instagram_max_reel_details=3,
            instagram_hashtag_max_reel_details=8,
            max_instagram_hashtags=min(100, len(hashtags)) if platform == "instagram" else 0,
            continue_graph_after_target=True,
        ))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return summary


def _drain_processing(
    *,
    database: Path,
    download_dir: Path,
    artifact_dir: Path,
    manifest: Path,
    platform: str,
    batch_size: int,
    min_metric: int,
    asr_model: str,
    device: str,
    asr_timeout_seconds: int,
    max_duration: float,
    max_file_size_mb: int,
    max_keyframes: int,
    max_ocr_frames: int,
    instagram_session_user: str | None,
    instagram_session_file: Path | None,
    max_attempts: int,
) -> dict[str, int | str]:
    totals: Counter[str] = Counter()
    last: dict[str, int | str] = {}
    # Each attempt is persisted in SQLite. max_attempts makes this loop finite.
    while True:
        last = run_processing_batch(
            database=database,
            download_dir=download_dir,
            artifact_dir=artifact_dir,
            dataset_manifest=manifest,
            limit=batch_size,
            min_metric=min_metric,
            platform=platform,
            instagram_session_username=instagram_session_user,
            instagram_session_file=instagram_session_file,
            asr_model=asr_model,
            asr_device=device,
            asr_timeout_seconds=asr_timeout_seconds,
            max_duration_seconds=max_duration,
            max_file_size_mb=max_file_size_mb,
            max_keyframes=max_keyframes,
            max_ocr_frames=max_ocr_frames,
            keep_frame_artifacts=False,
            delete_media_after_processing=True,
            max_processing_attempts=max_attempts,
        )
        for key in (
            "candidates_selected", "media_downloaded_this_run", "processed_this_run",
            "duplicates", "failed", "youtube_downloaded", "instagram_downloaded",
            "youtube_processed", "instagram_processed",
        ):
            totals[key] += int(last.get(key, 0))
        if int(last.get("candidates_selected", 0)) == 0:
            break
        console.print(
            f"[cyan]Processing batch:[/cyan] selected={last.get('candidates_selected', 0)}, "
            f"processed={last.get('processed_this_run', 0)}, failed={last.get('failed', 0)}"
        )
    totals["processing_complete_total"] = int(last.get("processing_complete_total", 0))
    totals["processing_failed_total"] = int(last.get("processing_failed_total", 0))
    totals["manifest_records"] = int(last.get("manifest_records", 0))
    totals["manifest_path"] = str(manifest.resolve())
    return dict(totals)


from shorts_intelligence.phase4 import phase4_app


@phase4_app.command("run-all")
def run_all(
    catalogue_dir: Path = typer.Option(Path("data/seed_catalogue/v0.2"), "--catalogue-dir", exists=True, file_okay=False),
    output_dir: Path = typer.Option(Path("outputs/phase4"), "--output-dir"),
    database: Path = typer.Option(Path(".shortslm/discovery.sqlite3"), "--database"),
    download_dir: Path = typer.Option(Path("data/private/acquired"), "--download-dir"),
    artifact_dir: Path = typer.Option(Path("data/private/processed"), "--artifact-dir"),
    manifest: Path = typer.Option(Path("outputs/dataset/phase4-features.jsonl"), "--manifest"),
    instagram_profile_dir: Path = typer.Option(Path(".shortslm/browser/instagram"), "--instagram-profile-dir"),
    instagram_session_user: str | None = typer.Option(None, "--instagram-session-user"),
    instagram_session_file: Path | None = typer.Option(None, "--instagram-session-file", exists=True, readable=True),
    seed: int = typer.Option(20261123, "--seed"),
    min_metric: int = typer.Option(1_000_000, "--min-metric", min=0),
    target_new_per_batch: int = typer.Option(2000, "--target-new-per-batch", min=1, max=2000),
    discovery_runtime_seconds: int = typer.Option(900, "--discovery-runtime-seconds", min=30, max=900),
    creator_batch_size: int = typer.Option(100, "--creator-batch-size", min=1, max=500),
    instagram_hashtag_batch_size: int = typer.Option(50, "--instagram-hashtag-batch-size", min=1, max=100),
    youtube_hashtag_batch_size: int = typer.Option(20, "--youtube-hashtag-batch-size", min=1, max=20),
    processing_batch_size: int = typer.Option(25, "--processing-batch-size", min=1, max=500),
    max_processing_attempts: int = typer.Option(2, "--max-processing-attempts", min=1, max=5),
    asr_model: str = typer.Option("small", "--asr-model"),
    device: str = typer.Option("cuda", "--device"),
    asr_timeout_seconds: int = typer.Option(300, "--asr-timeout-seconds", min=10, max=3600),
    max_duration: float = typer.Option(180.0, "--max-duration", min=1, max=1800),
    max_file_size_mb: int = typer.Option(1000, "--max-file-size-mb", min=1, max=10000),
    max_keyframes: int = typer.Option(24, "--max-keyframes", min=4, max=96),
    max_ocr_frames: int = typer.Option(12, "--max-ocr-frames", min=1, max=64),
    all_catalogue: bool = typer.Option(False, "--all-catalogue", help="Required acknowledgement before processing the full catalogue."),
) -> None:
    """Discover the full catalogue and sequentially extract features, deleting temporary media."""
    if not all_catalogue:
        raise typer.BadParameter("Pass --all-catalogue to explicitly confirm the potentially multi-day full-catalogue run.")
    if not instagram_profile_dir.exists():
        raise typer.BadParameter(
            f"Instagram browser profile not found: {instagram_profile_dir}. "
            "Run 'shorts-lm discover instagram-browser-login' and complete sign-in manually first."
        )

    started = time.monotonic()
    output_dir = output_dir.expanduser().resolve()
    catalogue_output = output_dir / "catalogue"
    reports_dir = output_dir / "runs"
    catalogue(
        catalogue_dir=catalogue_dir,
        output_dir=catalogue_output,
        batch_size=creator_batch_size,
        hashtag_batch_size=instagram_hashtag_batch_size,
    )

    instagram_creators = _read_values(catalogue_output / "instagram_creator_candidates.csv", "identity")
    youtube_creators_all = _read_values(catalogue_output / "youtube_creator_candidates.csv", "identity")
    youtube_creators = [value for value in youtube_creators_all if value.startswith("UC") and len(value) == 24]
    youtube_unresolved = len(youtube_creators_all) - len(youtube_creators)
    hashtags = _read_values(catalogue_output / "hashtag_candidates.csv", "hashtag")

    rng = random.Random(seed)
    rng.shuffle(instagram_creators)
    rng.shuffle(youtube_creators)
    rng.shuffle(hashtags)
    console.print(
        f"[bold]Full Phase 4 campaign[/bold] | Instagram creators={len(instagram_creators)}, "
        f"YouTube channel IDs={len(youtube_creators)} (unresolved handles skipped={youtube_unresolved}), "
        f"unique hashtags={len(hashtags)} (each platform)"
    )
    console.print("[yellow]Instagram and YouTube metrics are kept platform-specific. Media files are temporary and deleted after each processing attempt.[/yellow]")
    if not instagram_creators:
        raise typer.BadParameter("The normalized catalogue contains zero Instagram creators. Check source CSV headers and catalogue inputs.")
    if not youtube_creators:
        console.print("[bold yellow]No stable YouTube UC channel IDs were found. YouTube creator-harvest batches will be skipped; YouTube hashtag discovery will still run. Handle-only leads are reported for a separate resolver workflow.[/bold yellow]")

    totals: Counter[str] = Counter()
    blocked_platforms: list[str] = []
    discovery_batches = 0

    # Each platform receives every catalogue hashtag; independent random order is retained.
    jobs: list[tuple[str, list[str], list[str], str]] = []
    for index, chunk in enumerate(_chunks(instagram_creators, creator_batch_size), 1):
        jobs.append(("instagram", chunk, [], f"instagram-creators-{index:04d}"))
    for index, chunk in enumerate(_chunks(hashtags, instagram_hashtag_batch_size), 1):
        jobs.append(("instagram", [], chunk, f"instagram-hashtags-{index:04d}"))
    for index, chunk in enumerate(_chunks(youtube_creators, creator_batch_size), 1):
        jobs.append(("youtube", chunk, [], f"youtube-creators-{index:04d}"))
    for index, chunk in enumerate(_chunks(hashtags, youtube_hashtag_batch_size), 1):
        jobs.append(("youtube", [], chunk, f"youtube-hashtags-{index:04d}"))

    for platform, creators, tags, label in jobs:
        if platform in blocked_platforms:
            continue
        report_path = reports_dir / f"{label}.json"
        console.print(f"\n[bold cyan]Discovery {label}[/bold cyan] | creators={len(creators)} hashtags={len(tags)}")
        try:
            summary = _discover(
                platform=platform,
                creators=creators,
                hashtags=tags,
                database=database,
                profile_dir=instagram_profile_dir,
                runtime_seconds=discovery_runtime_seconds,
                min_metric=min_metric,
                target_new=target_new_per_batch,
                report_path=report_path,
            )
        except Exception as exc:
            console.print(f"[red]Discovery batch failed ({label}): {type(exc).__name__}: {exc}[/red]")
            totals["discovery_batches_failed"] += 1
            blocked_platforms.append(platform)
            console.print(f"[yellow]Stopping {platform} discovery after an unhandled batch error to avoid repeated failing requests.[/yellow]")
            continue
        discovery_batches += 1
        totals["discovery_candidates_observed"] += int(summary.get("candidates_observed", 0))
        totals["discovery_eligible_new"] += int(summary.get("eligible_new", 0))
        totals[f"{platform}_discovery_batches"] += 1
        if _blocked(summary):
            blocked_platforms.append(platform)
            console.print(f"[bold red]{platform} reported an access restriction. Further discovery on this platform is stopped; no bypass/retry will be attempted.[/bold red]")

        processing = _drain_processing(
            database=database,
            download_dir=download_dir,
            artifact_dir=artifact_dir,
            manifest=manifest,
            platform="all",
            batch_size=processing_batch_size,
            min_metric=min_metric,
            asr_model=asr_model,
            device=device,
            asr_timeout_seconds=asr_timeout_seconds,
            max_duration=max_duration,
            max_file_size_mb=max_file_size_mb,
            max_keyframes=max_keyframes,
            max_ocr_frames=max_ocr_frames,
            instagram_session_user=instagram_session_user,
            instagram_session_file=instagram_session_file,
            max_attempts=max_processing_attempts,
        )
        for key, value in processing.items():
            if isinstance(value, int):
                totals[f"processing_{key}"] = max(totals[f"processing_{key}"], value) if key.endswith("_total") else totals[f"processing_{key}"] + value
        console.print(
            f"[green]Checkpoint saved[/green] | manifest records={processing.get('manifest_records', 0)} "
            f"| processing failures this drain={processing.get('failed', 0)}"
        )

    # Drain any creator-frontier work left by runtime-limited discovery batches.
    for platform in ("instagram", "youtube"):
        if platform in blocked_platforms:
            continue
        previous_progress = -1
        for drain_index in range(1, 101):
            try:
                drain_summary = _discover(
                    platform=platform, creators=[], hashtags=[], database=database,
                    profile_dir=instagram_profile_dir, runtime_seconds=discovery_runtime_seconds,
                    min_metric=min_metric, target_new=target_new_per_batch,
                    report_path=reports_dir / f"{platform}-frontier-drain-{drain_index:03d}.json",
                    creator_limit=500,
                )
            except Exception as exc:
                blocked_platforms.append(platform)
                console.print(f"[yellow]Stopping {platform} frontier drain after an unhandled provider error: {type(exc).__name__}: {exc}[/yellow]")
                break
            pending = int(drain_summary.get("creators_pending", 0))
            progress = sum(int(drain_summary.get(key, 0)) for key in (
                "creators_completed", "creators_empty", "creators_exhausted",
                "creators_failed", "creators_blocked",
            ))
            if _blocked(drain_summary):
                blocked_platforms.append(platform)
                break
            if pending <= 0 or progress <= previous_progress:
                break
            previous_progress = progress

    # Final drain catches candidates added by the last discovery operation.
    final_processing = _drain_processing(
        database=database, download_dir=download_dir, artifact_dir=artifact_dir,
        manifest=manifest, platform="all", batch_size=processing_batch_size,
        min_metric=min_metric, asr_model=asr_model, device=device,
        asr_timeout_seconds=asr_timeout_seconds, max_duration=max_duration,
        max_file_size_mb=max_file_size_mb, max_keyframes=max_keyframes,
        max_ocr_frames=max_ocr_frames, instagram_session_user=instagram_session_user,
        instagram_session_file=instagram_session_file, max_attempts=max_processing_attempts,
    )
    report = {
        "schema_version": "phase4.master-run.v1",
        "seed": seed,
        "catalogue": {
            "instagram_creator_candidates": len(instagram_creators),
            "youtube_channel_id_candidates": len(youtube_creators),
            "youtube_handle_only_or_unresolved": youtube_unresolved,
            "unique_hashtags_per_platform": len(hashtags),
        },
        "discovery_batches_completed": discovery_batches,
        "blocked_platforms": blocked_platforms,
        "totals": dict(totals),
        "final_processing": final_processing,
        "manifest": str(manifest.resolve()),
        "database": str(database.resolve()),
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "limitations": [
            "Catalogue entries are candidates, not proof of an active public Shorts/Reels account.",
            "Search providers return best-effort results, not guaranteed global popularity rankings.",
            "Only stable YouTube UC channel IDs are used; unresolved handle-only records are counted and skipped.",
            "Media is deleted after processing; derived feature artifacts and manifests remain local.",
            "A public URL does not itself establish permission to download, retain derived artifacts, or train a model. Run only for content you are authorized to process.",
            "Access restrictions stop further discovery for that platform. The workflow does not bypass login challenges, CAPTCHAs, rate limits or other restrictions.",
        ],
    }
    reports_dir.mkdir(parents=True, exist_ok=True)
    final_report = reports_dir / "master-run-summary.json"
    final_report.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    table = Table(title="Phase 4 master campaign")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for label, value in [
        ("Instagram creator candidates", len(instagram_creators)),
        ("YouTube channel IDs", len(youtube_creators)),
        ("Unresolved YouTube handles", youtube_unresolved),
        ("Unique hashtags per platform", len(hashtags)),
        ("Discovery batches completed", discovery_batches),
        ("Blocked platforms", ", ".join(blocked_platforms) or "none"),
        ("Final manifest records", final_processing.get("manifest_records", 0)),
        ("Elapsed seconds", report["elapsed_seconds"]),
    ]:
        table.add_row(label, str(value))
    console.print(table)
    console.print(f"[bold green]Master report:[/bold green] {final_report}")
    console.print(f"[bold green]Feature manifest:[/bold green] {manifest.resolve()}")
