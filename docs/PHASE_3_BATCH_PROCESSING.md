# Phase 3 — Simple Batch Processing with VidTrace

**Goal:** turn discovered 1M+ YouTube Shorts and Instagram Reels into local video, transcript, OCR and analysis artifacts.

## What the command does

1. Reads eligible candidates from the existing SQLite discovery database.
2. Selects a balanced batch from YouTube and Instagram inventory, then downloads a missing MP4 using the current platform downloader.
3. Validates the MP4 with FFprobe and calculates SHA-256.
4. Skips exact duplicate media already in the inventory.
5. Runs the existing multimodal analyzer, preferring CUDA for the pinned VidTrace Whisper and PaddleOCR adapters.
6. Saves the transcript, OCR, analysis report and a JSONL index.
7. Keeps successful downloads so a later ASR/OCR retry does not download the MP4 again.

## Install

```powershell
pip install -e ".[dev,discovery,legacy-discovery,audio,vidtrace]" --upgrade
shorts-lm doctor
```

## Run

Start with ten videos:

```powershell
shorts-lm discover process --platform all --limit 10 --min-metric 1000000 --asr-model small --device cuda
```

Useful options include `--database`, `--download-dir`, `--artifact-dir`, `--dataset-manifest`, `--language`, `--max-duration`, `--max-file-size-mb`, `--max-keyframes` and `--max-ocr-frames`.

## Per-video outputs

```text
data/private/processed/<platform>/<source_id>/
    asset.json
    analysis.json
    transcript.json
    transcript.md
    ocr.json
    ocr.md
```

MP4 files are stored under `data/private/acquired/`. The JSONL index defaults to `outputs/dataset/processed-videos.jsonl` and contains source metadata, platform-native views/plays metric, media checksum, artifact paths, transcript/OCR counts and engine names.

## Resumability

- The SQLite database stores per-video download and processing status.
- If a download succeeds but analysis fails, a later run retries analysis from the same MP4.
- A failed or corrupt download is marked retryable.
- Exact duplicate files are skipped using SHA-256.
- Completed videos are not processed again.

The batch worker is sequential and bounded. With both platforms present, it alternates YouTube and Instagram candidates within the total limit. The command only processes candidates already saved in SQLite; run `shorts-lm discover graph-run --platform all ...` first to discover candidates. Validate 10 videos first, then 100 and 300. Review transcript/OCR accuracy and disk usage before larger runs.

CUDA is preferred by default for Whisper and PaddleOCR. Actual devices are included in the ASR/OCR engine names saved with each record. If the Windows CUDA/cuDNN or GPU PaddlePaddle runtime is missing, an adapter may fall back to CPU; follow [GPU setup](GPU_SETUP_WINDOWS.md) and verify the saved engine metadata before assuming the GPU was used.

## Long-term corpus goal

The project target remains 5–10 million YouTube Shorts and 5–10 million Instagram Reels with at least 1M platform-native views/plays. This is a long-term target, not a claim that discovery currently returns that number of unique videos. Track unique candidates, qualifying metrics, successful downloads, processed videos, duplicate counts, language coverage and processing cost.

## Next phase

Phase 4 will focus on dataset cleanup, perceptual near-duplicate detection, transcript/OCR review, creator/time grouping and model-ready dataset splits.
