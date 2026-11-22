# Phase 3 — Resumable Batch Processing with VidTrace

**Status:** implementation added; Windows validation against real, rights-cleared media is still required.  
**Purpose:** turn the existing discovered-media inventory into a reproducible multimodal artifact corpus for later ShortsLM training.

## 1. Scope and non-goals

Phase 3 consumes candidates already stored by ShortsLM discovery. It does not implement another crawler, speech recognizer or OCR engine. It reuses:

- the existing item-specific acquisition rights manifest and download adapters;
- the existing Phase 1 analyze_video pipeline;
- ShortsLM's telemetry.asr adapter, which prefers the pinned VidTrace WhisperTranscriber;
- ShortsLM's telemetry.ocr adapter, which prefers the pinned VidTrace PaddleOCREngine;
- the existing local SQLite discovery database.

This phase produces per-video media, analysis, transcript, OCR and provenance artifacts. It does not fine-tune model weights or infer causal explanations for virality.

## 2. End-to-end flow

~~~text
Discovery SQLite
    |
    | confirmed Shorts/Reel + platform-native metric >= threshold
    v
Current item-specific rights manifest
    |
    | retrieval + analysis + temporary processing
    | + derived-artifact retention + model-training grants
    v
Authorized downloader (yt-dlp / Instaloader / configured fallback)
    |
    v
FFprobe validation + SHA-256 exact-file deduplication
    |
    v
Existing Phase 1 analyzer
    |-- frame sampling, cut candidates, motion
    |-- VidTrace Whisper ASR (language + timestamped segments)
    |-- VidTrace PaddleOCR (timestamped text spans + bounding boxes)
    |-- audio measurements
    v
Per-item artifacts + SQLite processing state
    |
    v
Review-required JSONL processing manifest
    |
    v
Future Phase 4 QA / annotation / deduplication / split creation
    |
    v
Future model bake-off and fine-tuning
~~~

## 3. Rights and eligibility gates

Each media item must have a matching row in the private JSONL rights manifest keyed by (platform, source_id). The current row must grant:

- media retrieval;
- media analysis;
- temporary processing;
- derived-artifact retention;
- model training.

Expired, revoked, incomplete or absent grants are not selected for processing. Replacing the manifest refreshes the SQLite rights index, so removed or revoked grants also remove an item from the next exported training-candidate manifest. This is a local attestation/evidence pointer, not an independent legal validation of the underlying permission.

The queue requires a confirmed Shorts/Reels format and the configured minimum metric. YouTube views and Instagram-native views/plays stay separate and retain their metric kind and source. Exact metrics are the default for processing. A rounded Instagram UI label (for example, 1.2M) can be opted into for exploratory transcript/OCR processing, but is marked metric_is_estimate=true and remains review-required. It is not an exact engagement label.

## 4. CLI

Install the existing tools and the pinned VidTrace integration:

~~~powershell
pip install -e ".[dev,discovery,legacy-discovery,audio,vidtrace]" --upgrade
shorts-lm doctor
~~~

Start with ten authorized assets:

~~~powershell
shorts-lm discover process --rights-manifest data/private/rights.jsonl --limit 10 --min-metric 1000000 --asr-model small --asr-device cpu
~~~

Once the sample has been reviewed, increase limit to 100 and then 300. Do not use allow-estimated-metrics for the exact-metric training corpus. The option exists only for exploratory processing of estimate-backed items and is explicitly recorded in the run summary.

Useful controls include database, download-dir, artifact-dir, dataset-manifest, language, max-duration, max-file-size-mb, max-keyframes and max-ocr-frames. The 4 GB RTX 3050 is not required for discovery or downloading; begin with CPU ASR/OCR. VidTrace's ASR wrapper can try CUDA when explicitly selected and fall back to CPU if inference fails.

## 5. Per-video outputs

For each item, artifacts are stored under:

~~~text
data/private/processed/<platform>/<source_id>/
    asset.json
    analysis.json
    transcript.json
    transcript.md
    ocr.json
    ocr.md
    analysis_frames/                 # only with --keep-frame-artifacts
~~~

The media MP4 and its private metadata/rights sidecar are stored under the acquisition directory. The JSONL processing manifest stores references to those paths and the SHA-256 checksum, plus the platform-native metric snapshot, rights evidence reference, extractor engines, transcript/OCR counts, language and quality flags.

The manifest is deliberately not a training-ready manifest. Every exported record contains training_ready=false, review.status="review_required" and review.training_approved=false. Phase 4 must add explicit rights/content/transcript review and a separate approval step before examples can enter a training shard.

## 6. Resumability and failure behaviour

- Source identity and processing state are stored in SQLite; processing attempts and the latest error are retained.
- A successfully downloaded MP4 remains marked downloaded even when ASR/OCR or report generation fails.
- A later batch retries analysis from the existing MP4 instead of downloading it again.
- An acquisition failure remains a retryable download failure.
- Exact byte duplicates across platform/source IDs are marked duplicate_media; a newly downloaded redundant copy is removed.
- A missing, revoked or expired rights entry is excluded from processing and from the current training-candidate manifest.
- A stale/corrupted local media file that does not match its stored SHA-256 is not silently accepted.

The worker is intentionally sequential and bounded. It is a correctness-first local processing stage, not yet a distributed multi-million-item scheduler.

## 7. Validation gates

Run:

~~~powershell
ruff check src tests
pytest -q
~~~

Then manually validate:

1. One creator-owned or creator-authorized YouTube Short and one authorized Instagram Reel.
2. Missing, expired, revoked and incomplete permission records.
3. Exact 1M+ and below-threshold metric cases.
4. Rounded Instagram metrics excluded by default and clearly tagged when opted in.
5. Downloaded media FFprobe metadata, SHA-256 and cross-platform exact duplicates.
6. Transcript language, segment timestamps and content against the source audio.
7. OCR text, timestamps, bounding boxes and frame samples against the source video.
8. At least one analysis failure followed by a successful retry without a second media download.
9. The generated JSONL manifest remains review-required and is removed from export when a grant is revoked.
10. No MP4, SQLite database, session, cookie, private rights manifest, raw transcript or private artifact is committed.

## 8. Long-term corpus objective

The research ambition is a corpus of **5–10 million YouTube Shorts and 5–10 million Instagram Reels**, each meeting the project's 1M+ platform-native discovery threshold. This is a long-term target, not a guarantee that public discovery can find that many unique items or that the rights needed for retrieval and model training will be available.

Scale in stages and report separate counts for discovered IDs, exact-metric eligible IDs, estimate-backed candidates, permission-cleared media, downloaded assets, successfully processed assets, reviewed examples and training-approved examples. The corpus must preserve creator/time grouping, repost/duplicate relationships, metric observation time and retention constraints. Training should begin only after Phase 4 has established acceptable data quality and a leakage-resistant evaluation split.

## 9. Next phase

Phase 4 is dataset QA and annotation: perceptual near-duplicate detection, language/category coverage, rights and provenance review, ASR/OCR audits, creator/time-disjoint splits, annotation and a locked holdout. It converts the processing manifest into approved training shards; Phase 3 does not do that approval automatically.
