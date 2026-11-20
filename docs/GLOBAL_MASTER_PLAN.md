# Shorts Language Model — Global Master Plan

> **Revised direction — 21 November 2026:** build an automated, provider-based short-form video discovery and intelligence system. It should discover eligible candidates, deduplicate them in a local database, retrieve media through an authorized delivery route, extract audiovisual evidence, and fine-tune a compact multimodal model after dataset and baseline gates pass.
>
> **Critical distinction:** a source URL, public view count, metadata API response, permission to download, and permission to train are different things. The project can automate discovery; it cannot assume every public YouTube Short or Instagram Reel can be downloaded.

## 1. Product definition

The target product is an automated short-form video intelligence factory. On each scheduled or manual run, it should:

1. Discover candidates through official APIs, approved research interfaces or licensed provider feeds.
2. Filter by a configurable threshold (default: 1,000,000 observed views/plays).
3. Prevent repeated discovery using a local SQLite inventory, subject to each source's retention policy.
4. Store permitted title/caption, description, tags/hashtags, duration, publication time and engagement snapshots.
5. Acquire media automatically only where a platform/provider/creator route explicitly permits delivery and model training.
6. Extract transcript, OCR, scenes, cuts, effects candidates, motion and audio evidence.
7. Produce timestamp-grounded reports and human-auditable training examples.
8. Evaluate and fine-tune a pretrained compact multimodal model in cloud batches.
9. Ship a quantized model and local analysis application where actual hardware measurements support it.

The project owner should not have to paste URLs or manually download videos during a normal supported discovery run. Initial API credentials, institutional approval, creator agreements or a platform partnership may still be prerequisites. If no authorized media source exists for a platform, it remains metadata-only; the system must not silently fall back to scraping.

## 2. Requirements and honest limits

| Requirement | Design |
|---|---|
| No manual link pasting | Provider query planners search configured language/region/topic/time strata |
| 100–200 new unique candidates per run | Configurable target; partial result if quota/source/threshold prevents it |
| Filter videos above 1M views | Use a current, timestamped provider metric with its definition |
| Avoid duplicates | SQLite source keys plus file/perceptual fingerprints where retention and rights permit |
| YouTube Shorts and Instagram Reels | Separate provider adapters and metric semantics |
| Automatic media delivery | Only through a documented, authorized provider |
| Title, description, hashtags | Store provider-native fields; Instagram may expose caption rather than a separate title |
| Transcript/OCR/visual effects | Run existing telemetry after authorized media delivery |
| Training | Build/version/QA a dataset, then fine-tune in batches; do not train once per incoming file |
| RTX 3050 4 GB | Development, CPU preprocessing and quantized inference experiments; cloud for VLM training |

A randomized browser crawl is not a statistically uniform sample. Search results are ranked and query-dependent. Randomize query order across declared strata and report the sampling frame; do not claim unbiased platform-wide sampling.

## 3. Platform access reality

### YouTube

The YouTube Data API v3 can search videos and retrieve metadata/statistics. Current published default quota documentation describes a separate 100-call/day `search.list` bucket and 10,000 units/day for other standard methods. `videos.list` returns title, description, tags, duration and view statistics. Search can produce candidate IDs, but common public API fields do not reliably confirm every result is a Short.

Shorts classification must respect YouTube's current rule: for standard channels, square or vertical videos uploaded on/after 15 October 2024 and up to three minutes are categorized as Shorts. Duration alone is not sufficient. Store format status as `confirmed`, `candidate` or `unknown`.

YouTube developer policies prohibit downloading/caching audiovisual copies without prior written approval and prohibit scraping YouTube applications. Non-authorized API data generally has a 30-day storage/refresh limit. As of 1 June 2026, an amended policy offers audited developers a longer retention path for specified statistical data and approved derived metrics when the required amendment is accepted for an approved analytics use case. Other fields, including titles, creator names and descriptions, remain subject to refresh/deletion requirements.

YouTube also offers a creator/rightsholder third-party AI-training opt-in. It is off by default. Applicable rights holders must opt in, creators select approved third-party companies, and companies may apply to be listed. YouTube may share eligible videos with selected companies. This is the first platform-native route to investigate for automatic YouTube training media, but it requires acceptance and documented delivery terms. It is not permission to use yt-dlp on arbitrary videos.

### Instagram / Meta

Instagram Graph API access is limited to eligible professional Business/Creator accounts and required app permissions. Business Discovery can inspect eligible public professional accounts whose usernames are known. Reel `view_count` is documented through Business Discovery; it may include paid or cross-posted activity. The standard API is not a global index of every public Reel. Hashtag search is narrower, and its responses must not be assumed to contain the Business Discovery-only view-count field. A media URL can be omitted for copyrighted or flagged content.

