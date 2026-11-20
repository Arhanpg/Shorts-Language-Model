# Research Comparison: Supplied Proposals and Final Decisions

**Purpose:** preserve useful insights from the supplied diagrams and pasted AI proposals while separating robust architectural ideas from unverified empirical claims. This is a technical assessment, not endorsement of every source or number.

## 1. Supplied diagrams

Six images supplied on 20 November 2026 are included in [research/images](research/images/):

1. Data engine / model factory workflow.
2. Cost and storage comparison for 5,000–200 million videos.
3. View distribution and creator concentration chart.
4. Stratified ingestion → deterministic telemetry → cloud fine-tuning → local inference.
5. Claimed Qwen3.5 compact-model VRAM comparison.
6. GPU provider price comparison.

They are useful as proposed designs and scenario visualizations. Their numeric values have not been reproduced against this project's workload.

## 2. Cross-proposal consensus — accepted

- Do not train a foundation model from scratch.
- Use a pretrained multimodal VLM and task-specific fine-tuning only after baseline evaluation.
- Separate acquisition, extraction, annotation, dataset construction, training, evaluation and deployment.
- Combine language-model reasoning with explicit OCR, ASR, temporal and motion measurements.
- Preserve compact JSON telemetry and selected keyframes instead of treating raw MP4 storage as the only dataset representation.
- Include ordinary/non-viral controls; do not sample only high-view videos.
- Normalize performance by creator baseline and video age when valid data exists.
- Evaluate on creator-disjoint and time-aware splits.
- Design for quantized local inference while measuring real resource use.
- Publish model card, dataset card, rights/provenance policy and benchmark reports.

## 3. Proposal-by-proposal assessment

### A. Laptop/free API data engine + Colab/rented GPU model factory

**Accepted:** clean separation between discovery, permitted fetch, extraction, labeling, dataset construction, fine-tuning, evaluation and shipping. Temporary media processing and compact outputs are sensible where rights explicitly allow it.

**Changed:** “channel crawl” is not blanket permission to fetch media. Official APIs are used only within their policies and quotas. Metadata-only access does not grant video-download or model-training permission. Use provider capabilities and rights checks before each operation.

**Final decision:** retain the two-plane layout: data/telemetry plane and model factory plane, connected by versioned manifests and artifact references.

### B. 50K cost sweet spot vs. 20-crore corpus

**Accepted:** compare tiers, measure raw and derived storage separately, use compute-and-discard where lawful, and avoid a 200M raw corpus as the first milestone.

**Not accepted as facts:** $112.25 total for 50K; $449,004 for 200M; 69 GPU-hours; 2 GPU-seconds per full-video preprocessing; 0.83 MB per video; 4,000 tokens/video; 3,500 effective tokens/s; 4,000× cost ratio. These are scenario assumptions. The chart lacks enough workload measurements to validate them. The totals may omit human review, failure/retry, source access, data egress, backups, distributed orchestration, compliance and evaluation.

**Arithmetic observation:** at an assumed 9.5 MB/video, 50,000 videos are 475 GB decimal (about 0.475 TB); 200 million are 1.9 PB decimal. This is arithmetic from the chosen average, not a measured file-size distribution. Network transfer assumptions need protocol overhead and real utilization.

**Final decision:** keep scale figures as sensitivity scenarios, publish assumptions and measure cost/video on a 300-video pilot. Do not present the infographic total as a quote or project budget.

### C. Million-view channel concentration chart

**Accepted hypothesis:** raw 1M+ filters can overrepresent established mega-channels. Include creator baselines and matched controls; sample across creator sizes and categories.

**Not accepted as platform-wide truths:** the chart's exact observations (32,016 Shorts, 8.9% at 1M+, 64.7% from 49 channels, 2.6% vs 22.9% discovery bias) are usable only as reported sample-specific figures. The sampling frame and method are not sufficiently documented here to generalize.

**Final decision:** preserve them as unverified sample-specific evidence only. Build our own sampling ledger and report sample frame, dates, creator inclusion, observation age and uncertainty. Creator-relative performance is an experiment, not proven causal correction.

### D. Stratified ingestion + deterministic telemetry + cloud fine-tuning

**Accepted:** this is the strongest overall pipeline diagram. Lane-based architecture is right. Temporal telemetry is essential for rapid edits. Retain hook-aware keyframes, OCR, ASR, audio beat/event signals and JSON output.

**Changed:**
- TransNetV2 and PySceneDetect are candidates to compare, not one guaranteed solution.
- RAFT/GMFlow may be expensive; begin with OpenCV motion statistics and add learned optical flow only if the benchmark requires it.
- PaddleOCR support and accuracy must be validated per language/script.
- Whisper and Indic ASR should be compared per language; no universal word-perfect coverage claim.
- CLAP/audio models have separate model/data licenses; audit before use.
- “Raw MP4 discarded” is a retention pattern, not a copyright permission workaround.
- Teacher-generated labels need human review and telemetry contradiction checks.

