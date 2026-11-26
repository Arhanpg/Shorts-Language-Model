# ShortsLM Feature Bundle v3.0.0

**Status:** Initial implementation contract. This is a P0 evidence pipeline, not a validated training dataset.

## Purpose

The analyzer retains its legacy root fields for compatibility and additionally emits `analysis.feature_bundle`. This organizes evidence into modality-specific groups, a shared event timeline, a quality report and provenance.

## Bundle structure

- `video_manifest`: probed media facts and source stream availability.
- `transcript`: raw Whisper segments, normalized text, Unicode script hint, detected language, optional language probability, word timestamps and decoding diagnostics.
- `ocr`: all raw detections, normalized text, script hints, confidence, normalized bounding boxes, track IDs, observation intervals and acceptance/review flags.
- `audio_features`: RMS curve, silence ratio, zero-crossing rate, spectral centroid, onset/beat candidates, tempo estimate and clipping ratio.
- `visual_features`: sampled frame evidence, hook-window measurements, cut candidates and optical-flow summaries.
- `temporal_events`: timestamped transcript, OCR tracklet, cut-candidate and beat events.
- `semantic_features`: explicit P1/P2 module status and activation reason.
- `quality_report`: stage states, warnings, accepted/raw candidate counts and human-review recommendation.
- `provenance`: declared rights state, requested ASR/OCR configuration and actual stage engine names.

The legacy `analysis.transcript_segments`, `analysis.ocr_spans`, `analysis.audio`, `analysis.motion` and other root fields remain present. Consumers should migrate to `feature_bundle` when they need the organized contract.

## ASR behavior

1. Prefer the existing VidTrace faster-whisper adapter.
2. If the adapter errors or returns no segments, fall back to direct faster-whisper.
3. Direct faster-whisper uses VAD on the first pass.
4. If the first pass returns zero segments, retry once with `vad_filter=False`.
5. Preserve per-segment `no_speech_prob`, `avg_logprob`, `compression_ratio`, temperature, language probability where available, word timing and the retry marker.

A zero-segment result after retry is **not proof of silence**. It is marked for review; independent VAD or human validation must establish speech absence. Decoding flags and probabilities are review signals, not calibrated transcript correctness.

## OCR behavior

Every detection is retained in `raw_candidates`. Text is NFC-normalized in a separate field; script labels are Unicode-script hints, not language identification. Bounding boxes are normalized relative to sampled frame dimensions. Repeated exact text with overlapping boxes observed within 1.25 seconds may be joined into a video-local text tracklet.

The default acceptance threshold is 0.50 and can be configured. It is **provisional and not calibrated**. Short ambiguous one-character Latin/symbol detections are retained but flagged for review; one-character CJK/Indic tokens are not rejected solely for being one character. No candidate is deleted because of the threshold.

OCR stage status is `complete` only when at least one candidate exists and all returned candidates pass the provisional acceptance rule. Mixed accepted/review candidates are `partial`.

## Audio and visual signals

Audio stores a bounded RMS time-series and additional low-cost signal summaries. Beat, onset and spectral measurements are algorithmic descriptors, not identified songs, genre labels or sound-event classes.

Current visual telemetry remains sampled frames, OpenCV motion and candidate cuts. Motion magnitude does not identify an action or distinguish subject movement from camera movement.

## Semantic-model gates

Person/pose, general action, objects/interactions, scene context, music/sound-event classification, text-speech relation and narrative-structure modules are marked `NOT_YET_PROCESSED` in v3.0.0. Speaker diarization and fine-grained dance labels are deferred P2 work. These fields are not populated with guesses.

A model is activated only after exact checkpoint/code/weight license review, install/runtime benchmarking, a task-specific human-reviewed sample, class-wise quality/abstention rules, and evidence timestamps plus extractor/version provenance.

This follows the accepted Gemini reconciliation: a small local-first P0 stack first, one validated specialist module at a time, and optional VLM reasoning only for selected rights-approved clips.

## Training safeguards

A feature extraction success does not imply a valid training example. Training datasets must require explicit item-level model-training permission, preserve source-native metrics, deduplicate and split by creator/time/audio-template as appropriate, and include human-reviewed labels. Do not treat raw views or likes as causal virality labels. Content understanding and engagement prediction remain separate tasks and datasets.

## Versioning and migration

The Colab notebook reprocesses prior records whose nested bundle is missing or whose bundle version is not `3.0.0`, while leaving current v3 records reusable. Per-video JSON files are updated in the private feature repository; older Git history remains available.
