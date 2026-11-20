"""Phase 2 CLI: manifest validation, stratified sampling, processing and reports."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from shorts_intelligence.config import AnalyzerConfig
from shorts_intelligence.pilot.manifest import (
    load_and_validate_manifest,
    validation_template_record,
    write_json,
)
from shorts_intelligence.pilot.matching import build_matched_pairs
from shorts_intelligence.pilot.reporting import build_pilot_report
from shorts_intelligence.pilot.runner import process_selected
from shorts_intelligence.pilot.sampling import (
    create_or_load_salt,
    select_stratified,
    write_selection_outputs,
)

pilot_app = typer.Typer(
    name="pilot",
    help="Phase 2: build a rights-aware, reproducible 300-video diagnostic pilot.",
    no_args_is_help=True,
)
console = Console()


@pilot_app.command("template")
def template(
    output: Path = typer.Option(
        Path("data/private/manifest.example.jsonl"), "--output", "-o"
    ),
) -> None:
    """Write one example JSONL row; no real media or permission is fabricated."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(validation_template_record(), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    console.print(f"[green]Template written:[/green] {output.resolve()}")
    console.print(
        "[yellow]Replace the example path, creator identifier and evidence reference. "
        "The template is invalid until it refers to permitted media and documented rights.[/yellow]"
    )


