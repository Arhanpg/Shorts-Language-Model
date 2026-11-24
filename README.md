# Shorts Language Model

Shorts Language Model is an automated short-form video discovery, telemetry and intelligence pipeline. The current acquisition implementation uses **open-source public-web search and downloader repositories**, not the YouTube Data API, Instagram Graph API or Meta Content Library.

The objective is to discover YouTube Shorts and Instagram Reels with 1M+ views/plays, save unique candidates in a local SQLite database, download selected videos through open-source extractors, and run the multimodal analyzer for transcripts, OCR, scenes, motion, audio and editing evidence.

## Non-API toolchain

| Purpose | Open-source tool | Use |
|---|---|---|
| YouTube Shorts search + metadata | ytscrape (MIT) | Shorts-only InnerTube search with bounded public pagination and typed views/duration |
| YouTube Shorts discovery surfaces | yt-dlp | Flat metadata-only hashtag Shorts shelves and discovered-channel Shorts tabs |
| YouTube media download | yt-dlp + FFmpeg | MP4 download, remuxing and retry |
| Instagram public-link discovery | DDGS | Search indexed public Reel URLs without an Instagram developer token |
| Instagram Reel metadata + primary download | Instaloader | Resolve shortcode; view/play count, caption/hashtags, duration and Post download |
| Instagram metadata fallback | yt-dlp Instagram extractor | Independent metadata-only fallback after non-access-related Instaloader parser failures |
| Instagram fallback downloader | gallery-dl | Optional third attempt if Instaloader and yt-dlp fail |
| Local deduplication and job state | SQLite | Persist source IDs, metrics, download status and SHA-256 fingerprints |

The detailed rationale and limitations are in [docs/NON_API_DISCOVERY_TOOLCHAIN.md](docs/NON_API_DISCOVERY_TOOLCHAIN.md).

## Instagram session setup

Anonymous Instagram metadata access is frequently incomplete. If you choose to use your own account, create a local session through Instaloader's interactive login flow:

```powershell
shorts-lm discover instagram-login --username YOUR_INSTAGRAM_USERNAME
```

This prompts locally for credentials/verification and stores the session at `.shortslm/instagram.session`. Never share that file or commit it. Then run discovery with:

```powershell
shorts-lm discover run --platform instagram --instagram-session-user YOUR_INSTAGRAM_USERNAME --instagram-session-file .shortslm/instagram.session --target-new 100 --min-views 1000000
```

A session may improve metadata access, but does not guarantee every Reel is accessible or that Instagram exposes a numeric view count. Stop if Instagram requests a challenge or blocks the account; do not bypass it.

## Important metric handling

- YouTube view_count is stored as the view metric where ytscrape returns it; capped detail enrichment uses ytscrape player metadata when search results omit the metric.
- Instagram video_view_count and video_play_count are stored as separate platform-native metrics. A play count is never relabeled as a view count.
- The graph discovery inventory can use a conservative lower bound from a rounded Instagram display label (for example, 1.2M); the record remains explicitly marked as an estimate.
- Rounded Instagram display values are kept as estimates with a conservative lower bound for threshold filtering. Their metric is still labeled estimated in the saved metadata and JSONL index.
- Missing metrics are unknown, not zero, and never pass the processing threshold.
- YouTube candidates come from ytscrape's dedicated Shorts search filter, plus bounded yt-dlp hashtag Shorts shelves and Shorts tabs for channels found through those surfaces.
- Query selection learns from prior query yield after cooldown; never-used queries remain an exploration pool.
- Only candidates with confirmed Shorts/Reels format and a platform-native qualifying discovery metric at or above 1,000,000 enter the eligible inventory. Processing applies its own exact-metric threshold by default; a merely short-duration or format-uncertain video does not qualify.
- Instagram search results are confirmed Reels when they came from a /reel/ search result and the resolved media is video. Profile/hashtag discoveries are candidates unless more source evidence is available.

## Current commands

Install on Windows PowerShell:

    py -3.11 -m venv .venv
    .venv/Scripts/Activate.ps1
    python -m pip install --upgrade pip
    pip install -e ".[dev,discovery,legacy-discovery,audio,vidtrace]" --upgrade

