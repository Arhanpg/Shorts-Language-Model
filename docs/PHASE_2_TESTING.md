# Phase 2 — Download and Media Validation

## Environment

Use Windows PowerShell. Install Python 3.11 and FFmpeg (ffmpeg.exe and ffprobe.exe on PATH). The RTX 3050 accelerates Whisper and PaddleOCR; discovery, downloading, FFprobe and database operations remain CPU-oriented. Follow [Windows RTX 3050 GPU Setup](GPU_SETUP_WINDOWS.md) once before processing.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,discovery,legacy-discovery,audio,vidtrace]"
pip install -e ".[instagram-fallback]"
shorts-lm doctor
```

The optional gallery-dl fallback may be skipped.

## Download candidates

Discover candidates:

```powershell
shorts-lm discover graph-run --platform all --target-new 100 --min-metric 1000000
```

Download the current eligible inventory:

```powershell
shorts-lm discover download --limit 25 --min-metric 1000000 --output-dir data/private/acquired
```

The downloader writes an MP4 and a small metadata sidecar. YouTube uses yt-dlp; Instagram tries Instaloader, then yt-dlp and the optional gallery-dl fallback.

## Batch processing with VidTrace

```powershell
shorts-lm discover process --platform all --limit 10 --min-metric 1000000 --asr-model small --device cuda
```

The command reads both platforms from the local SQLite inventory, alternates YouTube and Instagram candidates when both are available, downloads missing MP4s, checks them with FFprobe, deduplicates exact file hashes, and runs CUDA-preferred ASR/OCR. It writes per-video analysis, transcript, OCR and asset JSON files under:

```text
data/private/processed/<platform>/<source_id>/
    asset.json
    analysis.json
    transcript.json
    transcript.md
    ocr.json
    ocr.md
```

The JSONL output defaults to `outputs/dataset/processed-videos.jsonl`.

## Validation checklist

1. Discover a small batch of YouTube Shorts and Instagram Reels.
2. Download ten candidates and check that MP4 files are non-empty.
3. Confirm FFprobe metadata and SHA-256 are recorded.
4. Check that exact duplicate MP4 bytes are not processed twice.
5. Compare transcript language and timestamps against the source audio.
6. Compare OCR text and timestamps against the source video.
7. Simulate an analysis failure and confirm a retry uses the existing MP4.
8. Confirm an invalid or unavailable media download remains retryable.
9. Confirm local databases, sessions, media files and private outputs remain gitignored.

Increase the batch from 10 to 100 to 300 only after the initial sample is working correctly. The processing command does not discover new videos; populate the inventory first with `shorts-lm discover graph-run --platform all ...`.

## Commands

Run lint and tests:

```powershell
ruff check src tests
pytest -q
```
