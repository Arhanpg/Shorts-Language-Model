"""Simple randomized sampling from the committed creator and hashtag catalogue."""

from __future__ import annotations

import csv
import random
import re
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

campaign_app = typer.Typer(
    name="campaign",
    help="Randomly sample creator and hashtag seeds for discovery campaigns.",
    no_args_is_help=True,
)
console = Console()


def _read(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_seeds(path: Path, values: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{value}\n" for value in values), encoding="utf-8")


@campaign_app.command("sample")
def sample(
    catalogue_dir: Path = typer.Option(
        Path("outputs/phase4/catalogue"), "--catalogue-dir",
        exists=True, file_okay=False,
    ),
    output_dir: Path = typer.Option(Path("outputs/campaign"), "--output-dir"),
    creators_per_platform: int = typer.Option(100, "--creators", min=1, max=5000),
    hashtags_per_platform: int = typer.Option(100, "--hashtags", min=1, max=5000),
    seed: int | None = typer.Option(None, "--seed", help="Optional reproducible random seed."),
) -> None:
    """Randomly sample creator and hashtag seeds independently for both platforms.

    YouTube creator seeds are restricted to stable UC channel IDs; unresolved
    handles remain in the catalogue CSV for later manual resolution.
    """
    rng = random.Random(seed)
    creators: dict[str, list[dict[str, str]]] = {"youtube": [], "instagram": []}
    for platform in creators:
        path = catalogue_dir / f"{platform}_creator_candidates.csv"
        if not path.exists():
            continue
        rows = _read(path)
        for row in rows:
            identity = (row.get("identity") or "").strip()
            if not identity:
                continue
            if platform == "youtube" and not re.fullmatch(r"UC[A-Za-z0-9_-]{22}", identity):
                continue
            creators[platform].append(row)

    tag_path = catalogue_dir / "hashtag_candidates.csv"
    tags = _read(tag_path) if tag_path.exists() else []
    selected_tags: dict[str, list[dict[str, str]]] = {}
    for platform in ("youtube", "instagram"):
        platform_tags = [
            row for row in tags
            if not (row.get("platform") or "").strip()
            or (row.get("platform") or "").strip().casefold() == platform
        ]
        # The current catalogue is platform-neutral; its candidate tags are
        # available to both discovery providers unless a source labels a platform.
        rng.shuffle(platform_tags)
        selected_tags[platform] = platform_tags[:hashtags_per_platform]

    output_dir = output_dir.expanduser().resolve()
    report: dict[str, object] = {"seed": seed, "platforms": {}}
    table = Table(title="Random campaign sample")
    table.add_column("Platform")
    table.add_column("Creators", justify="right")
    table.add_column("Hashtags", justify="right")
    for platform in ("youtube", "instagram"):
        rows = creators[platform][:]
        rng.shuffle(rows)
        rows = rows[:creators_per_platform]
        tags_for_platform = selected_tags[platform]
        _write_csv(output_dir / f"{platform}_creators.csv", rows, ["platform", "identity", "source", "display_name", "verification"])
        _write_seeds(
            output_dir / f"{platform}_creator_seeds.txt",
            [row["identity"] for row in rows],
        )
        _write_csv(output_dir / f"{platform}_hashtags.csv", tags_for_platform, ["hashtag", "language", "domain", "source"])
        _write_seeds(
            output_dir / f"{platform}_hashtag_seeds.txt",
            [str(row.get("hashtag") or "").lstrip("#") for row in tags_for_platform],
        )
        report["platforms"][platform] = {
            "creator_candidates_available": len(creators[platform]),
            "creators_sampled": len(rows),
            "hashtags_available": len(tags),
            "hashtags_sampled": len(tags_for_platform),
        }
        table.add_row(platform, str(len(rows)), str(len(tags_for_platform)))

    output_dir.mkdir(parents=True, exist_ok=True)
    import json

    (output_dir / "sample_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    console.print(table)
    console.print(f"Randomized seed files: {output_dir}")
    if seed is None:
        console.print("[dim]Random sample is not reproducible; pass --seed to reproduce it.[/dim]")
