# Revised Implementation Roadmap

**Updated:** 21 November 2026  
**Current direction:** open-source, non-official-API discovery and download tools.

## Phase 0 — Local toolchain and private config

- Install Python 3.11, FFmpeg/ffprobe and optional discovery dependencies.
- Establish local private database, acquired-media and reports directories.
- Add a private item-specific rights manifest; do not commit it.
- Confirm search/downloader versions and local Instaloader session handling.

**Exit:** doctor reports ytscrape, yt-dlp, Instaloader, DDGS and FFmpeg availability; local data paths are gitignored.

## Phase 1 — Non-API discovery + SQLite

- YouTube search via ytscrape v2.2+ with the dedicated Shorts-only filter (not generic yt-dlp search).
- YouTube media acquisition remains a separate yt-dlp + FFmpeg step after the rights gate.
- Rotate locale/topic query pools across English, Hindi, Marathi, Kannada, Tamil, Telugu, Bengali, Spanish, Portuguese and Indonesian strata.
- Persist exact query/locale history and default seven-day cooldown in SQLite; use random order by default and an optional --seed for reproducibility.
- Instagram public Reel URL discovery via DDGS, with explicit backends, an 8-second timeout and one fallback engine.
- Resolve Instagram metadata through Instaloader with 12-second per-request timeout, one connection attempt, 15 lookup cap and circuit breaker.
- Enrich only a capped number of new YouTube candidates whose view count or duration is missing.
- Evaluate unseen platform/source IDs before previously known IDs; count an item as new only if its platform/source key was absent before the run.
- Preserve view/play metric provenance and keep Instagram view_count distinct from play_count.
- Persist query usage, provider errors, enrichment statistics, lookup counts and circuit-breaker reasons in the run report.
- Keep threshold default at 1,000,000; unknown metrics do not pass and targets remain best-effort.

**Exit tests:** YouTube provider invokes SearchFilter.SHORTS and parses typed views/duration; two runs with persisted query history rotate to never-used queries; existing IDs are not counted as new; query-history survives DB reopen; YouTube enrichment is capped; Instagram timeout and attempt settings are bounded; repeated Instaloader failures open the circuit; DDGS primary timeout can use one configured fallback; missing/below-threshold/eligible records remain distinct.

See [PHASE_1_DISCOVERY_COVERAGE.md](PHASE_1_DISCOVERY_COVERAGE.md) for detailed testing commands and provider limits.


## Phase 2 — Open-source downloader and media QA

- YouTube: yt-dlp + FFmpeg to MP4.
- Instagram: Instaloader → yt-dlp Instagram extractor → optional gallery-dl.
- Gate every download on an item-specific rights record with retrieval, processing, retention and model-training scopes.
- Record source metadata sidecar and download status.
- Validate file with FFprobe, size and checksum.
- Reject/clean empty/failed files and retry transient failures.
- Use SHA-256 to catch exact cross-platform duplicate bytes.
- Preserve failed jobs for retry; duplicate media are not sent to processing again.

**Exit:** one permitted test asset from each configured source downloads, metadata sidecar validates, FFprobe passes, missing/expired/revoked permission blocks, identical files are deduplicated, interrupted/failed jobs are recoverable.

## Phase 3 — Automated batch video processing

- Feed downloaded permitted MP4 files into the existing Phase 1 analyzer.
- Add sequential batch worker with resumability and per-stage status.
- Run ASR, OCR, frame/shot/motion and audio measurements.
- Produce a manifest and metrics for each asset.
- Validate on 10 assets before 100 and 300.

**Exit:** all stages have explicit complete/partial/failed states and a manual sample audit.

## Phase 4 — Dataset QA and annotation

- Run exact SHA-256 and perceptual near-duplicate checks.
- Verify rights/provenance and media quality.
- Build creator/time-disjoint splits where creator information is legitimately available.
- Review hook, edit taxonomy, OCR/ASR, narrative and evidence claims.
- Save model-ready JSONL/Parquet shards; exclude unresolved rights or quality failures.

**Exit:** first 1K–2K reviewed examples and a locked holdout.

## Phase 5 — Model bake-off and baselines

Compare small pretrained multimodal models using the same permitted data, frame/token budgets and locked holdout. Establish deterministic telemetry and tabular baselines before fine-tuning.

**Exit:** frozen baseline report, chosen model card/license and resource estimate.

## Phase 6 — Cloud fine-tuning

- Build batch shards from examples explicitly permitted for model training.
- Use supported LoRA/DoRA recipe for the selected model.
- Rent cloud GPU for training; checkpoint and cap spending.
- Keep evaluation splits fixed.

**Exit:** repeatable improvement over frozen baseline without major regression by task/language.

## Phase 7 — Local deployment

- Export a supported quantized multimodal checkpoint.
- Benchmark CPU and RTX 3050 4 GB; record peak RAM/VRAM, latency and quality.
- Package CLI/API/UI.

**Exit:** measured local device matrix and model card.

## Phase 8 — Controlled expansion

Expand 1K → 5K → 20K → 50K+ only when discovery yield, upstream reliability, media permissions, deduplication, unit costs and model improvements support it.

## Existing work mapping

- Existing Phase 1 single-video telemetry remains the downstream analyzer.
- Old manual-manifest pilot code is retained as validation/processing support, not the automatic discovery layer.
- PR #5's API-first planning direction is superseded by the user's selected open-source non-API toolchain; this branch updates docs and adds the implementation.
