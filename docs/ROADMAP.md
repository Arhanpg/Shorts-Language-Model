# ShortsLM Implementation Roadmap

**Updated:** 24 November 2026  
**Direction:** minimal local-first multimodal telemetry, with optional cloud reasoning and staged training.

This roadmap supersedes model shopping lists in older drafts. Existing discovery/acquisition code, SQLite state, rights gates and VidTrace adapters should be reused unless a source-level audit proves they need replacement.

## Phase 0 — source and environment audit

- Map the current CLI, downloader, analyzer, VidTrace adapters, schemas and artifact paths.
- Record Python/runtime/dependency versions and actual local CUDA availability.
- Audit exact code/weight/dataset licenses before adding any new model.
- Preserve existing non-API discovery policy and rights checks.
- Document optional environment variables; do not add mandatory external tokens.

**Exit:** implementation map and dependency/license ledger.

## Phase 1 — P0 timeline and media manifest

- FFprobe media facts, duration, resolution, FPS/VFR, streams and time-base.
- FFmpeg decode-once workflow with PTS-preserving frame/audio extraction.
- Canonical timestamp and missingness contract from [FEATURE_EXTRACTION_SPEC.md](FEATURE_EXTRACTION_SPEC.md).
- Persist provenance and idempotent stage status.

**Exit:** 10-video smoke test with valid schema, correct timestamps and recoverable failures.

## Phase 2 — P0 speech, OCR, audio and temporal baseline

- Reuse current VAD/faster-whisper and PaddleOCR adapters.
- Benchmark current ASR vs one large-v3-turbo INT8 candidate; select one.
- Evaluate Hindi, English, Hinglish, additional Indic languages, code-switching, music-heavy and no-speech clips.
- Add inexpensive RMS/loudness, onset/spectral flux and beat/tempo candidates.
- Add/validate shot boundaries, adaptive frames and OpenCV motion.
- Report transcript/OCR/audio/shot metrics and stage runtime.

**Exit:** 100–300 authorized videos audited; selected defaults documented; no unsupported quality claims.

## Phase 3 — P1 action, pose, object and editing modules

- Evaluate one pose model and one object detector, one at a time.
- Add anonymous video-local person tracks, general action intervals and HOI candidates.
- Add editing taxonomy and text/speech relation.
- Add sound-event model only if inexpensive audio features are insufficient.
- Fine-grained dance labels require human-reviewed class definitions and enough examples.

**Exit:** every added module improves held-out metrics or is removed/deferred.

## Phase 4 — dataset QA and annotation

- Verify item-specific rights for each operation.
- Exact SHA-256 and perceptual duplicate/repost/template grouping.
- Sample ordinary and high-performing controls; report actual language/topic/creator coverage.
- Annotate temporal actions, hooks, edits, audio, transcript/OCR quality and grounded summaries.
- Keep machine draft labels separate from human-corrected labels.
- Build creator-disjoint and forward-time splits; keep gold holdout locked.

**Exit:** first reviewed gold set; quality and missingness report.

## Phase 5 — frozen model baselines

- Transcript-only, OCR-only, audio-only, visual-only, metadata-only and combined baselines.
- CatBoost/LightGBM for structured prediction.
- One compact VLM candidate vs optional Gemini API on the same clip/frame budget.
- Record licenses, model versions, resource use and cost.

**Exit:** reproducible baseline report and model selection ADR.

## Phase 6 — task-specific training

- Train compact temporal fusion head with confidence masks and PTS-aware encoding.
- Train separate CatBoost engagement estimator.
- Fine-tune a pretrained VLM only if frozen baseline and gold set show a meaningful gap.
- Use rented GPU, checkpointing and spend cap; do not train 2B/4B multimodal models on RTX 3050 4 GB.

**Exit:** held-out gains, subgroup metrics, ablations and calibration.

## Phase 7 — optional reasoning and deployment

- Enable one optional Gemini API key only for selected rights-approved clips if cost/quality gate passes.
- Optional Sarvam Saaras API only if Indic ASR benchmark demonstrates need; not required alongside Gemini.
- Quantize only supported model paths; test actual projector/video input compatibility.
- Benchmark local CPU/GPU latency, peak memory and quality delta.

**Exit:** evidence-grounded report, model card, deployment matrix and reproducible setup.

## Phase 8 — scale

Progress only after measured quality, rights-cleared supply, unique yield, storage and cost:
10 → 30 → 100 → 300 → 1K → 2K → 5K → 20K → 50K → 100K+.

The long-term multi-million URL goal is aspirational. Discovered URLs are not equivalent to permitted, downloadable, analyzable or trainable assets.

## Required experiment report for every phase

Record:
- commit SHA, environment and dependency lock;
- source/rights manifest hash (private evidence remains private);
- input sample manifest hash and split;
- model/checkpoint/license/version and configuration;
- runtime per stage, peak VRAM/RAM and actual device;
- quality metrics by language/script/content subgroup;
- failure/retry counts and missingness distribution;
- cost per processed clip and per accepted example;
- decision: keep, revise or remove.

## Minimal setup policy

Baseline extraction should require no new API token. Optional services are limited to one Gemini API key for multimodal reasoning and, only if justified, one Sarvam API key for Indic ASR. Do not require gated Hugging Face access, multiple ASR vendors or multiple model dashboards.
