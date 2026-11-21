# Shorts Language Model

Shorts Language Model is an automated short-form video discovery, telemetry and intelligence pipeline. The current acquisition implementation uses **open-source public-web search and downloader repositories**, not the YouTube Data API, Instagram Graph API or Meta Content Library.

The objective is to search for YouTube Shorts and Instagram Reels, filter current view-count observations at 1M+, save unique candidates to a local SQLite database, and download media to the laptop through open-source extractors when a valid item-specific rights record permits it. The existing multimodal analyzer then extracts transcript, OCR, scene, motion, audio and editing evidence.

## Non-API toolchain

| Purpose | Open-source tool | Use |
|---|---|---|
| YouTube Shorts search + metadata | ytscrape (MIT) | Shorts-only InnerTube web search, typed views/duration, pagination; not the official Data API |
| YouTube media download | yt-dlp + FFmpeg | Authorized MP4 acquisition, remuxing and download retry |
| Instagram public-link discovery | DDGS | Search indexed public Reel URLs without an Instagram developer token |
| Instagram Reel metadata + primary download | Instaloader | Resolve shortcode; view/play count, caption/hashtags, duration and Post download |
| Instagram alternate extractor | yt-dlp Instagram extractor | Second download attempt on a discovered Reel URL |
| Instagram fallback downloader | gallery-dl | Optional third attempt if Instaloader and yt-dlp fail |
| Local deduplication and job state | SQLite | Persist source IDs, metrics, download status and SHA-256 fingerprints |

The detailed rationale and limitations are in [docs/NON_API_DISCOVERY_TOOLCHAIN.md](docs/NON_API_DISCOVERY_TOOLCHAIN.md).

## Important metric handling

- YouTube view_count is stored as the view metric where ytscrape returns it; capped detail enrichment uses ytscrape player metadata when search results omit the metric.
- Instagram video_view_count is stored separately from video_play_count.
- The default filter uses view_count only. The optional --instagram-use-play-count switch permits play_count when the view_count field is absent, but preserves the metric label.
- Missing metrics are unknown, not zero, and never pass the default 1M threshold.
- YouTube candidates come from ytscrape's dedicated Shorts search filter. This is stronger format evidence than generic video search, but not a guarantee that every result will remain available for later download.
- Instagram search results are confirmed Reels when they came from a /reel/ search result and the resolved media is video. Profile/hashtag discoveries are candidates unless more source evidence is available.

## Current commands

Install on Windows PowerShell:

    py -3.11 -m venv .venv
    .venv/Scripts/Activate.ps1
    python -m pip install --upgrade pip
    pip install -e ".[dev,discovery,audio]" --upgrade

Install FFmpeg and ffprobe and ensure both are on PATH. The gallery-dl Instagram fallback is optional:

    pip install -e ".[instagram-fallback]"

Check dependencies:

    shorts-lm doctor

Discovery requires ytscrape, yt-dlp, Instaloader and DDGS. The doctor output checks ytscrape separately. Deno 2.3+ or Node.js 22+ is still recommended for yt-dlp YouTube media downloads.

### Phase 1 discovery reliability and coverage

