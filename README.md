# Shorts Language Model

A rights-aware, local-first multimodal system for analyzing short-form videos. The project combines deterministic audiovisual telemetry with a compact video-language model in later phases; **Phase 1 implements the local single-video telemetry pipeline only**.

<p align="center">
  <img src="docs/research/images/telemetry-training-architecture.jpg" alt="Stratified ingestion, telemetry, training and local inference architecture" width="760" />
</p>

## Phase 1 — Single-video telemetry

The first working command accepts a local video file and writes a validated JSON evidence report:

    shorts-lm analyze --input "D:\Videos\my_short.mp4" --output outputs\my_short.analysis.json --rights-basis creator_owned

It extracts:
- media metadata, dimensions, FPS, duration, codec and SHA-256;
- dense opening-window frames plus selected frames across the rest of the clip;
- visual shot-boundary candidates using frame-histogram discontinuities;
- optical-flow motion measurements;
- multilingual timestamped ASR through faster-whisper;
- timestamped on-screen text through PaddleOCR;
- acoustic energy, silence, onset, tempo and estimated beat times;
- a validated JSON report with warnings, provenance and timestamp bounds.

**Important:** cut, motion and beat events are measured candidates, not human-verified labels. The hook window is measured only; Phase 1 does not judge hook quality or predict views. The pipeline does not crawl websites, download platform videos or upload media to a cloud service.

## Hardware recommendation

**Run Phase 1 on your local Windows laptop first.** Your RTX 3050 4 GB is not required for this phase. Start with CPU ASR (`--asr-device cpu`) and CPU OCR to avoid VRAM contention. Colab is unnecessary for this preprocessing/telemetry phase; later rented GPUs will be used for model fine-tuning after the pilot and baselines.

## Installation

### 1. System dependency

Install FFmpeg (including ffprobe) and make sure both executables are on PATH:

    ffmpeg -version
    ffprobe -version

### 2. Python environment (Windows PowerShell)

Python 3.11 is recommended:

    py -3.11 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    pip install -e ".[dev,audio]"

### 3. Reuse your existing VidTrace project (recommended)

VidTrace already contains a maintained PaddleOCR wrapper, faster-whisper transcription, adaptive frame sampling and a common event model. ShortsLM integrates its OCR and ASR adapters when VidTrace is installed; it does not copy VidTrace's implementation.

With both repositories as sibling folders and the ShortsLM environment activated:

    pip install -e "..\VidTrace[whisper,ocr]"

Adjust the relative path if your two repositories are not sibling folders. Alternatively:

    pip install -e ".[ocr]"

PaddlePaddle GPU installation is platform/CUDA-specific. Follow the official PaddlePaddle installation instructions for your platform. Do not install CPU and GPU Paddle builds together.

## Check setup

    shorts-lm doctor
    shorts-lm doctor --json

FFmpeg, ffprobe and OpenCV are required. faster-whisper, PaddleOCR and librosa are optional engines; missing extras are reported as skipped stages rather than silently fabricated results.

## Analyze one permitted video

    shorts-lm analyze --input "D:\Videos\my_short.mp4" --output "outputs\my_short.analysis.json" --rights-basis creator_owned --asr-model small --asr-device cpu --keep-artifacts

Supported rights-basis values:
- `creator_owned`
- `creator_permission`
- `licensed_dataset`
- `approved_research`

This is an explicit user declaration, not an automatic legal check. Model-training permission is a separate field and defaults to false. Use `--training-permitted` only when that permission is explicitly covered by the relevant rights/consent record.

For a quick pipeline smoke run without downloading model weights or initializing OCR:

    shorts-lm analyze --input "D:\Videos\my_short.mp4" --output outputs\smoke.json --rights-basis creator_owned --no-asr --no-ocr

Useful controls: `--max-duration 180`, `--max-file-size-mb 500`, `--max-keyframes 48`, `--max-ocr-frames 12`, `--no-asr`, `--no-ocr`, `--no-audio-analysis`, `--keep-artifacts`.

