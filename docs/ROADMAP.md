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

- YouTube search via ytscrape v2.2+ with the dedicated Shorts-only filter, first-page-only consumption and no lazy pagination.
- YouTube media acquisition remains a separate yt-dlp + FFmpeg step after the rights gate.
- Rotate locale/topic query pools across English, Hindi, Marathi, Kannada, Tamil, Telugu, Bengali, Spanish, Portuguese and Indonesian strata.
- Persist exact query/locale history and default seven-day cooldown in SQLite; use random order by default and an optional --seed for reproducibility.
- Instagram public Reel URL discovery via DDGS, with explicit backends, an 8-second timeout and one fallback engine.
- Resolve Instagram metadata through Instaloader with 12-second per-request timeout, one connection attempt, 40 lookup cap and circuit breaker.
- Enrich only a capped number of new YouTube candidates whose view count or duration is missing; optional enrichment has a separate 20-second budget.
- Evaluate unseen platform/source IDs before previously known IDs; count an item as new only if its platform/source key was absent before the run.
- Preserve view/play metric provenance and keep Instagram view_count distinct from play_count.
- Persist query usage, provider errors, enrichment statistics, lookup counts and circuit-breaker reasons in the run report. Show progress and enforce a three-minute default overall runtime budget, short YouTube timeouts and zero retries.
- Keep threshold default at 1,000,000; unknown metrics do not pass and targets remain best-effort.

**Exit tests:** YouTube provider invokes SearchFilter.SHORTS and parses typed views/duration; two runs with persisted query history rotate to never-used queries; existing IDs are not counted as new; query-history survives DB reopen; YouTube enrichment is capped; Instagram timeout and attempt settings are bounded and respected; repeated Instaloader failures open the circuit; DDGS primary timeout can use one configured fallback; combined runs schedule both selected platform stages when the shared deadline permits; per-platform reports distinguish not-selected, not-started, completed and circuit-open states; missing/below-threshold/eligible records remain distinct.

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

**Implementation added in PR: phase3/batch-acquisition-vidtrace-dataset. Real Windows media validation remains an acceptance gate.**

- Add a resumable, bounded batch worker over confirmed, eligible Shorts/Reels in the discovery SQLite inventory.
- Refresh and enforce item-specific retrieval, analysis, temporary-processing, derived-artifact-retention and model-training grants from the current private rights manifest.
- Reuse the existing downloader and Phase 1 analyzer; prefer the pinned VidTrace WhisperTranscriber and PaddleOCREngine through the existing ASR/OCR adapters.
- Write per-video analysis JSON, timestamped transcript JSON/Markdown, OCR JSON/Markdown, asset provenance and a JSONL processing manifest.
- Preserve native YouTube views and Instagram views/plays metric type/source. Exclude rounded UI estimates by default; an explicit research-only option keeps estimates marked and review-required.
- Preserve a successful MP4 and its SHA-256 after analysis failure so the next run retries ASR/OCR without downloading again.
- Stream the output manifest, keep the worker sequential and bounded, and recheck current rights before export.
- Validate on 10 assets before 100 and 300; manually audit transcript/OCR quality before increasing the batch size.

**Exit:** rights expiry/revocation tests pass; download failures and analysis retries behave independently; exact duplicates are not processed twice; artifact timestamps and media hashes validate; JSONL records remain review-required; a manual sample audit passes; CI passes.

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

The long-term research objective is 5–10 million YouTube Shorts plus 5–10 million Instagram Reels at the 1M+ platform-native metric threshold. Expand through measured gates (300 → 1K → 5K → 20K → 50K → 100K → larger batches) only when unique discovery yield, explicit media/training permissions, provider access, processing quality, duplicate control, retention constraints, storage and unit costs support the next scale step. This target is aspirational, not a promise that public discovery or rights availability can supply that many items.

## Existing work mapping

- Existing Phase 1 single-video telemetry remains the downstream analyzer.
- Old manual-manifest pilot code is retained as validation/processing support, not the automatic discovery layer.
- PR #5's API-first planning direction is superseded by the user's selected open-source non-API toolchain; this branch updates docs and adds the implementation.


### Phase 1.5 — Multi-source discovery recall and strict eligibility

- Replace private ytscrape buffer access with bounded public pagination.
- Add yt-dlp metadata-only hashtag Shorts shelf discovery.
- Expand only channels discovered from Shorts surfaces into their Shorts tabs.
- Prioritize historical productive query/locale strategies after cooldown while preserving exploration.
- Add optional local Instaloader interactive-login/session validation.
- Add yt-dlp metadata-only fallback after non-access-related Instaloader parsing failures.
- Reclassify legacy eligible rows whose format was not confirmed.
- Enforce confirmed Shorts/Reel format and preserve platform-native metric definitions. Exact numeric metrics are required by default for the processing/training-candidate queue; rounded Instagram display counts remain explicit estimates and are excluded unless exploratory processing is opted into.

**Exit:** deterministic tests pass; GitHub Actions passes; Windows run shows per-surface yields, confirmed-format counts, metric coverage and separate Instagram session/fallback diagnostics.