Meta Content Library/API is controlled research access for eligible academic or not-for-profit research institutions. Its API operates in a secure research environment, and Meta says API data cannot be downloaded from that environment. An approved web-interface downloadable subset has separate conditions; it is not a universal MP4 training feed.

Therefore, Instagram discovery can be partially automated through known eligible professional accounts or institutional research access. A fully automatic arbitrary-public-Reel-to-local-MP4 pipeline is not available through the standard Graph API.

### Acquisition consequence

Support three independent states: `discovered_metadata`, `authorized_media_available` and `authorized_for_model_training`. A video can pass the 1M filter and still remain metadata-only. That is an expected source outcome, not a pipeline error.

See [Automated Discovery and Rights-Gated Media Acquisition](AUTOMATED_DISCOVERY_AND_ACQUISITION.md) and [Data and Compliance](DATA_AND_COMPLIANCE.md).

## 4. Revised end-to-end architecture

```text
Scheduled discovery run
       |
       v
Provider query planner
       |
       +--> YouTube Data API
       +--> Instagram Business Discovery
       +--> Meta research / licensed provider
       +--> Creator-authorized source
       |
       v
Provider response normalization
       |
       v
1M threshold + short-format confidence
       |
       v
SQLite inventory + retention-aware deduplication
       |
       v
Rights and delivery capability gate
       |                            |
authorized media                 not authorized
       |                            |
       v                            v
Approved media delivery        Metadata-only / deferred
       |
       v
Private media staging + checksum
       |
       v
Phase 1 telemetry: ASR/OCR/shots/motion/audio
       |
       v
Evidence store + human review + dataset QA
       |
       v
Frozen model baseline -> cloud batch LoRA fine-tuning
       |
       v
Evaluation -> quantized local model + report application
```

### Core subsystems

1. **Discovery Agent:** query planner, source connectors, quota/rate-limit manager, candidate normalizer and 1M+ filter.
2. **Local Inventory:** SQLite for discovery runs, source items, metadata snapshots, rights, media assets, jobs and provider state.
3. **Rights Gate:** independent scopes for metadata, media retrieval, analysis, temporary processing, derived retention, training and redistribution.
4. **Media Delivery:** pluggable licensed/creator/platform-approved providers; no universal public URL downloader.
5. **Telemetry Engine:** reuse existing ShortsLM Phase 1 analyzer and audited VidTrace adapters.
6. **Dataset Factory:** checksums, perceptual dedup, annotations, split control, sampling weights, human review and quality reports.
7. **Model Factory:** frozen baselines, ranking model and VLM SFT; cloud batch jobs with recoverable checkpoints.
8. **Local Inference:** quantized compact model, structured report validator and CPU-capable preprocessing.

## 5. Discovery-run design

Planned command (not implemented yet):

```powershell
shorts-lm discover run --platform all --target-new 100 --min-views 1000000 --max-candidates 1500
```

A run generates queries from a seeded grid of platform/provider, language/script, country/region, content niche, publication window and discovery mode. Queries are shuffled with a recorded seed. Candidate results are enriched, filtered, deduplicated and assigned an acquisition status. The run stops after its target of new unique candidates, candidate budget, quota or provider limit. It returns actual yield and reasons for any shortfall. Do not retry indefinitely to force the output to say 100.

The database stores provider source keys and expiry/refresh rules. Durable deduplication can be guaranteed only while source identity/fingerprint can lawfully be retained. A hashed identifier is not automatically outside platform retention rules.

## 6. Local SQLite inventory

Use SQLite first; no remote database is required for initial discovery.

| Table | Purpose |
|---|---|
| `discovery_runs` | Target, start/end, query seed, quota and run summary |
| `source_items` | Platform ID, canonical URL, first/last seen, unique key and state |
| `metadata_snapshots` | Title/caption, description, tags/hashtags, duration, views/likes/comments and observation time |
| `rights_records` | Permission evidence, capability flags, version, expiry/revocation |
| `media_assets` | Delivered file, checksum, size, codec, provider and retention |
| `jobs` | Acquisition/processing status, retries and last error |
| `provider_state` | API cursor, query cell, quota and rate-limit state |

Use a unique index on provider/platform/source identity while that key may be retained. After authorized media acquisition, compute SHA-256 and optional perceptual video/audio fingerprints to catch cross-platform copies. A retention worker refreshes/deletes API data as required. Keep the database and media out of GitHub.

## 7. Model architecture and training

Do not train a foundation model from scratch. Use a pretrained decoder-based multimodal VLM, deterministic perception tools and a separate performance estimator.

Candidate bake-off (no winner preselected):
- Qwen3-VL-2B;
- Qwen3.5-2B;
- SmolVLM2-500M;
- VideoLLaMA3-2B;
- a larger open-weight teacher only if its license and cost are appropriate.

The initial local deployment target is a 2B-class quantized model; 4B is a stretch goal on the RTX 3050 4 GB, not a universal guarantee. Fine-tuning uses cloud GPUs after rights, data-quality and baseline gates pass. Training settings are model-specific.

