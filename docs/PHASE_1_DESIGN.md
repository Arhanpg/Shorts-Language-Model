# Existing Local Single-Video Telemetry Analyzer

## Relationship to automated discovery

This document describes the existing local single-video telemetry analyzer. It is not the automated discovery crawler. The separate non-API search and SQLite component is documented in [Phase 1 Discovery Reliability](PHASE_1_DISCOVERY_RELIABILITY.md). Authorized downloaded MP4 files can later be passed into this analyzer.

## Scope

Phase 1 accepts one **local video file that the user is permitted to process** and emits a versioned JSON evidence report. It does not crawl platforms, download videos from links, train a model, predict views or make causal claims.

## Components

1. **Media validation** — local path/extension/size checks, ffprobe metadata, SHA-256 and duration cap.
2. **Frame sampling** — sequential OpenCV decoding, dense opening-window sampling, histogram-based cut candidates and Farneback motion measurements. Retained image memory is capped by max_keyframes.
3. **Audio extraction** — bounded FFmpeg extraction to temporary 16 kHz mono WAV. Temporary audio is deleted after processing.
4. **ASR** — prefers the existing VidTrace faster-whisper implementation; falls back to faster-whisper directly.
5. **OCR** — prefers VidTrace's PaddleOCR wrapper; falls back to PaddleOCR v3 or v2 APIs. OCR defaults to CPU to avoid contention on 4 GB GPUs.
6. **Audio features** — librosa RMS/silence, onset and tempo/beat estimates.
7. **Schemas** — Pydantic-validated report with explicit rights declaration and timestamp bounds.

## Evidence semantics

- Cut candidates are image-histogram discontinuities. They are **not** guaranteed to be editor-authored cuts; abrupt brightness changes and flash effects may also trigger them.
- Motion samples are mean optical-flow magnitudes between sampled frames. Camera movement, subject movement and edits are not yet disentangled.
- Audio beat times are estimated by librosa. They are not verified music beats or a song-identification result.
- OCR/ASR confidence is reported only when the engine supplies it; absent confidence is left null rather than fabricated.
- The hook window is a measured 0–3 second interval. Phase 1 does not rate hook quality.

## Reuse of VidTrace

The optional VidTrace dependency pins the inspected VidTrace source revision. The ASR and OCR adapters use its existing WhisperTranscriber and PaddleOCREngine APIs when installed. ShortsLM does not copy VidTrace's implementation. The pipeline can also use standalone faster-whisper and PaddleOCR packages.

## Resource behavior

- CPU is the default ASR device; OCR is initialized with GPU preference off.
- Only a bounded set of resized keyframes is retained in memory.
- FFmpeg audio is written to a temporary directory and deleted after extraction.
- Default file cap is 500 MB and 180 seconds.
- GPU training and model inference are outside Phase 1.

## Known limitations

- Optical-flow and histogram cut candidates need a labeled 25–50-video audit before thresholds can be considered accurate.
- PaddleOCR package versions, language packs and supported constructor arguments vary by platform.
- ASR downloads its selected model on first run. Internet access is needed only for the initial model download unless weights are already cached.
- Beat/tempo estimates on short, speech-heavy clips may be unreliable; warnings and empty output are valid results.
- The code has been exercised in this environment with synthetic audio/video fixtures, not on the user's Windows laptop or the complete 25–50 clip acceptance set.
