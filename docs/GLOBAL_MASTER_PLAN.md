# Shorts Language Model — Global Master Plan

**Updated:** 21 November 2026  
**Direction selected:** non-official-API, open-source discovery and extractor workflow.

## 1. Product goal

Shorts Language Model (ShortsLM) is an automated short-form video discovery and intelligence pipeline. A normal run should not require the owner to paste individual video URLs or download MP4 files manually.

The intended cycle is:

1. Generate/search topic and language phrases automatically.
2. Find YouTube Shorts and public Instagram Reel links using open-source discovery tools.
3. Extract available metadata: title/caption, description, hashtags, creator, duration, upload date and current view/play metric.
4. Keep only new candidates that meet the configurable 1,000,000 metric threshold and have adequate short-form evidence.
5. Store candidate identity, metadata snapshots and state in a local SQLite database.
6. Avoid reselecting an already stored platform item; after media delivery, compare SHA-256 to catch byte-identical cross-posts.
7. Download media automatically using open-source extractors only for items with the required item-specific permission.
8. Send authorized MP4s through the existing local Phase 1 telemetry pipeline.
9. Build reviewed, deduplicated training shards and fine-tune a pretrained multimodal model in batches.
10. Evaluate, quantize and deploy a compact model for local analysis.

The discovery and media acquisition components are intentionally separate. Finding a URL is not the same as proving that downloading, persistent storage, analysis and model training are permitted.

## 2. No official platform API keys in the discovery workflow

The user explicitly selected open-source repositories rather than the YouTube Data API, Instagram Graph API or Meta Content Library. The implemented discovery commands do not use those platform APIs or require platform developer tokens.

| Platform/task | Selected open-source tool | Implementation role |
|---|---|---|
| YouTube search | yt-dlp | Uses the ytsearchN query extractor; metadata and video URL extraction |
| YouTube download | yt-dlp + FFmpeg | Downloads an eligible video and remuxes to MP4 |
| Instagram public Reel link search | DDGS | Searches the public web index for indexed instagram.com/reel links |
| Instagram Reel metadata | Instaloader | Resolves shortcode and reads available caption, hashtag, duration, view/play metrics |
| Instagram hashtag/profile expansion | Instaloader | Optional; requires the user's own existing Instaloader session for some queries |
| Instagram download primary | Instaloader | Downloads a resolved video Post where available |
| Instagram download fallback 1 | yt-dlp | Attempts its Instagram extractor on the Reel URL |
| Instagram download fallback 2 | gallery-dl | Optional alternate extractor if earlier tools fail |
| Candidate database | Python SQLite | Local persistent run history, unique IDs, states and metrics |
| Cross-platform exact-file dedup | SHA-256 | Prevents byte-identical MP4s being processed twice |

These tools are best-effort extractors. Website changes can break them; public search engines do not index every post, and Instagram fields may not be available on every Reel. Do not promise platform-wide complete or uniform sampling.

See [NON_API_DISCOVERY_TOOLCHAIN.md](NON_API_DISCOVERY_TOOLCHAIN.md) for repository research, commands, actual fields and limitations.

## 3. Discovery behaviour

Planned command:

```powershell
shorts-lm discover run --platform all --target-new 100 --min-views 1000000 --max-candidates 1500
```

The query planner builds a set of phrases across language, region, category and topic. Example topics include cricket, comedy, education, music, gaming, technology, cooking, travel and editing. Query order and candidate order are shuffled using a recorded seed. Search engine results remain ranked/indexed; this is not mathematically uniform random sampling.

Default objective: 100 new unique qualifying candidates in a run. 200 can be configured by raising target-new. The command stops at the target, maximum candidate budget or available results. If only 43 new items qualify, it reports 43; it does not fabricate candidates or loop without limit.

Candidate status includes:
- eligible;
- below_threshold;
- metric_unknown;
- format_unknown;
- not_short;
- downloaded;
- download_failed;
- duplicate_media.

Unknown metrics are never converted to zero and never pass the 1M filter by default.

### YouTube format classification

A URL explicitly returned as a Shorts URL is a strong format indicator. Otherwise, metadata dimensions and duration are used. For standard channels, YouTube's three-minute Shorts eligibility applies to square/vertical uploads on/after 15 October 2024; the earlier duration ceiling was 60 seconds. If upload date or dimensions are missing, the candidate remains uncertain instead of being confidently labelled a Short. Landscape videos are rejected as non-Shorts by this heuristic.

### Instagram metrics

Store Instaloader's video_view_count as view_count and video_play_count as play_count, separately. The default threshold uses view_count only. A CLI option can explicitly use play_count when view_count is absent, and the source metric name remains attached. Missing counts remain unknown. Do not combine views and plays across services in an unlabeled common measure.

### Phase 1 reliability implementation

YouTube discovery uses yt-dlp's flat playlist extraction mode (extract_flat=in_playlist) so playlist search entries are not each resolved as a full individual video page. View counts and durations are taken from search-page metadata when present. The provider uses a quiet logger and records errors instead of flooding the terminal with one failure per unavailable video.