Keep tasks separable: video grounding, OCR/transcript fusion, editing/VFX candidate detection, hook/pacing/payoff/audio analysis, metadata interpretation, creator-relative performance estimation and evidence-linked recommendations.

Train only on assets and derived records whose rights permit the intended use. Public API metadata and raw media have their own platform terms; local storage does not override them.

## 8. Scale and collection policy

The original ambition of 5–10 crore Reels plus 5–10 crore Shorts is not the first implementation target. It remains a long-term ambition conditional on platform agreements, licensed media feeds, durable data rights, storage, compute, rights operations and measured model improvement.

| Gate | Unique items/assets | Purpose |
|---|---:|---|
| Provider smoke tests | 10–25 mock/API candidates | Validate schema, quotas, dedup and retention |
| Discovery MVP | 100 new candidates/run target | Verify source yield and repeat prevention |
| Acquisition pilot | 100 rights-cleared media assets if available | Verify automatic delivery |
| Telemetry pilot | 300 authorized videos | Measure extractor quality and cost |
| Dataset v1 | 1K–2K reviewed examples | Baselines and annotation agreement |
| SFT candidate | 5K–10K examples | Fine-tuning experiment |
| Expansion | 20K–50K | Generalization and learning curves |
| Large corpus | 100K+ | Only with rights and unit economics |

The number of discovered URLs and trainable media assets are separate counters. Reports must never imply 1,000 metadata candidates equal 1,000 downloaded/training videos.

## 9. Evaluation

Discovery: per-provider query/unique yield; threshold correctness and snapshot age; duplicates across runs; data retention; short-format confirmation; quota/retry rates; candidates with authorized media delivery.

Data: all training assets have rights/provenance; checksums and extractor versions; ASR/OCR missing/failed states explicit; coverage by source/language/topic/speech mode/duration; creator/repost leakage excluded.

Model: timestamp grounding, edit-event F1, OCR/ASR quality, JSON validity, unsupported-claim rate, human usefulness, creator/time-holdout ranking/calibration and per-language/platform metrics.

The model may explain plausible associations. It must not claim one edit caused virality from observational data alone.

## 10. Revised phases

| Phase | Deliverable | Exit gate |
|---|---|---|
| 0. Provider/rights foundation | Credentials, source contracts, schemas and retention | Each enabled source has documented discovery and acquisition scopes |
| 1. Automated discovery + SQLite | YouTube metadata provider, Instagram Business Discovery interface, query planner, 1M filter, retention-aware dedup | Replay produces no duplicates; second run yields unseen items where available |
| 2. Rights-gated media delivery | YouTube partner path if accepted, creator inbox, licensed datasets/provider | Every acquired asset has delivery and training rights evidence |
| 3. Automated video processing | Reuse existing Phase 1 telemetry | 10, then 100, then 300 authorized media assets audited |
| 4. Dataset and labels | Dedup, review queue, creator/time splits | 1K–2K reviewed examples |
| 5. Model bake-off and baselines | Frozen VLM, retrieval and tabular baselines | Locked baseline report |
| 6. Cloud fine-tuning | LoRA/DoRA with checkpointing | Beats frozen model on predeclared tasks |
| 7. Quantized local deployment | Local model/API/UI | Measured hardware matrix |
| 8. Controlled scale | 5K/20K/50K+ | Rights, quality and marginal value pass |

### Existing work mapping

- Original Phase 1 single-video telemetry is retained as the processing component in revised Phase 3.
- Earlier Phase 2 local-manifest code/PR #4 is not an automated acquisition solution. Its validation, sampling, resumability and metrics may be reused once discovery and delivery layers exist. Do not mistake that PR for the requested hands-off crawler or treat it as the final acquisition path without reconciling it to this roadmap.

## 11. Hardware and deployment

Local laptop: Discovery Agent, SQLite, API calls, metadata normalization, deduplication, job scheduler, FFmpeg smoke tests and CPU preprocessing. RTX 3050 4 GB is useful for small experiments and quantized inference, not large-scale multimodal fine-tuning.

Cloud: VLM training and large-batch inference only after data rights/quality gates. Use SSH-capable instances, persistent object storage, checkpoints, resumable jobs, budget caps and shutdown guards. Colab is for experiments, not durable acquisition/database scheduling.

Storage: SQLite locally first; authorized raw media in private object storage/encrypted staging with expiry; compact telemetry in Parquet/JSON/JSONL; never put platform videos in public GitHub.

## 12. References

See [References](REFERENCES.md) and [Automated Discovery and Rights-Gated Media Acquisition](AUTOMATED_DISCOVERY_AND_ACQUISITION.md). Re-check platform terms, API versions, quotas, Meta eligibility and model licenses before implementation/release.