**Final decision:** adopt lane-based telemetry, but make each extractor replaceable and benchmarked.

### E. Qwen3.5 / DeltaNet 4 GB memory and local inference claims

**Accepted:** Qwen3.5-2B and 4B deserve a benchmark; compact hybrid attention could reduce cache requirements; GGUF/llama.cpp merits testing. Separate a Lite model from a higher-quality model.

**Not accepted without reproduction:** 2,369 MB, 3,244 MB, 3.3× KV-cache reduction, 49/102 tokens/s, 14-second reports, universal 4 GB fit, and assumptions about CPU projector offload flags. Real memory includes weights, vision/projector modules, KV or recurrent state, CUDA buffers, frame activations, context and runtime overhead. Windows desktop VRAM use varies.

**Training caveat:** current Unsloth Qwen3.5 fine-tuning guidance reports approximate BF16 LoRA memory of 5 GB for 2B and 10 GB for 4B, and advises against 4-bit QLoRA on Qwen3.5 due to quantization differences. This supports rented-GPU training and contradicts treating 4-bit QLoRA as the default Qwen3.5 recipe.

**Final decision:** candidate benchmark only. Record peak VRAM/RAM, first-token and end-to-end latency, model/runtime/quantization/context/frame count. Start at 2B or smaller; 4B is a stretch for 4 GB.

### F. GPU provider pricing chart

**Accepted:** SSH-capable GPU with persistent storage, tmux and checkpointing is generally more suitable than a notebook for long experiments. Colab is good for tutorials and short tests, not production orchestration.

**Not accepted as fixed quotes:** Race Engineering ₹20/₹65 hourly rates, Vast.ai $0.59/$0.75, RunPod $0.69/$2.09, Colab $0.75 effective, and other listed values. Marketplace availability, region, storage, bandwidth, tax and spot interruptions change effective cost. They were not verified as quotes for our account.

**Final decision:** benchmark one 24 GB-class instance and one larger-memory instance. Keep provider-neutral scripts and include persistent storage and interruption overhead. Check current billing before spending.

## 4. Assessment of the additional pasted proposals

### Hybrid neuro-symbolic telemetry + Qwen3.5 2B/4B + optional 235B teacher + SFT/GRPO/GGUF

**Keep:** telemetry front-end, shared visual-editing vocabulary across platforms, optional small platform adapters, creator-relative controls, evidence verification and local quantization.

**Modify:** do not force platform conditioning if platform labels are unavailable or unreliable; do not mix incompatible engagement metrics. Store platform and metric definitions and test cross-platform transfer separately. Use separate platform calibration/heads if distributions differ.

**Not mandatory:** 235B teacher, exact teacher price, 50K in eight weeks, 10K-pair GRPO, 75% reasoning traces, exact LoRA configuration and stated benchmark targets. Each needs independent validation. Long hidden reasoning traces are unnecessary; concise structured evidence is easier to audit.

### ReelScope-style creator copilot

**Keep:** upload-first workflow, structured JSON, review UI, creator draft feedback and creator-owned analytics. These are practical product features.

**Modify:** accept links only through authorized integrations or rights-confirmed paths. A public link is not itself a processing license. Start CLI, then Gradio/Streamlit; Next.js later if the product warrants it.

### Scale-first cloud architecture

**Keep:** manifests, shards, idempotent workers, quotas, checkpoints, observability and cost counters early. Smoke tests still run before a large batch.

**Modify:** scale-ready interfaces do not justify large cloud spend before the 300-video pilot. Expand only after measured quality and unit economics pass.

### 20K great examples and small-model proposal

**Keep:** 300 → 5K → 20K initial ladder; same-creator controls; baseline predictor before VLM fine-tuning; SmolVLM2-500M as a smoke baseline; Qwen3-VL-2B as a candidate; existing VidTrace reuse after interface audit.

**Modify:** 20K is not a scientifically guaranteed optimal size. Sample size must follow task coverage, uncertainty and measured learning curves. MicroLens and other datasets require independent license/provenance review; research availability does not imply commercial training or redistribution rights.

## 5. Final model and training decision

| Layer | Decision | Status |
|---|---|---|
| Compact baseline | Qwen3-VL-2B | First benchmark candidate |
| Alternative | Qwen3.5-2B | Verify card, runtime and training support |
| Video-specific baseline | VideoLLaMA3-2B | Compare temporal quality |
| Low-resource baseline | SmolVLM2-500M | Pipeline and CPU fallback |
| Larger teacher | Open-weight model with compatible terms | Optional, not MVP dependency |
| Fine-tuning | SFT + LoRA/DoRA as supported | After frozen baseline |
| QLoRA | Only if the selected family supports it well | Not assumed for Qwen3.5 |
| GRPO/RL | Deferred | After stable SFT and verifiable reward checks |
| Performance estimator | LightGBM/ranker | Separate from VLM |
| Local packaging | GGUF/llama.cpp if exact multimodal model supported | Verify first |

## 6. Source and claim hygiene

