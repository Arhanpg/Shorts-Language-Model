# Automated Discovery and Rights-Gated Media Acquisition

**Research checked:** 21 November 2026  
**Status:** accepted architecture proposal; provider implementation not yet started.

## 1. Objective and system boundary

The project owner should not have to paste individual URLs or manually download MP4 files during normal operation. Build an automated Discovery Agent that searches configured sources, filters candidates, stores them in a local SQLite inventory, prevents repeats within the source's lawful retention period, and queues media acquisition only through an authorized delivery provider.

The system must separate these facts:

1. A video is discoverable.
2. A metadata record and view-count observation are available.
3. The media file can lawfully be retrieved.
4. The media can be analyzed and derived artifacts retained.
5. The media and derived examples may be used for model training.
6. The resulting trained weights may be redistributed.

None of these permissions should be inferred from another. A public URL and a million views do not grant download or training permission.

A candidate may be stored as metadata-only or delivery-unavailable. It is not sent to the media processor or training dataset until its required rights and delivery checks pass.

## 2. Platform capability matrix

| Source | Discovery | 1M+ metric | Raw media delivery | Role |
|---|---|---|---|---|
| YouTube Data API v3 | Video search and metadata, within quota | Yes, from current statistics response | No general MP4 download right | Candidate metadata discovery |
| YouTube third-party AI-training program | Eligible creator/rightsholder opt-in | Eligibility can be checked by video ID | YouTube may share eligible content with an approved selected company; exact handoff is program-dependent | Potential approved training source |
| Instagram Graph API Business Discovery | Eligible public Business/Creator accounts whose usernames are known | Reel view_count is documented through Business Discovery | Not a global arbitrary-Reel download API; media_url can be omitted | Narrow professional-account discovery |
| Instagram hashtag API | Limited hashtag discovery | Do not assume view_count is exposed | No general training-media grant | Topic discovery only |
| Meta Content Library/API | Controlled research access, subject to eligibility | Product-specific research filters | API data cannot be downloaded from the API/cleanroom | Institutional research |
| Licensed provider/dataset | Provider-specific API or catalogue | Depends on contract/feed | Yes only when license permits delivery and ML training | Scalable media source |
| Creator-authorized media inbox | Automated upload/drive handoff | Creator-authorized snapshots | Yes within the explicit creator/license grant | Reliable media/training source |

**Important conclusion:** there is no single unrestricted official API that discovers every public YouTube Short and Instagram Reel and returns a downloadable MP4 for model training. YouTube metadata discovery is feasible. Instagram discovery is narrower unless the project obtains approved research access or works from known eligible professional accounts. Neither access path creates universal download rights.

## 3. YouTube provider

### 3.1 Metadata discovery

Use the official YouTube Data API v3, not HTML scraping.

The provider should:
- create seeded, stratified search queries across language, region, topic and publication window;
- call search.list with video-only results and supported region/language/date filters;
- batch-enrich IDs with videos.list fields for title, description, tags, duration and statistics;
- preserve raw title/description separately from extracted hashtags;
- filter the current view-count observation at the configured threshold (default 1,000,000);
- record the observation timestamp and metric source;
- construct a canonical Shorts URL for navigation while keeping source identity only as long as its retention rules allow.

Published default quota documentation describes a separate 100-call/day search.list bucket and 10,000 quota units/day for other standard methods. A search call can return up to 50 results. This is not a guarantee of 5,000 new useful Shorts or 100 new 1M+ candidates per run.

### 3.2 Shorts classification

Do not label every video shorter than three minutes as a Short. YouTube's current help guidance says that standard-channel square or vertical videos uploaded on/after 15 October 2024 and up to three minutes are categorized as Shorts. Duration alone does not prove the format. Store short_format_status as confirmed, candidate or unknown. Confirm aspect ratio and upload-date eligibility only where a permitted source exposes the evidence.

### 3.3 API metadata retention and derived metrics

For non-authorized API data, YouTube's developer policies generally require temporary data to be refreshed or deleted within 30 calendar days. A June 2026 additional-derived-metrics policy provides a longer retention path for specific statistical data and approved derived metrics for audited developers who explicitly accept the applicable amendment for an approved analytics use case. Other fields, such as titles, creator names and descriptions, remain subject to the shorter refresh/deletion requirements.

The application must attach provider-specific retention and refresh deadlines to fields, not apply one indefinite retention rule to the whole candidate record. The standard policy restricts aggregation and derived metrics. Do not enable YouTube creator-normalized performance calculations until the project has accepted the required amendment and confirmed that the proposed use is in scope.

Hashing a video ID does not automatically remove source retention obligations. The deduplication ledger must respect the same source-specific limits.

### 3.4 Media delivery

The Data API does not supply the MP4. Do not fall back to scraping or an unofficial downloader.

The first route to investigate is YouTube's third-party AI-training program. Creator/rightsholder opt-in is off by default; all applicable rights holders must consent; creators select approved third-party companies. YouTube may share eligible content with a selected company, and companies may apply to be included in that selection list.