The default Instagram DDGS region is India English (in-en), and the search adapter supports multiple result pages. Discovery diagnostics distinguish raw search hits, unique IDs, repeated results, source IDs already stored, missing view metrics, below-threshold counts, uncertain short format and provider failures. Per-platform counts are written to the JSON report.

SQLite upserts calculate eligibility from merged incoming and previously stored metadata. A later result that omits a metric cannot downgrade a row that already has a valid observation.

For full YouTube video extraction and downloading, the environment also needs yt-dlp EJS scripts and a supported JavaScript runtime (Deno 2.3+ recommended, Node.js 22+ accepted). The doctor command checks these separately from flat search prerequisites. See [Phase 1 Discovery Reliability](PHASE_1_DISCOVERY_RELIABILITY.md).

## 4. Local inventory and unique selection

Default database: `.shortslm/discovery.sqlite3`.

Tables:
- discovery_runs: run ID, start/end, requested target, threshold, result totals;
- candidates: platform, source ID, canonical URL, title/caption, description, creator, metric snapshots, duration, tags/hashtags, upload date, format confidence, discovery state, download state and error;
- media fingerprint columns: SHA-256 and downloaded timestamp.

Unique source key: `(platform, source_id)`. A repeated discovery result updates its metadata record rather than creating another candidate row.

Exact cross-platform duplicate rule: after authorized download, compute SHA-256. If an identical file already exists under another platform/source ID, mark the later one `duplicate_media` and delete the redundant newly fetched file. This catches exact byte duplicates, not perceptually identical re-encodes. Perceptual hashing is a later phase.

The DB, local reports, private session file, rights manifest and MP4s remain on the laptop and are excluded from Git.

## 5. Media acquisition

Open-source extractors may technically retrieve a URL, but an extractor's capability is not permission for the intended use. The downloader therefore consumes a private rights JSONL manifest keyed by platform and source ID. It requires separate current grants for:
- media retrieval;
- media analysis;
- temporary processing;
- derived-artifact retention;
- model training.

A missing, revoked, expired or incomplete grant blocks the item. The manifest is a local attestation/evidence pointer; the program does not independently verify the authenticity of consent or copyright ownership. Keep the evidence itself private.

Download order:
- YouTube: yt-dlp + FFmpeg.
- Instagram: Instaloader → yt-dlp extractor → optional gallery-dl.

Do not use browser-cookie scraping, password command-line flags, CAPTCHA/challenge bypass, proxy rotation to evade rate limits, DRM circumvention or account/access-control bypass. Use an Instaloader session created by the user through its normal login workflow when a supported Instagram query needs it. If a service blocks a request, record the failure and stop/retry later within normal upstream controls.

## 6. Media processing and model

The existing local Phase 1 analyzer remains the telemetry engine. Each authorized downloaded clip can be analyzed for:
- frame sampling and keyframe evidence;
- cut/shot candidates and motion;
- ASR transcript and language;
- on-screen OCR;
- audio energy/events;
- grounded metadata and evidence-linked JSON report.

Do not update model weights once per incoming clip. Accumulate a versioned, deduplicated and reviewed batch; preserve creator/time split controls; then fine-tune. Use a pretrained multimodal model, not a foundation model trained from scratch.

Compact VLM candidates remain Qwen3-VL-2B, Qwen3.5-2B, SmolVLM2-500M and VideoLLaMA3-2B, subject to current model cards, supported training recipes and fair benchmark comparison. Train on rented/cloud GPUs; use the local RTX 3050 4 GB for discovery, SQLite, FFmpeg/CPU preprocessing and small quantized inference experiments.

## 7. Revised phases

| Phase | Deliverable | Exit gate |
|---|---|---|
| 0 | Provider setup, local config and permission manifest | Optional tools installed; secrets/data locations private |
| **1** | **Non-API discovery + SQLite** | Search, filter, metrics, source-ID dedup, partial-yield report and repeat-run validation |
| **2** | **Open-source media acquisition** | Permission-gated MP4 download, FFprobe, SHA-256, retries and exact duplicate handling |
| 3 | Batch telemetry | 10 → 100 → 300 authorized clips with extractor QA |
| 4 | Dataset QA and annotation | Gold examples, creator/time split and review |
| 5 | Model bake-off | Frozen baseline and chosen compact model |
| 6 | Cloud fine-tuning | Repeatable checkpointed SFT and held-out improvements |
| 7 | Local deployment | Quantized inference resource/quality matrix |
| 8 | Controlled scale | Expand only when data rights, yield, quality and cost are measured |

## 8. Success reporting

Always report separate counts:
- results encountered;
- unique platform candidates newly stored;
- 1M+ eligible candidates;
- candidates with unknown metric;
- candidates with uncertain format;
- already seen source IDs;
- authorized downloads;
- failed downloads;
- byte-identical media duplicates;
- clips successfully analyzed;
- examples approved for model training.

The number of discovered links must never be presented as the number of downloaded or trainable videos.

## 9. References and tool details

See:
- [Non-API Discovery Toolchain](NON_API_DISCOVERY_TOOLCHAIN.md)
- [Data and Compliance](DATA_AND_COMPLIANCE.md)
- [Dataset and Labeling](DATASET_AND_LABELING.md)
- [References](REFERENCES.md)

This master plan supersedes the earlier API-first discovery direction chosen in PR #5.
