# Shorts Language Model

Shorts Language Model is an automated, rights-aware short-form video discovery and intelligence project. The goal is to discover eligible YouTube Shorts and Instagram Reels without manually pasting individual links, deduplicate candidates in a local database, acquire media through authorized providers, extract multilingual audiovisual evidence, and ultimately fine-tune a compact multimodal model for local analysis.

> Automation does not grant media rights. A public URL or view count is not permission to download, store or train on a video. The system uses official APIs, approved research interfaces, creator-authorized delivery and licensed media providers. It will not fall back to unauthorized scraping or generic downloading.

## What the finished system is intended to do

1. Run a discovery job with a target such as 100 or 200 new candidates.
2. Search supported sources across language, region, topic and publication windows.
3. Filter by a current, timestamped 1M+ view/plays observation where the source exposes that metric.
4. Check local SQLite inventory so already-seen candidates are not repeatedly selected while their identity can lawfully be retained.
5. Store permitted title/caption, description, hashtags/tags, duration and engagement snapshots.
6. Acquire the MP4 automatically only where a platform/provider/creator delivery route grants the required media and training rights.
7. Run transcript, OCR, scene, motion, cut, VFX-candidate and audio extraction.
8. Build a clean dataset and fine-tune a compact multimodal model in cloud batches.
9. Run the resulting quantized model locally where hardware measurements support it.

A discovery target is not a guaranteed download count. If a source cannot lawfully deliver raw media or quota/search yield is lower than expected, the run reports the actual yield and why.

## Platform reality

- **YouTube:** the official Data API can discover videos and return metadata/statistics. It does not grant MP4 download rights. YouTube prohibits downloading/caching audiovisual copies without prior written approval and prohibits scraping. The creator third-party AI-training opt-in is a possible authorized path, but the project/company must be admitted and creators/rightsholders must opt in.
- **Instagram:** the Graph API can inspect eligible public Business/Creator accounts using Business Discovery; Reel view counts are available through that path. It is not a global search/download API for every public Reel. Meta Content Library is controlled research access; API data cannot be downloaded from the API.
- **Browser agent:** Playwright may automate a specific approved interface. It is not used to bypass API access, login, rate limits or download restrictions.

Read [Automated Discovery and Rights-Gated Media Acquisition](AUTOMATED_DISCOVERY_AND_ACQUISITION.md) for the detailed source matrix and acquisition routes.

## Current implementation status

- **Implemented:** local single-video telemetry CLI, media validation, frame sampling, cut/motion candidates, ASR/OCR adapters, audio measurements and validated JSON reports.
- **Not implemented yet:** automated API discovery, local discovery SQLite database, 100/200 target-based query planner, policy-aware metadata retention, rights-gated media delivery providers and autonomous end-to-end ingestion.
- **Not yet trained:** no ShortsLM fine-tuned checkpoint or 300-video empirical dataset is claimed.

The existing single-video analyzer is retained as the media-processing engine. The old local-manifest Phase 2 pilot is useful as downstream processing/QA code, but it is not the automated source-discovery solution.

## Revised architecture

    Discovery scheduler
        |
        v
    YouTube Data API / Instagram Business Discovery / approved research / licensed feeds
        |
        v
    Provider normalizer -> 1M+ candidate filter -> SQLite dedup + retention
        |
        v
    Rights and media-delivery gate
       / \
      /   \
    authorized  metadata-only/deferred
      |
      v
    Approved asset delivery -> private staging + checksum
      |
      v
    ShortsLM telemetry: ASR + OCR + shots + motion + audio
      |
      v
    Evidence store + human review + dataset quality/splits
      |
      v
    Frozen model baseline -> cloud LoRA fine-tuning -> evaluation
      |
      v
    Quantized local multimodal model + report app

## Hardware strategy

**Local Windows/WSL laptop:** discovery, SQLite, API calls, metadata normalization, deduplication, job scheduling, FFmpeg smoke tests and CPU telemetry. RTX 3050 4 GB is optional for small experiments and quantized inference.

**Cloud GPU:** batch fine-tuning and higher-throughput VLM evaluation after data rights and quality gates pass. Colab is useful for short experiments, not as the durable acquisition scheduler or database.

## Existing local analyzer quickstart

Install FFmpeg (including ffprobe), create the Python environment, then run:

    py -3.11 -m venv .venv
    .venv/Scripts/Activate.ps1
    python -m pip install --upgrade pip
    pip install -e ".[dev,audio]"
    shorts-lm doctor

Analyze a file that you are authorized to process:

    shorts-lm analyze --input authorized_clip.mp4 --output outputs/analysis.json --rights-basis creator_owned --asr-model small --asr-device cpu

This is the existing media processor, not the future autonomous acquisition command.

## Revised phases

1. Provider and rights foundation
2. Automated discovery + SQLite deduplication — next coding phase
3. Rights-gated media acquisition
4. Automated multimodal processing
5. Dataset QA and annotation
6. Model bake-off and baselines
7. Cloud fine-tuning
8. Quantized local deployment and controlled scale

## Project documentation

- [Global Master Plan](docs/GLOBAL_MASTER_PLAN.md)
- [Automated Discovery and Media Acquisition](docs/AUTOMATED_DISCOVERY_AND_ACQUISITION.md)
- [ADR-002: Automated Discovery Without Unauthorized Scraping](docs/ADR-002-AUTOMATED-DISCOVERY.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Data and Compliance](docs/DATA_AND_COMPLIANCE.md)
- [Dataset and Labeling](docs/DATASET_AND_LABELING.md)
- [Evaluation](docs/EVALUATION.md)
- [Roadmap](docs/ROADMAP.md)
- [References](docs/REFERENCES.md)
- [Research Comparison](docs/RESEARCH_COMPARISON.md)
- [Original Phase 1 Design and Testing](docs/PHASE_1_DESIGN.md)

## Tests

    ruff check src tests
    pytest -q

## Data safety

Keep API credentials in environment variables or a local secret manager. Never commit cookies, access tokens, source media, private SQLite files, creator data, transcripts, consent documents or private reports. API-derived metadata and IDs must expire/refresh according to provider policy; hashing an ID does not automatically remove those obligations.

## License

Apache-2.0. See [LICENSE](LICENSE).