Install FFmpeg and ffprobe and ensure both are on PATH. The gallery-dl Instagram fallback is optional:

    pip install -e ".[instagram-fallback]"

Check dependencies:

    shorts-lm doctor

Discovery requires ytscrape, yt-dlp, Instaloader and DDGS. The doctor output checks ytscrape separately. Deno 2.3+ or Node.js 22+ is still recommended for yt-dlp YouTube media downloads.

### Phase 1 discovery reliability, coverage and runtime

YouTube search uses the Shorts-specific filter from the MIT-licensed [ytscrape](https://github.com/vsmutok/ytscrape) library. The discovery adapter consumes **only the first parsed search page**. It deliberately does not iterate ytscrape's lazy `SearchResults` iterator, because that iterator transparently fetches continuation pages. Media downloads remain a separate yt-dlp + FFmpeg stage.

The default discovery run now has a **180-second overall runtime budget**, visible per-query progress and short network requests. YouTube discovery uses a 6-second per-request timeout, zero retries and a 0.5-second minimum request interval. Search is capped at 20 first-page results per query by default. The run stops cleanly when its deadline is reached or the requested number of new qualifying IDs is found.

Optional YouTube detail enrichment has a separate 20-second wall-clock budget. `--metadata-enrichment-limit 40` is a maximum lookup count, not a requirement to perform 40 sequential requests. Any results already collected are still normalized, deduplicated and stored when the enrichment budget expires.

The query planner rotates a broad topic/language/region pool (including Hindi, Marathi, Kannada, Tamil, Telugu, Bengali, English, Spanish, Portuguese and Indonesian). SQLite records exact query/locale combinations. Instagram searches share the same overall deadline and use bounded DDGS/Instaloader request timeouts.

The JSON report records elapsed time, stop reason, YouTube first pages fetched, completed queries, network timeout/retry configuration and enrichment-budget exhaustion. It also records each platform's selection and execution state so intentional exclusion is not confused with zero indexed hits or provider failure. In `--platform all` mode, both selected platform stages are scheduled before final candidate evaluation while the shared deadline allows. See [Phase 1 Discovery Coverage and Provider Reliability](docs/PHASE_1_DISCOVERY_COVERAGE.md).

### Discover 100 new unique eligible candidates

```powershell
shorts-lm discover run --platform all --target-new 100 --min-views 1000000 --max-candidates 1500
```

Useful controls:
- `--max-search-queries 24`: YouTube query budget per run.
- `--instagram-max-search-queries 8`: DDGS query budget per run.
- `--query-cooldown-days 7`: avoid repeating the same query/locale within seven days.
- `--metadata-enrichment-limit 40`: maximum detailed YouTube lookups for missing metadata; also subject to `--enrichment-budget-seconds` (20 by default).
- `--max-runtime-seconds 180`: stop the full run cleanly after three minutes by default.
- `--results-per-query 20`: consume only this many results from the first page; no hidden continuation-page requests.
- `--youtube-request-timeout 6`: six-second per-request timeout, with retries disabled.
- `--enrichment-budget-seconds 20`: separate time budget for optional detail lookups.
- `--instagram-max-lookups 40`: cap individual Instaloader metadata fetches.
- `--seed 42`: optional reproducible query ordering. Omit it for a fresh random ordering.

YouTube only:

```powershell
shorts-lm discover run --platform youtube --target-new 100 --min-views 1000000 --max-search-queries 30 --max-runtime-seconds 180 --results-per-query 20 --metadata-enrichment-limit 40 --enrichment-budget-seconds 20
```

Instagram only:

```powershell
shorts-lm discover run --platform instagram --target-new 100 --min-views 1000000 --instagram-max-search-queries 8 --instagram-max-lookups 40 --instagram-timeout 8 --instagram-request-timeout 12
```

A result target is best-effort, not guaranteed. Search result ranking is biased, and only new unique IDs with a reported qualifying view metric count. Missing views remain unknown and never become zero or 1M+. The README and coverage guide distinguish this from platform-wide random sampling.

### Download candidates

Download confirmed candidates from the local SQLite inventory:

```powershell
shorts-lm discover download --limit 25 --min-metric 1000000 --output-dir data/private/acquired
```

### Batch-process YouTube Shorts and Instagram Reels

First populate the shared SQLite inventory from both platforms:

```powershell
shorts-lm discover graph-run --platform all --target-new 100 --min-metric 1000000
```

Then process a mixed batch:

```powershell
shorts-lm discover process --platform all --limit 10 --min-metric 1000000 --asr-model small --device cuda
```

The processor reads the existing SQLite inventory. It alternates between YouTube and Instagram candidates when both platforms have eligible videos, so the YouTube backlog cannot consume the entire batch first. Its summary shows selected, downloaded and processed counts separately for each platform. When Instagram counts are zero, run combined discovery again and check the Instagram discovery report; processing cannot create candidates that are not in the inventory.

Whisper and PaddleOCR prefer the RTX 3050 by default. Whisper uses the compact `int8_float16` CUDA compute type. OCR releases its model after the video batch stage so the two models do not need to occupy VRAM simultaneously. The actual engine names saved in each record include the device used. If CUDA libraries or GPU-enabled PaddlePaddle are unavailable, the existing adapters can fall back to CPU; the stage metadata will show that actual device.
The processor rhttps://github.com/Arhanpg/Shorts-Language-Model/pull/28/conflict?name=README.md&ancestor_oid=1518b9e2cabcd559ca465ab9027b5d9ed1c585d1&base_oid=573a028d05cae978311b0e73ef856514c8927a10&head_oid=899be4aa2d526a134b1a7e749021dcb76f9e14d8eads the existing SQLite inventory. It alternates YouTube and Instagram candidates when both platforms have eligible videos, so the YouTube backlog cannot consume the entire batch first. Its summary shows selected, downloaded and processed counts separately for each platform. When Instagram counts are zero, run combined discovery again and inspect the Instagram discovery report; processing cannot create candidates that are not in the inventory.

Whisper and PaddleOCR prefer the RTX 3050 by default. Whisper uses the compact `int8_float16` CUDA compute type. ASR and OCR run sequentially, and the VidTrace wrappers release model resources after each stage. Actual engine names saved with each item include the device used. If CUDA libraries or GPU-enabled PaddlePaddle are unavailable, a backend may fall back to CPU; the stage metadata will show the actual device.

Useful controls:
- `--platform all`: process both platforms (default); use `youtube` or `instagram` to restrict a run.
- `--limit 10`: total videos in the batch, shared across both platforms.
- `--min-metric 1000000`: minimum native views for YouTube or plays for Instagram.
- `--device cuda`: prefer NVIDIA CUDA for Whisper and PaddleOCR (default); `--device cpu` is an explicit fallback.
- `--device cuda`: prefer NVIDIA CUDA for Whisper and PaddleOCR (default); `--device cpu` is an explicit override.
- `--language hi`: optionally specify a language; omit it for automatic detection.
- `--dataset-manifest outputs/dataset/processed-videos.jsonl`: choose the JSONL output path.

Processing resumes from a downloaded MP4 when ASR/OCR fails. The SQLite database keeps per-video download and processing state, checksums, output paths, attempts and errors. Start with 10 videos, then 100 and 300 after checking transcript and OCR quality.

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

The Phase 1 analyzer remains the downstream processor for a local MP4:

    shorts-lm doctor
    shorts-lm analyze --input data/private/acquired/VIDEO.mp4 --output outputs/analysis.json

The laptop's RTX 3050 is used for local Whisper transcription and PaddleOCR where the CUDA runtimes are installed. Discovery, database operations, video decoding and frame sampling remain CPU-oriented. See [Windows RTX 3050 GPU setup](docs/GPU_SETUP_WINDOWS.md) before the first GPU batch.
The laptop's RTX 3050 accelerates local Whisper transcription and PaddleOCR when the NVIDIA CUDA runtimes and GPU-enabled PaddlePaddle are installed. Discovery, database operations, FFmpeg and video frame sampling remain CPU-oriented. See [Windows RTX 3050 GPU setup](docs/GPU_SETUP_WINDOWS.md) before the first GPU batch.

## Revised phases

1. Non-API discovery + SQLite — implemented.
2. Media acquisition + robust metadata/asset validation — implemented.
3. Batch multimodal processing using the existing analyzer and VidTrace ASR/OCR adapters — implementation in the current PR; validate locally on 10 → 100 → 300 videos.
4. Dataset QA, duplicate control and annotation.
5. Model bake-off and frozen baselines.
6. Cloud fine-tuning.
7. Quantized local deployment.
8. Controlled expansion with measured cost and data quality.

## Security and data safety

Never commit the discovery SQLite database, downloaded MP4s, Instagram session files, cookies, credentials, raw transcripts or private metadata reports. The .gitignore includes these local artifacts.

Instagram discovery uses ordinary browser navigation. A login prompt, account checkpoint or rate limit may prevent collection; the tool does not automate verification or bypass those restrictions.

## Tests

    ruff check src tests
    pytest -q

## Multimodal research and final master plan

The research-backed direction is documented here:

- [Global Master Plan — 24 November 2026](docs/GLOBAL_MASTER_PLAN.md)
- [Gemini Research Reconciliation and Independent Technical Review](docs/GEMINI_RESEARCH_RECONCILIATION.md)
- [Feature Extraction Specification](docs/FEATURE_EXTRACTION_SPEC.md)
- [Minimal Model Selection and Training Plan](docs/MODEL_AND_TRAINING.md)
- [Minimal Multimodal Evidence Architecture](docs/ARCHITECTURE.md)
- [Updated Implementation Roadmap](docs/ROADMAP.md)

The default feature-extraction path is local-first and requires no new developer API token. It reuses the existing ASR/OCR adapters, introduces a canonical PTS-aligned evidence timeline, and adds specialist models only after a measured quality/runtime/license gate. Optional Gemini reasoning and Sarvam Indic-ASR integrations are not required for baseline operation.

## India-focused creator catalogue

A separate India-specific discovery catalogue builder is available. See [India Creator Catalogue](docs/INDIA_CREATOR_CATALOGUE.md) for source provenance, diversity scope, build commands, and separate URL output paths. Run `python scripts/build_india_seed_catalogue.py` to generate up to 1,500 Indian Instagram accounts, 1,500 YouTube channels, and 1,500 multilingual hashtag candidates; actual creator counts are source-limited and reported without fabricated top-ups.

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
- [Instagram Discovery Operations](docs/INSTAGRAM_DISCOVERY_OPERATIONS.md)

## License

Apache-2.0. See LICENSE.

## Creator-graph discovery (new experimental engine)

The first-generation keyword-search pipeline remains available as a legacy path. The new experimental engine uses a persistent SQLite creator frontier and YouTube Shorts recommendation graph.

Install the primary non-API discovery dependency:

    pip install -e ".[discovery]"

For local Instagram browser observation:

    pip install -e ".[instagram-browser]"
    playwright install chromium
    shorts-lm discover instagram-browser-login

This command opens your installed Google Chrome as a normal desktop browser (not Playwright's bundled Chromium). Sign in and complete any CAPTCHA or account verification manually. The dedicated profile is stored under .shortslm/browser/instagram/ and is gitignored. After sign-in, close every Chrome window using that profile before starting graph discovery. The collector then opens the same profile through Playwright's installed Chrome channel. Never copy its contents into the repository or share the profile. If Chrome is installed in a non-standard location, pass --chrome-path "C:\\path\\to\\chrome.exe".

Run the YouTube graph harvester:

    shorts-lm discover graph-run --platform youtube --target-new 100 --min-metric 1000000 --max-runtime-seconds 240

Run Instagram creator and hashtag discovery from the checked-in starter files:

    shorts-lm discover graph-run --platform instagram --target-new 50 --min-metric 1000000

The default hashtag file is `data/instagram_hashtags.txt`. It includes seeds such as `getreadywithme`, `cricket`, `viratkohli`, `anirudh`, `comedy`, `dance`, `food` and `travel`. Hashtag pages are visited in the same manually authenticated Chrome profile as creator Reels tabs. Add repeated `--instagram-hashtag` options or edit the file. Use `--instagram-max-hashtags` to cap how many tags are visited in a run.

Example targeted hashtag-only smoke test (zero creator profiles):

    shorts-lm discover graph-run --platform instagram --instagram-seeds-file .shortslm/no-seeds.txt --instagram-hashtag getreadywithme --instagram-hashtag viratkohli --instagram-max-hashtags 2 --max-creators 0 --target-new 20 --max-runtime-seconds 240 --instagram-max-scrolls 6 --instagram-hashtag-max-reel-details 5

The collector reuses one persistent Chrome context for the run instead of starting a new browser for every creator. It gathers rendered Reel permalinks and observed JSON metadata, then visits a bounded sample of Reel detail pages when the metric is missing. Exact numeric WatchAction/ViewAction counts in public JSON-LD are accepted; abbreviated display labels are not converted into guessed integers. A Reel link with no numeric metric remains an unknown-metric candidate, not a million-play Reel.

The seed list is `data/instagram_creator_seeds.txt`. It includes vloggers, comedy/entertainment creators, technology creators and meme/publisher pages. It is a starting test corpus, not a guarantee that every account is active or that every Reel exceeds one million plays. Add one handle per line or pass extra `--instagram-creator @handle` values.

Force a fresh check of the supplied/default seed handles even if they were previously completed, empty, exhausted, failed or blocked:

    shorts-lm discover graph-run --platform instagram --force --max-creators 100 --max-runtime-seconds 900 --instagram-max-scrolls 12

Use `--force` when manually retrying a creator such as `taneja.gaurav` or `souravjoshivlogs`. It does not clear candidates or delete the database. It only requeues the selected seed handles.

Useful Instagram controls:
- `--instagram-hashtag getreadywithme`: add one or more live hashtag pages.
- `--instagram-hashtags-file data/instagram_hashtags.txt`: choose a different tag list.
- `--instagram-max-hashtags 8`: cap hashtag pages per run.
- `--instagram-max-reel-details 3`: inspect up to three metric-unknown Reel details per creator.
- `--instagram-hashtag-max-reel-details 8`: inspect up to eight metric-unknown Reel details per hashtag.
- `--max-creators 0`: run hashtag-only discovery.
- `--instagram-max-scrolls 8`: cap scrolling on each surface.

The report distinguishes candidate links, candidates with a numeric metric, candidates whose metric meets the threshold, and newly eligible inventory. A high candidate count alone is not evidence that videos were selected or that their metrics were verified. See [Instagram Discovery Operations](docs/INSTAGRAM_DISCOVERY_OPERATIONS.md).

Run both providers:

    shorts-lm discover graph-run --platform all --instagram-creator creator_handle

The graph engine is opt-in until repeated Windows runs validate real provider behavior. The first-generation `discover run` command is retained for comparison and requires the `legacy-discovery` extra. It preserves the existing SQLite inventory and does not download media. YouTube eligibility uses numeric views; Instagram eligibility uses an explicitly labeled numeric plays metric when that is what the browser payload provides. The two metrics are never relabeled as one another.

TubeScrape is pinned to 0.6.0 and uses YouTube's public web/InnerTube interface; it is not the official YouTube Data API. The engine uses channel Shorts tabs, related-Shorts sequences, bounded batch enrichment and persistent creator scheduling. A popular-sort label is not assumed to guarantee strict descending numeric views, so the initial engine does not use an unsafe first-below-threshold cutoff.

Instagram sign-in is performed in the user's installed Google Chrome outside Playwright automation. After the user closes Chrome, the collector reopens the same persistent profile through Playwright's Chrome channel and passively observes JSON responses and rendered Reel links generated by normal browser navigation. Each creator result records final URL, response counts, parsed/unparsed responses, Reel-link counts and an actionable zero-result reason. It does not replay captured requests, construct GraphQL calls, rotate identities, bypass checkpoints, or evade rate limits. Discovery and media acquisition are separate commands; batch processing downloads and processes selected candidates directly.

See [ADR-003](docs/ADR-003-CREATOR-GRAPH-DISCOVERY.md) and the [Creator-Graph Discovery Plan](docs/CREATOR_GRAPH_DISCOVERY_PLAN.md) for architecture, schema, terminology, metrics and phase gates.
