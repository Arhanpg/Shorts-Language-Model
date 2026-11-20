# Phase 1 — Setup and Test Guide

## Where to run it

Run Phase 1 on your **local ASUS TUF laptop first**. This phase is media extraction and telemetry, not model training. Use CPU for the first run; your RTX 3050 4 GB is not required. Colab is unnecessary for the local-media workflow, and uploading source clips to a notebook adds friction. A rented GPU is also unnecessary at this stage.

## Windows PowerShell setup

Install FFmpeg (which includes ffprobe) and ensure both commands are on PATH. Open a new PowerShell window and confirm:

    ffmpeg -version
    ffprobe -version

From the repository root:

    py -3.11 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    pip install -e ".[dev,audio]"

Install OCR/ASR engines. Preferred route reuses your existing VidTrace checkout in the same virtual environment:

    # From the Shorts-Language-Model repository root, if VidTrace is a sibling folder
    pip install -e "..\VidTrace[whisper,ocr]"

Adjust the relative path if your repositories are stored elsewhere. Alternatively install PaddleOCR directly:

    pip install -e ".[ocr]"

The VidTrace route is preferred because it contains maintained OCR result normalization and Whisper CPU/CUDA fallback. PaddlePaddle's GPU build is platform/CUDA-specific. Do not install CPU and GPU Paddle builds together; follow PaddlePaddle's official installation selector if you later test GPU OCR.

If PowerShell blocks virtual-environment activation, run Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass in that terminal only, then activate again.

## Linux / WSL setup

Install FFmpeg using your distribution's package manager, then:

    python3.11 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    pip install -e ".[dev,audio]"
    # Optional reuse of a sibling VidTrace checkout:
    pip install -e "../VidTrace[whisper,ocr]"

## Check dependencies

    shorts-lm doctor
    shorts-lm doctor --json

Required: FFmpeg, ffprobe and OpenCV. Recommended for full telemetry: faster-whisper and PaddleOCR (preferably through VidTrace), plus librosa.

## Run one video

Use a clip you own or have explicit permission to process. Phase 1 accepts local files only; it does not download links.

    shorts-lm analyze --input "D:\Videos\my_short.mp4" --output "outputs\my_short.analysis.json" --rights-basis creator_owned --asr-model small --asr-device cpu --keep-artifacts

Other rights-basis values: creator_permission, licensed_dataset, approved_research. This is a user declaration; it is not a legal verification. Model-training permission is separate and defaults to false. Use --training-permitted only when the relevant permission expressly covers training.

For a first smoke run without downloading ASR weights or initializing OCR:

    shorts-lm analyze --input "D:\Videos\my_short.mp4" --output outputs\smoke.json --rights-basis creator_owned --no-asr --no-ocr

To skip one optional lane, use --no-asr, --no-ocr or --no-audio-analysis.

## What should be generated

- outputs/my_short.analysis.json: validated report with video metadata, rights declaration, opening-window measurements, frame timestamps, cut candidates, motion metrics, ASR transcript, OCR spans, audio features, stage statuses and warnings.
- outputs/my_short.analysis_frames/: selected JPEG evidence frames, only with --keep-artifacts.

Extracted WAV audio is temporary and deleted after processing. Do not commit source videos/audio, generated frames, private analytics, transcripts or training data to GitHub.

## Test checklist: 25–50 clips

Start with 10 clips, fix environment issues, then expand to 25–50. Include:
1. rapid-cut edit with jump cuts and flashes;
2. cricket/sports edit with music only;
3. Hindi speech/voiceover;
4. Hinglish speech and English on-screen text;
5. English talking-head clip;
6. silent visual sequence;
7. caption-heavy tutorial;
8. meme/reaction with overlays;
9. slow cinematic footage with few edits;
10. end-loop/repeated opening frame.

For each clip check: duration/resolution/aspect ratio are correct; opening frames cover 0–3 seconds; obvious cuts appear as candidates; motion rises during action; OCR matches legible on-screen text; ASR language/transcript are plausible; no-audio clips complete without error; timestamps stay within duration; warnings identify missing optional dependencies.

Record in a test sheet: clip ID, rights basis, language, category, duration, style, ASR status, OCR status, manually verified cut candidates, transcript correctness, OCR correctness, runtime, failures/warnings and notes. Do not publish source clips or private metrics.

## Automated checks

    ruff check src tests
    pytest -q
    shorts-lm doctor --json

## GPU experiment (only after CPU baseline)

First measure CPU runtime. Then test a short clip with --asr-device cuda only if nvidia-smi works and your CTranslate2 installation supports CUDA. Compare transcript quality, wall time and VRAM with CPU. Keep OCR on CPU; do not load Whisper and PaddleOCR concurrently on a 4 GB GPU.

## Troubleshooting

- ffprobe not found: install FFmpeg and reopen the terminal so PATH refreshes.
- OpenCV could not open: verify the file plays locally; remux to H.264 MP4 with FFmpeg.
- faster-whisper is not installed: install the audio extra or VidTrace's whisper extra.
- First ASR run downloads a model: keep internet enabled for the first fetch; later runs can use the local cache.
- PaddleOCR fails on constructor/version: use the pinned VidTrace extra; capture the full error and installed version before changing dependencies.
- CUDA error: return to --asr-device cpu; Phase 1 does not require GPU.