## Output

- `outputs/my_short.analysis.json` — timestamped telemetry report.
- `outputs/my_short.analysis_frames/` — selected JPEG evidence frames, only when `--keep-artifacts` is supplied.

Extracted WAV audio lives in a temporary directory and is deleted when processing ends. Do not commit videos, audio, generated frames, private analytics, transcripts or training data to GitHub.

## Tests

    ruff check src tests
    pytest -q

For the 25–50-video manual acceptance checklist, setup troubleshooting, GPU experiment and test log template, see [Phase 1 Setup and Test Guide](docs/PHASE_1_TESTING.md). For component contracts and limitations, see [Phase 1 Design](docs/PHASE_1_DESIGN.md).

## Research architecture and next phases

- [Full Global Master Plan](docs/GLOBAL_MASTER_PLAN.md)
- [Architecture Decision Record](docs/ARCHITECTURE.md)
- [Phase 1 Design](docs/PHASE_1_DESIGN.md)
- [Phase 1 Setup and Test Guide](docs/PHASE_1_TESTING.md)
- [Dataset and Labeling](docs/DATASET_AND_LABELING.md)
- [Evaluation Protocol](docs/EVALUATION.md)
- [Data and Compliance](docs/DATA_AND_COMPLIANCE.md)
- [Roadmap](docs/ROADMAP.md)

## License

Apache-2.0. See [LICENSE](LICENSE).


## Phase 2 — 300-video diagnostic pilot

Phase 2 adds a private, rights-aware data workflow around the Phase 1 analyzer. It validates candidate manifests and local media, deduplicates by SHA-256, pseudonymizes creator groups using a private local HMAC salt, and selects a reproducible stratified sample across platform, language, topic, duration, performance tier and speech mode.

It also creates same-creator comparison candidates (only where enough comparable uploads exist), a human-review queue, resumable sequential telemetry processing, per-video processing metrics and quality summaries by stratum. It **does not scrape YouTube/Instagram, download URLs, train a model, or claim causal virality drivers**.

### Quickstart

Create and edit a private candidate manifest:

    shorts-lm pilot template --output data/private/manifest.example.jsonl

Copy the template to `data/private/candidates.jsonl`. Add one JSONL record per locally stored video you are permitted to process. Model-training permission is a separate explicit flag and defaults to false.

Validate rights, file paths, size/duration, media metadata and duplicates:

    shorts-lm pilot validate --manifest data/private/candidates.jsonl --report outputs/pilot/validation.json

Select the 300-video stratified diagnostic sample:

    shorts-lm pilot sample --manifest data/private/candidates.jsonl --output-dir outputs/pilot --target 300 --seed 42 --max-per-creator 5

First process a few videos:

    shorts-lm pilot process --manifest outputs/pilot/selected_manifest.jsonl --output-dir outputs/pilot --limit 10 --asr-model tiny --asr-device cpu

Then process all selected videos:

    shorts-lm pilot process --manifest outputs/pilot/selected_manifest.jsonl --output-dir outputs/pilot --asr-model small --asr-device cpu

Build the report:

    shorts-lm pilot report --pilot-dir outputs/pilot --output outputs/pilot/final_pilot_report.json

The processor is sequential and resumable. Completed reports are reused only if the source checksum, size, rights reference/expiry and pipeline configuration match. Use `--no-resume` to reprocess. If fewer than 300 eligible records exist, the command stops unless `--allow-shortfall` is explicitly supplied; the requested target and shortfall remain in the selection report.

**Keep all files under `data/`, `outputs/` and `.shortslm/` private.** The selected manifest contains local paths and pseudonymous creator IDs; the creator salt must never be published. The CLI measures local wall time and artifact sizes, not cloud bills or human-review cost.

Full instructions:
- [Phase 2 design](docs/PHASE_2_DESIGN.md)
- [Phase 2 setup, commands and manual audit](docs/PHASE_2_TESTING.md)
