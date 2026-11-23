"""User-facing command line for the Phase 1 short-video telemetry pipeline."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Literal

import typer
from rich.console import Console
from rich.table import Table

# Importing phase4_master registers the resumable run-all command on phase4_app.
from shorts_intelligence import (
    __version__,
    phase4_master,  # noqa: F401
)
from shorts_intelligence.analyzer import analyze_video
from shorts_intelligence.campaign import campaign_app
from shorts_intelligence.config import AnalyzerConfig
from shorts_intelligence.discovery.cli import discovery_app
from shorts_intelligence.media.probe import MediaError
from shorts_intelligence.phase4 import phase4_app
from shorts_intelligence.pilot.cli import pilot_app
from shorts_intelligence.url_collection import url_collection_app

app = typer.Typer(
    name="shorts-lm",
    help="Discover public short-form links with open-source tools, acquire permitted media, and analyze locally.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def analyze(
    input: Path = typer.Option(
        ..., "--input", "-i", exists=True, readable=True,
        help="Local MP4/MOV/MKV/WebM/AVI file.",
    ),
    output: Path = typer.Option(
        Path("outputs/analysis.json"), "--output", "-o",
        help="JSON report destination.",
    ),
    max_duration: float = typer.Option(
        180.0, "--max-duration", min=1.0, max=1800.0,
        help="Maximum duration accepted in seconds.",
    ),
    max_file_size_mb: int = typer.Option(
        500, "--max-file-size-mb", min=1, max=10000,
        help="Maximum input size in MB.",
    ),
    max_keyframes: int = typer.Option(48, "--max-keyframes", min=4, max=96),
    max_ocr_frames: int = typer.Option(12, "--max-ocr-frames", min=1, max=64),
    asr_model: str = typer.Option(
        "small", "--asr-model",
        help="faster-whisper model: tiny, base, small, medium or large-v3.",
    ),
    asr_device: Literal["cpu", "cuda", "auto"] = typer.Option(
        "cuda",
        "--device",
        "--asr-device",
        help="Inference device for Whisper and PaddleOCR; CUDA is the default.",
    ),
    language: str | None = typer.Option(
        None, "--language",
        help="Optional language code, e.g. hi, en, mr. Omit for auto-detection.",
    ),
    asr_timeout_seconds: int = typer.Option(
        300, "--asr-timeout-seconds", min=10, max=3600,
        help="Hard ASR timeout; stuck inference is terminated.",
    ),
    no_asr: bool = typer.Option(False, "--no-asr", help="Skip speech transcription."),
    no_ocr: bool = typer.Option(False, "--no-ocr", help="Skip on-screen text extraction."),
    no_audio_analysis: bool = typer.Option(
        False, "--no-audio-analysis", help="Skip librosa acoustic features.",
    ),
    keep_artifacts: bool = typer.Option(
        False, "--keep-artifacts",
        help="Keep selected keyframe JPEGs beside the JSON report.",
    ),
) -> None:
    """Analyze one local video and write a JSON report."""
    config = AnalyzerConfig(
        max_file_size_mb=max_file_size_mb,
        max_duration_seconds=max_duration,
        max_keyframes=max_keyframes,
        max_ocr_frames=max_ocr_frames,
        asr_model=asr_model,
        asr_device=asr_device,
        asr_timeout_seconds=asr_timeout_seconds,
        language=language,
        enable_asr=not no_asr,
        enable_ocr=not no_ocr,
        enable_audio_analysis=not no_audio_analysis,
        keep_artifacts=keep_artifacts,
    )
    try:
        report = analyze_video(
            input_path=input,
            output_path=output,
            config=config,
        )
    except (MediaError, ValueError, OSError, RuntimeError) as exc:
        console.print(f"[bold red]Analysis failed:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    console.print("[bold green]Phase 1 telemetry complete.[/bold green]")
    console.print(f"Report: [cyan]{output.expanduser().resolve()}[/cyan]")
    console.print(
        f"Duration: {report.video.duration_seconds:.2f}s | "
        f"Frames retained: {len(report.frame_evidence)} | "
        f"Cut candidates: {len(report.cut_candidates)}"
    )
    console.print(
        f"ASR segments: {len(report.transcript_segments)} | "
        f"OCR spans: {len(report.ocr_spans)} | "
        f"Audio analyzed: {report.audio.analyzed}"
    )
    for warning in report.warnings:
        console.print(f"[yellow]Warning:[/yellow] {warning}")



def _supported_js_runtime(executable: str, minimum: tuple[int, int]) -> tuple[bool, str | None]:
    """Return whether a supported yt-dlp EJS runtime is installed and recent enough."""
    path = shutil.which(executable)
    if path is None:
        return False, None
    try:
        result = subprocess.run(
            [path, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=4,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, None
    output = (result.stdout or result.stderr).strip()
    match = re.search(r"([0-9]+)[.]([0-9]+)", output)
    if not match or result.returncode != 0:
        return False, output.splitlines()[0] if output else None
    version = (int(match.group(1)), int(match.group(2)))
    return version >= minimum, output.splitlines()[0] if output else None


def _distribution_installed(name: str) -> bool:
    try:
        importlib.metadata.version(name)
        return True
    except importlib.metadata.PackageNotFoundError:
        return False


@app.command()
def doctor(
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable dependency status.")
) -> None:
    """Check external binaries, Python engines and yt-dlp YouTube prerequisites."""
    deno_ok, deno_version = _supported_js_runtime("deno", (2, 3))
    node_ok, node_version = _supported_js_runtime("node", (22, 0))
    gpu_name = None
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            gpu_result = subprocess.run(
                [nvidia_smi, "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if gpu_result.returncode == 0 and gpu_result.stdout.strip():
                gpu_name = gpu_result.stdout.strip().splitlines()[0]
        except (OSError, subprocess.TimeoutExpired):
            pass

    ctranslate2_cuda = False
    try:
        import ctranslate2
        ctranslate2_cuda = ctranslate2.get_cuda_device_count() > 0
    except Exception:
        pass

    paddle_cuda = False
    try:
        import paddle
        paddle_cuda = bool(paddle.is_compiled_with_cuda())
    except Exception:
        pass

    checks = {
        "nvidia_smi": gpu_name is not None,
        "ctranslate2_cuda": ctranslate2_cuda,
        "paddle_cuda": paddle_cuda,
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "ffprobe": shutil.which("ffprobe") is not None,
        "opencv": importlib.util.find_spec("cv2") is not None,
        "librosa": importlib.util.find_spec("librosa") is not None,
        "faster_whisper": importlib.util.find_spec("faster_whisper") is not None,
        "paddleocr": importlib.util.find_spec("paddleocr") is not None,
        "vidtrace": importlib.util.find_spec("vidtrace") is not None,
        "ytscrape": _distribution_installed("ytscrape"),
        "yt_dlp": importlib.util.find_spec("yt_dlp") is not None,
        "yt_dlp_ejs": _distribution_installed("yt-dlp-ejs"),
        "deno_2_3_or_newer": deno_ok,
        "node_22_or_newer": node_ok,
        "instaloader": importlib.util.find_spec("instaloader") is not None,
        "ddgs": importlib.util.find_spec("ddgs") is not None,
        "gallery_dl": importlib.util.find_spec("gallery_dl") is not None,
    }
    if as_json:
        typer.echo(json.dumps({"version": __version__, "checks": checks}, indent=2))
        return
    table = Table(title=f"ShortsLM doctor · v{__version__}")
    table.add_column("Dependency")
    table.add_column("Status")
    for name, available in checks.items():
        table.add_row(
            name,
            "[green]available[/green]" if available else "[yellow]not installed[/yellow]",
        )
    console.print(table)
    if gpu_name:
        console.print(f"[dim]NVIDIA GPU: {gpu_name}[/dim]")
    if not checks["ctranslate2_cuda"]:
        console.print(
            "[yellow]Whisper CUDA is unavailable. Check that CUDA 12 cuBLAS "
            "(cublas64_12.dll) and cuDNN 9 are installed and on PATH. "
            "Whisper will otherwise fall back to CPU.[/yellow]"
        )
    if not checks["paddle_cuda"]:
        console.print(
            "[yellow]The installed PaddlePaddle build has no CUDA support. "
            "PaddleOCR will run on CPU; install the matching Windows "
            "paddlepaddle-gpu wheel if GPU OCR is required.[/yellow]"
        )
    if not checks["ffmpeg"] or not checks["ffprobe"]:
        console.print("[red]FFmpeg and ffprobe are required for media processing.[/red]")
    if not checks["ytscrape"]:
        console.print('[yellow]YouTube Shorts discovery needs ytscrape >=2.2; install with pip install -e ".[discovery]".[/yellow]')
    if checks["yt_dlp"] and not checks["yt_dlp_ejs"]:
        console.print("[yellow]YouTube extraction: install matching EJS scripts with pip install -U 'yt-dlp[default]'.[/yellow]")
    if checks["yt_dlp"] and not (deno_ok or node_ok):
        console.print("[yellow]YouTube full video extraction needs Deno >=2.3 (recommended) or Node.js >=22.[/yellow]")
    if deno_version:
        console.print(f"[dim]Deno: {deno_version}[/dim]")
    if node_version:
        console.print(f"[dim]Node.js: {node_version}[/dim]")


@app.command()
def version() -> None:
    """Print package version."""
    typer.echo(__version__)


app.add_typer(pilot_app, name="pilot")
app.add_typer(discovery_app, name="discover")
app.add_typer(phase4_app, name="phase4")
app.add_typer(campaign_app, name="campaign")
app.add_typer(url_collection_app, name="urls")