@pilot_app.command("validate")
def validate(
    manifest: Path = typer.Option(..., "--manifest", "-m", exists=True, readable=True),
    report: Path = typer.Option(
        Path("outputs/pilot/validation.json"), "--report", "-o"
    ),
    require_training_rights: bool = typer.Option(
        False, "--require-training-rights",
        help="Reject records that do not explicitly permit model training.",
    ),
    max_duration: float = typer.Option(180.0, "--max-duration", min=1, max=1800),
    max_file_size_mb: int = typer.Option(
        500, "--max-file-size-mb", min=1, max=10000
    ),
) -> None:
    """Validate rights, local media, uniqueness, file size and video metadata."""
    try:
        result = load_and_validate_manifest(
            manifest,
            max_file_size_mb=max_file_size_mb,
            max_duration_seconds=max_duration,
            require_training_rights=require_training_rights,
        )
    except Exception as exc:
        console.print(f"[bold red]Manifest validation failed:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc
    write_json(report, result.summary)
    table = Table(title="Phase 2 manifest validation")
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    for label, value in [
        ("Input rows", result.summary.input_rows),
        ("Accepted unique videos", result.summary.accepted_rows),
        ("Rejected rows", result.summary.rejected_rows),
        ("Duplicate media rows", result.summary.duplicate_media_rows),
        ("Training-permitted accepted rows", result.summary.training_permitted_rows),
    ]:
        table.add_row(label, str(value))
    console.print(table)
    console.print(f"Report: {report.resolve()}")
    if result.summary.rejected_rows:
        console.print("[yellow]Review issues in the validation JSON before sampling.[/yellow]")


@pilot_app.command("sample")
def sample(
    manifest: Path = typer.Option(..., "--manifest", "-m", exists=True, readable=True),
    output_dir: Path = typer.Option(Path("outputs/pilot"), "--output-dir", "-o"),
    target: int = typer.Option(300, "--target", min=1, max=100000),
    seed: int = typer.Option(42, "--seed"),
    max_per_creator: int = typer.Option(5, "--max-per-creator", min=0, max=10000),
    require_training_rights: bool = typer.Option(False, "--require-training-rights"),
    allow_shortfall: bool = typer.Option(False, "--allow-shortfall"),
    salt_file: Path = typer.Option(Path(".shortslm/creator_salt"), "--salt-file"),
    max_duration: float = typer.Option(180.0, "--max-duration", min=1, max=1800),
    max_file_size_mb: int = typer.Option(
        500, "--max-file-size-mb", min=1, max=10000
    ),
) -> None:
    """Create a deterministic stratified sample, creator groups, pairs and review queue."""
    try:
        validation = load_and_validate_manifest(
            manifest,
            max_file_size_mb=max_file_size_mb,
            max_duration_seconds=max_duration,
            require_training_rights=require_training_rights,
        )
        if len(validation.candidates) < target and not allow_shortfall:
            raise ValueError(
                f"Need {target} valid unique records, but found {len(validation.candidates)}. "
                "Add eligible records or pass --allow-shortfall for a smaller diagnostic run."
            )
        salt = create_or_load_salt(salt_file)
        selected, summary = select_stratified(
            validation.candidates,
            target=min(target, len(validation.candidates)),
            seed=seed,
            max_per_creator=max_per_creator,
            salt=salt,
        )
        if len(selected) < target and not allow_shortfall:
            raise ValueError(
                f"Per-creator cap reduced selection to {len(selected)} of {target}. "
                "Increase --max-per-creator or pass --allow-shortfall."
            )
        # Preserve the original requested target when a diagnostic shortfall is allowed.
        summary["target"] = target
        summary["shortfall"] = max(0, target - len(selected))
        pairs = build_matched_pairs(selected)
        write_selection_outputs(
            output_dir, selected, summary,
            [item.model_dump(mode="json") for item in pairs],
        )
        write_json(output_dir / "validation_summary.json", validation.summary)
    except Exception as exc:
        console.print(f"[bold red]Pilot sampling failed:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    console.print("[bold green]Phase 2 sample created.[/bold green]")
    console.print(
        f"Selected {len(selected)} / {target} records; "
        f"{len(pairs)} same-creator matched pairs; "
        f"{summary['unique_creator_groups_in_selection']} pseudonymous creator groups."
    )
    console.print(f"Output directory: {output_dir.resolve()}")
    if summary["shortfall"]:
        console.print("[yellow]Shortfall recorded. Review selection_report.json.[/yellow]")
    console.print(
        "[yellow]The selected manifest contains local paths and must remain private. "
        "Never commit pilot data, reports, creator IDs or consent evidence to GitHub.[/yellow]"
    )


@pilot_app.command("process")
def process(
    manifest: Path = typer.Option(..., "--manifest", "-m", exists=True, readable=True),
    output_dir: Path = typer.Option(Path("outputs/pilot"), "--output-dir", "-o"),
    limit: int | None = typer.Option(None, "--limit", min=1),
    max_duration: float = typer.Option(180.0, "--max-duration", min=1, max=1800),
    max_keyframes: int = typer.Option(48, "--max-keyframes", min=4, max=96),
    max_ocr_frames: int = typer.Option(12, "--max-ocr-frames", min=1, max=64),
    asr_model: str = typer.Option("small", "--asr-model"),
    asr_device: str = typer.Option("cpu", "--asr-device"),
    no_asr: bool = typer.Option(False, "--no-asr"),
    no_ocr: bool = typer.Option(False, "--no-ocr"),
    no_audio_analysis: bool = typer.Option(False, "--no-audio-analysis"),
    keep_artifacts: bool = typer.Option(False, "--keep-artifacts"),
    resume: bool = typer.Option(
        True, "--resume/--no-resume",
        help="Reuse completed reports only when input checksum, rights reference and config match.",
    ),
) -> None:
    """Run Phase 1 telemetry for selected Phase 2 records, sequentially and locally."""
    try:
        config = AnalyzerConfig(
            max_duration_seconds=max_duration,
            max_keyframes=max_keyframes,
            max_ocr_frames=max_ocr_frames,
            asr_model=asr_model,
            asr_device=asr_device,
            enable_asr=not no_asr,
            enable_ocr=not no_ocr,
            enable_audio_analysis=not no_audio_analysis,
            keep_artifacts=keep_artifacts,
        )
        summary = process_selected(
            manifest, output_dir, limit=limit, config=config, resume=resume
        )
    except Exception as exc:
        console.print(f"[bold red]Pilot processing failed:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc
    console.print("[bold green]Pilot processing finished.[/bold green]")
    for key in (
        "processed_records", "complete_records", "partial_records",
        "failed_records", "total_wall_seconds", "mean_seconds_per_record_this_run",
        "resumed_records", "analyzed_new_records",
        "input_media_file_bytes_total", "telemetry_report_json_bytes_total",
        "keyframe_artifact_bytes_total", "training_permitted_processed_records",
    ):
        console.print(f"{key}: {summary.get(key)}")
    console.print(f"Metrics: {(output_dir / 'processing_metrics.csv').resolve()}")


@pilot_app.command("report")
def report(
    pilot_dir: Path = typer.Option(Path("outputs/pilot"), "--pilot-dir", "-d"),
    output: Path = typer.Option(
        Path("outputs/pilot/final_pilot_report.json"), "--output", "-o"
    ),
) -> None:
    """Combine selection, matched-pair, human-review and processing metrics."""
    try:
        result = build_pilot_report(pilot_dir, output)
    except Exception as exc:
        console.print(f"[bold red]Could not build pilot report:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc
    console.print(f"[green]Pilot report written:[/green] {output.resolve()}")
    console.print(f"Selection: {result.get('selected_records')} videos")
    console.print(f"Matched pairs: {result.get('matched_pairs')}")
    processing = result.get("processing")
    console.print(f"Processing success rate: {processing.get('success_rate') if processing else 'not run'}")
    console.print("[yellow]This is a diagnostic report, not a completed training dataset.[/yellow]")