YouTube search now uses the Shorts-specific filter from the MIT-licensed [ytscrape](https://github.com/vsmutok/ytscrape) library, rather than generic yt-dlp search results. It returns typed view-count/duration metadata and paginated results; a capped number of new candidates with missing fields can be enriched through a detail lookup.

The query planner rotates a broad topic/language/region pool (including Hindi, Marathi, Kannada, Tamil, Telugu, Bengali, English, Spanish, Portuguese and Indonesian). SQLite records every exact query/locale combination, so later runs prefer queries not used in the previous seven days. The new-candidate target is evaluated against unseen platform/source IDs first; known records no longer dominate the candidate evaluation budget.

Instagram public Reel URLs are discovered through DDGS with bounded timeouts, explicit search backends and one fallback engine. Instaloader now uses a 12-second request timeout and one connection attempt rather than its 300-second/three-attempt defaults. After repeated failures or a block/rate-limit response, the provider stops further Instagram lookups for that run instead of hanging or flooding the logs.

The latest JSON report separates query rotation, raw hits, new/known IDs, view-metric coverage, YouTube enrichment attempts, Instagram lookup successes/failures and circuit-breaker reasons. See [Phase 1 Discovery Coverage and Provider Reliability](docs/PHASE_1_DISCOVERY_COVERAGE.md).

### Discover 100 new unique eligible candidates

```powershell
shorts-lm discover run --platform all --target-new 100 --min-views 1000000 --max-candidates 1500
```

Useful controls:
- `--max-search-queries 24`: YouTube query budget per run.
- `--instagram-max-search-queries 8`: DDGS query budget per run.
- `--query-cooldown-days 7`: avoid repeating the same query/locale within seven days.
- `--metadata-enrichment-limit 40`: cap detailed YouTube lookups for missing search metadata.
- `--instagram-max-lookups 15`: cap individual Instaloader metadata fetches.
- `--seed 42`: optional reproducible query ordering. Omit it for a fresh random ordering.

YouTube only:

```powershell
shorts-lm discover run --platform youtube --target-new 100 --min-views 1000000 --max-search-queries 30
```

Instagram only:

```powershell
shorts-lm discover run --platform instagram --target-new 100 --min-views 1000000 --instagram-max-search-queries 8 --instagram-max-lookups 15 --instagram-timeout 8 --instagram-request-timeout 12
```

A result target is best-effort, not guaranteed. Search result ranking is biased, and only new unique IDs with a reported qualifying view metric count. Missing views remain unknown and never become zero or 1M+. The README and coverage guide distinguish this from platform-wide random sampling.

### Download candidates

Discovery does not automatically equate a public URL with training permission. Downloading requires a private JSONL rights manifest with an item-specific, current grant for media retrieval, analysis, temporary processing, derived-artifact retention and model training.

The example manifest at examples/rights_manifest.example.jsonl is deliberately non-authorizing. Replace it only with real permission evidence and keep the actual manifest under data/private/.

    shorts-lm discover download --rights-manifest data/private/rights.jsonl --limit 25 --output-dir data/private/acquired

The downloader rejects missing, expired, revoked or incomplete permission records. It writes a local MP4 and a private metadata/rights sidecar.

## Local persistence and deduplication

Default SQLite database: .shortslm/discovery.sqlite3. It is private and gitignored.

- Unique platform/source ID prevents the same link being selected again.
- SHA-256 after download catches byte-identical content found on different platforms.
- Download failures remain retryable.
- Metadata records store title/caption, description, creator, hashtags, observed metric, duration, publication date and discovery status.
- Run summaries are written under outputs/discovery/.

Search results are indexed and ranked. Shuffling queries/results makes selection less tied to a single result ordering; it does not create a mathematically uniform random sample of all YouTube or Instagram videos. The requested target is not guaranteed: source coverage, rate limits, duplicate results and missing view counts can produce a partial yield.

## Instagram session and access limits

Public indexed Reel links are attempted without a session first. Some Instagram content, hashtag searches or metadata fields may require the user's own Instaloader session. Instaloader respects its own rate controller. If an item is login-gated, blocked, deleted or unavailable, the crawler records/skips the error. It does not use proxy rotation, CAPTCHA bypass, stolen cookies or other access-control workarounds.

## Existing local video analyzer

The Phase 1 analyzer remains the downstream processor for a permitted local MP4:

    shorts-lm doctor
    shorts-lm analyze --input data/private/acquired/VIDEO.mp4 --output outputs/analysis.json --rights-basis creator_permission --rights-reference PRIVATE_CONSENT_REFERENCE --training-permitted

The 4 GB RTX 3050 is not required for discovery, SQLite or download. The local laptop is appropriate for discovery and CPU media preprocessing. Use a rented GPU for substantial multimodal fine-tuning after the dataset and rights gates pass.

## Revised phases

1. Non-API discovery + SQLite — current implementation.
2. Authorized media acquisition + robust metadata/asset validation.
3. Batch multimodal processing using the existing analyzer.
4. Dataset QA, duplicate control and annotation.
5. Model bake-off and frozen baselines.
6. Cloud fine-tuning.
7. Quantized local deployment.
8. Controlled expansion with measured cost and data quality.

## Security and data safety

Never commit the discovery SQLite database, downloaded MP4s, Instagram session files, cookies, credentials, private rights manifests, consent documents, raw transcripts or private metadata reports. The .gitignore includes these local artifacts.

Only acquire and train on media for which the exact intended use is authorized. Publicly viewable content is not automatically licensed for bulk copying, persistent storage or model training. This project does not attempt to bypass platform login, technical restrictions or rate limits.

## Tests

    ruff check src tests
    pytest -q

## Documentation

- [Non-API Discovery and Downloader Toolchain](docs/NON_API_DISCOVERY_TOOLCHAIN.md)
- [Global Master Plan](docs/GLOBAL_MASTER_PLAN.md)
- [Roadmap](docs/ROADMAP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Data and Compliance](docs/DATA_AND_COMPLIANCE.md)
- [Dataset and Labeling](docs/DATASET_AND_LABELING.md)
- [Phase 1 Design](docs/PHASE_1_DESIGN.md)
- [Phase 2 Design](docs/PHASE_2_DESIGN.md)
- [Phase 2 Testing](docs/PHASE_2_TESTING.md)
- [References](docs/REFERENCES.md)

## License

Apache-2.0. See LICENSE.