Every dataset size, performance value, video count, cost, throughput and license statement must have source, date checked, scope and confidence. Distinguish peer-reviewed research, official documentation, model cards, repository claims, third-party measurements and internal experiments. Verify item-level terms before commercial training or releasing weights.

## 7. Overall verdict

The best combined plan is **rights-aware stratified ingestion + deterministic telemetry + compact multimodal reasoning + separate creator-relative performance predictor**. It takes the strongest structural ideas from all proposals without inheriting speculative global-supply estimates, exact cloud-cost claims or unverified 4 GB performance promises.


## 8. Updated acquisition research — 21 November 2026

This section supersedes the earlier working assumption that a generic browser agent can discover and download arbitrary public Reels/Shorts.

### YouTube Data API

Official documentation gives a separate default 100-call/day quota for search.list and 10,000 quota units/day for other standard methods. videos.list returns snippet fields such as title, description and tags, content details and statistics. This supports candidate metadata discovery and a current view-count filter, but not MP4 delivery.

The Developer Policies prohibit copying audiovisual content without prior written approval and prohibit scraping YouTube applications. Non-authorized API data has a 30-day refresh/delete limit. The additional-derived-metrics policy, updated 1 June 2026, provides an approval/amendment pathway for specific Analytics & Reporting metrics and longer retention of approved statistical data; it does not automatically grant raw-video training permission.

YouTube's third-party AI-training option is off by default and requires all applicable rights holders to opt in. Approved third-party companies can be selected by creators, and YouTube may share eligible videos with them. Companies can apply to join the list. This is a plausible media-delivery path only if accepted and the handoff is documented.

### YouTube Shorts identification

Official Shorts guidance says that, for standard channels, square or vertical videos up to three minutes uploaded from 15 October 2024 are categorized as Shorts. Public Data API fields used in ordinary candidate discovery do not provide a reliable universal aspect-ratio flag. Discovery therefore stores candidate/unknown/confirmed format state rather than equating every video under 180 seconds with a Short.

### Instagram Graph API

Meta's media documentation says media endpoints return media belonging to professional accounts, not personal accounts. Business Discovery is a narrow path for eligible public Business/Creator accounts whose usernames are known. Reels view_count is available through Business Discovery; its definition can include paid/cross-posted views. Hashtag search does not expose all Business Discovery fields, so hashtag results cannot be assumed to provide the same 1M+ filter. media_url may be omitted for copyrighted/flagged content.

### Meta Content Library

Meta Content Library is a controlled-access research product with institutional eligibility/review. Its API is used in a secure research environment and Meta says API data cannot be downloaded from it. The UI has a separate downloadable subset for approved researchers, subject to additional requirements. This may support institutional research discovery, but it is not a general local MP4 feed.

### Decision

- Build official metadata discovery and a rights-aware SQLite dedup ledger.
- Treat metadata candidate discovery and media acquisition as separate subsystems.
- Keep arbitrary public-platform downloader/scraper out of default design.
- Make YouTube third-party-training partner admission, Meta institutional access, creator handoff and licensed providers explicit onboarding workstreams.
- Do not promise 100/200 media files per run; report actual unique candidates and separately report authorized media assets.


## 9. Final toolchain decision — non-API request (21 November 2026)

The earlier API-first recommendation is superseded by the project owner's explicit direction to avoid official platform APIs and use open-source GitHub tools.

**Accepted implementation:**
- yt-dlp's YouTube search extractor (ytsearch) for link discovery, metadata and video retrieval;
- DDGS public web search to find indexed Instagram Reel URLs;
- Instaloader to resolve Instagram shortcode metadata, hashtags, view/play metrics and download posts;
- yt-dlp Instagram extraction as a secondary download attempt;
- gallery-dl as an optional third-party extraction fallback;
- SQLite for durable local platform/source-ID dedup and job status;
- SHA-256 to detect exact duplicate media bytes across platforms.

**Why not a single Instagram crawler:** no reviewed open-source project can guarantee a complete, current global listing of every public Instagram Reel without depending on the site search/login behaviour. The implemented approach combines indexed link search with Instaloader. It is intentionally best-effort and reports incomplete metadata, blocked pages and failures.

**Metric decision:** never convert missing Instagram view/play fields into zero. Keep video_view_count and video_play_count separately. Default 1M filter uses view_count; play_count requires an explicit CLI option and keeps its source metric label. YouTube short format uses explicit Shorts URL or available upload-date/dimensions/duration evidence; ambiguous format stays a candidate/unknown.

**Acquisition decision:** the open-source downloader is not the rights authority. A matching private manifest is required before media retrieval and training. The code checks required scopes, revocation and expiry; the project owner remains responsible for authentic permission evidence and third-party music/rights. No CAPTCHA, login, rate-limit, DRM or access-control bypass is part of the implementation.

**What remains uncertain:** platform extractor compatibility and search engine coverage can change without notice. The 100/200 target is a best-effort target; actual new eligible candidates per run depend on public indexing, search rank, metric availability and dedup history. No claim of uniform/random sampling or universal Instagram coverage is made.