This requires project/company acceptance, creator/rightsholder opt-in and a documented asset-delivery protocol. It is not a generic public download endpoint and does not authorize yt-dlp against arbitrary videos.

## 4. Instagram / Meta provider

### 4.1 Instagram Graph API Business Discovery

Instagram Media endpoints are scoped to professional accounts. Business Discovery can inspect eligible public Business/Creator accounts when their usernames are known and the app has the required token and permissions.

For Reels, view_count is documented through Business Discovery. Meta notes that this count may include paid and cross-posted activity. The media_url field may be omitted for copyrighted or flagged media. Preserve the source metric definition; do not treat it as directly interchangeable with YouTube views.

The standard Graph API is not a global index of every public Reel. Hashtag search is narrower; do not assume it returns Business Discovery's view_count field.

Implementation approach:
- maintain an approved seed list of eligible public professional-account usernames;
- query Business Discovery and paginate within API limits;
- normalize Reel metadata and source metric definitions;
- filter the current view-count snapshot;
- record the username seed source and discovery query;
- mark a candidate metadata-only unless a separate authorized media-delivery route exists.

### 4.2 Meta Content Library

Meta Content Library/API is a controlled research product for eligible researchers affiliated with qualified academic or not-for-profit research institutions, subject to application and review.

The API operates in a secure research environment. Meta says API data cannot be downloaded from the API, including from the Secure Research Environment. The web interface has a separate downloadable subset for approved researchers and permitted content types; that is not a universal MP4 training feed.

This route may support institutional research discovery, but it does not solve local video delivery by itself.

## 5. Browser agent and downloaders

Playwright may automate a specifically approved interface, for example:
- navigating an approved research UI;
- exporting a dataset subset where the interface and agreement permit it;
- automating a creator's own connected-account workflow;
- checking a licensed provider's approved handoff or job status.

It must not be used to:
- scrape YouTube/Instagram pages instead of documented APIs;
- bypass login, CAPTCHA, rate limits, robots rules or technical protections;
- use logged-in cookies to evade access rules;
- extract hidden media URLs or circumvent DRM;
- bulk-copy arbitrary public platform videos.

The browser agent is an orchestrator, not a policy bypass. API connectors should handle normal discovery; browser automation is optional and restricted to approved UI tasks.

yt-dlp and similar projects are media transport software. Their ability to parse a URL does not grant download, retention or model-training rights. Keep them out of the default public-platform path. A downloader can be added only for a source/item whose contract explicitly authorizes that method.

## 6. Rights-aware delivery providers

Use one provider interface, but enable only providers with a real authorized delivery route.

| Provider adapter | Input | Output | Required evidence |
|---|---|---|---|
| youtube_training_share | Video ID and approved opt-in state | Platform-authorized training asset/handoff | Project approval, applicable rightsholder opt-ins, program delivery terms |
| creator_media_inbox | Signed upload or creator-authorized cloud-drive handoff | Original media and rights record | Creator grant for analysis, processing, derivatives and model training |
| licensed_dataset | Dataset/item manifest | Media file and provenance | Item-level license explicitly allows required use |
| instagram_creator_handoff | Creator-authorized original media | Original file and rights record | Creator and third-party/music rights |
| meta_research | Approved research workspace | Analysis in approved environment | Institutional access and cleanroom rules; no API download |
| youtube_public_metadata | Video ID | Metadata candidate only | API policy; no media retrieval right |
| instagram_business_discovery | Professional-account username | Metadata candidate; media URL only if returned | App permissions and separate use rights |

Each item needs independent scopes for metadata read, identifier retention, media retrieval, media analysis, temporary processing, raw retention, derived-artifact retention, model training and redistribution.

## 7. Local SQLite inventory

Use SQLite on the laptop first. It is appropriate for a single-user discovery/job ledger. Migrate only if concurrent workers or data volume later justify a server database.

Proposed tables:

| Table | Purpose |
|---|---|
| discovery_runs | Run ID, provider, query-plan version, start/end, target, yield and quota use |
| source_items | Platform/provider item ID, URL, first/last seen, state and dedup key |
| metadata_snapshots | Title/caption, description, hashtags/tags, duration, view/like/comment snapshot, metric definition and observed time |
| rights_records | Evidence reference, capability flags, agreement, permission version, expiry and revocation |
| media_assets | Authorized private path/URI, checksum, size, codec, delivery provider and retention |
| jobs | Queued/downloading/processing/complete/failed/blocked state, retries and last error |
| provider_state | Pagination cursor, query cells, quota and rate-limit state |

Use a unique source identity key while the source's policy permits retaining it. After an authorized media delivery, compute SHA-256 and, where lawful, perceptual video/audio fingerprints to detect cross-platform reposts.

### Retention-safe uniqueness

The local database can prevent repeats while the source identity or fingerprint can lawfully be retained. For assets covered by a durable training license, a durable dedup record may be kept if the contract permits it. For non-authorized public YouTube API records, source retention rules still apply. Do not promise lifetime non-repetition for data that must later be deleted or refreshed.

## 8. Discovery run behavior

Planned CLI shape (not implemented yet):

    shorts-lm discover run --platform all --target-new 100 --min-views 1000000 --max-candidates 1500

Each run:
1. loads enabled providers and checks credentials/permissions without printing secrets;
2. creates a seeded query plan across language, region, topic and publication windows;
3. queries each provider within quotas and rate limits;
4. normalizes records into a provider-neutral schema;
5. filters by current metric and short-format confidence;
6. checks the local dedup ledger;
7. stores permitted metadata and retention deadlines;
8. checks media acquisition and model-training rights separately;
9. queues only assets with a verified delivery route;
10. reports new candidates, duplicates, below-threshold items, format uncertainty, metadata-only records, media-authorized assets, training-authorized assets, quota use and partial-target reasons.

Default target is 100 new candidates; 200 can be selected. The target is not guaranteed. If source quotas, provider access, view threshold or deduplication prevent the target, return the actual yield and reason rather than retry indefinitely.

“Random” means randomized order across declared strata. Search results are ranked/indexed and cannot be called a uniform sample of every platform video. Record query cells and sampling decisions so bias can be measured.

## 9. Metadata and media processing

For candidates whose media is lawfully delivered:
- retain title/caption, description, tags/hashtags and metric snapshot with source and observation time;
- parse hashtags separately without overwriting original source text;
- use official captions/transcript only where permitted and available;
- otherwise run the existing faster-whisper/ASR pipeline on the delivered file;
- run OCR, keyframe selection, shot/cut candidates, motion and audio features;
- write checksums and extractor/model versions to the evidence manifest.

Instagram may expose a caption rather than a distinct title. Instagram view-count semantics may include paid/cross-posted activity. Keep the platform metric definitions separate.

Do not update model weights after every arriving video. Build a versioned, quality-checked dataset and fine-tune in reproducible batches with checkpoints. Per-video online updates are order-dependent and complicate leakage control and evaluation.

## 10. Technology choices

| Concern | Choice | Reason |
|---|---|---|
| YouTube metadata | YouTube Data API v3 with google-api-python-client or httpx | Documented metadata/search route |
| Instagram professional metadata | Instagram Graph API Business Discovery | Narrow official account discovery |
| Institutional research | Meta Content Library | Controlled research source |
| Browser automation | Playwright, optional | Approved UI workflows only |
| Local database | SQLite, optionally SQLAlchemy | Persistent local dedup/job ledger |
| Data schemas | Pydantic | Provider-neutral validation |
| Scheduling | CLI and resumable worker first; Prefect later if needed | Avoid premature orchestration complexity |
| Media delivery | Provider-specific signed/download adapters | No generic scrape-and-download fallback |
| Media analysis | Existing ShortsLM/VidTrace/FFmpeg components | Reuse telemetry |
| Model training | Transformers/PEFT or a compatible framework on rented GPUs | Reproducible batch training |

## 11. Acceptance tests

Before a 100-candidate batch:
- provider mock records normalize to one versioned schema;
- every candidate has source, observation time, metric definition and retention deadline;
- replaying the same provider page creates zero duplicate rows;
- a second run selects unseen items while dedup records remain valid;
- expired metadata is refreshed or deleted according to provider policy;
- view_count below 1,000,000 is rejected; missing view count is unknown, not zero;
- YouTube short-format candidates with unknown aspect ratio remain unconfirmed;
- Instagram hashtag results are not assigned a Business-Discovery-only view_count field;
- media acquisition is blocked when permission is missing;
- quota/provider outage returns a partial report without infinite retries;
- no secrets, cookies, video files, transcripts or database are committed to GitHub.

## 12. Official source links

- YouTube Data API overview and quota: https://developers.google.com/youtube/data/getting-started
- YouTube search.list: https://developers.google.com/youtube/v3/docs/search/list
- YouTube videos.list: https://developers.google.com/youtube/v3/docs/videos/list
- YouTube developer policies: https://developers.google.com/youtube/terms/developer-policies
- Additional derived metrics and storage: https://developers.google.com/youtube/terms/derived-metrics-policy
- YouTube third-party AI training opt-in: https://support.google.com/youtube/answer/15509945
- Three-minute Shorts eligibility: https://support.google.com/youtube/answer/15424877
- Instagram Media endpoint: https://developers.facebook.com/docs/instagram-platform/reference/instagram-media/
- Instagram IG User / Business Discovery: https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/
- Instagram Graph API rate limits: https://developers.facebook.com/docs/graph-api/overview/rate-limiting/
- Meta Content Library/API overview: https://developers.facebook.com/docs/content-library-and-api/content-library-api/overview
- Meta Content Library access: https://developers.facebook.com/docs/content-library-and-api/get-access
- yt-dlp project: https://github.com/yt-dlp/yt-dlp
