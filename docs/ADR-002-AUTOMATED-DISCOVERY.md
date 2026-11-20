# ADR-002: Automated Discovery Without Unauthorized Media Scraping

- Status: accepted architectural constraint; provider implementation pending
- Date: 21 November 2026
- Supersedes: assumption that a generic browser crawler can find and download every public Reel/Short
- Related: Automated Discovery and Rights-Gated Media Acquisition

## Context

The project owner does not want to paste video URLs or manually download MP4s. The intended workflow is to discover 100–200 new unique videos per run, filter candidates by 1M+ views, keep a local deduplication history, acquire videos, retain metadata and train/prepare the model.

A browser agent or downloader can technically retrieve content from some pages. That technical capability does not mean the platform grants bulk scraping, media download, persistent storage or ML-training rights.

Official access paths are asymmetric:
- YouTube Data API v3 supports search and metadata/statistics retrieval, but its policies prohibit downloading/caching audiovisual copies without prior written approval and prohibit scraping YouTube applications.
- YouTube has a creator/rightsholder third-party AI-training opt-in. It is off by default, requires applicable rightsholder permissions and selected-company access.
- Instagram Business Discovery can retrieve data for known eligible public Business/Creator accounts, including Reel view_count. It does not create a universal catalogue of all public Reels.
- Meta Content Library is controlled research access. Its API is not a local media-download service.

## Decision

1. Implement a provider-pluggable discovery agent using documented APIs and approved research interfaces.
2. Persist provider-neutral candidate identity and discovery state in local SQLite, with per-field source retention deadlines and deduplication.
3. Make candidate discovery, media retrieval, media analysis, derived-artifact retention and model training separate permission capabilities.
4. Do not integrate arbitrary public YouTube/Instagram downloading as a default capability.
5. Use platform-authorized training delivery, creator-authorized original-file handoff, or a licensed dataset/vendor for raw media.
6. Use Playwright only for an approved UI workflow; never use it to replace a prohibited API or bypass technical controls.
7. If no approved media provider exists for a platform, permit metadata discovery where allowed, but mark the candidate metadata-only and do not process/train on media.
8. Define a run target of 100 or 200 new candidates, but return partial yields when quota, provider availability, eligibility or deduplication prevents the target.
9. Train in reproducible batches after dataset construction; do not update model weights once per incoming video.

## Why this is the correct engineering decision

It preserves the hands-off objective without building around brittle browser scraping, account cookies, downloader workarounds or assumed rights. It also allows new licensed providers to be added without rewriting the model and telemetry pipeline.

## Consequences

Positive:
- Local deduplication and resumable runs.
- Clear distinction between discoverable candidates and trainable media.
- Provider-specific retention/deletion enforcement.
- Better reliability than HTML scraping.
- A path to scale via contracts and official provider feeds.
- Reuse of Phase 1 telemetry after media is lawfully delivered.

Trade-offs:
- The system cannot promise 100 newly acquired Instagram MP4s per run from public sources.
- YouTube API search quotas limit discovery volume.
- A YouTube third-party training partnership requires application and creator opt-in.
- Meta research access is institution-gated and does not expose a general API download route.
- Long-term identity retention for public API records is constrained by platform policy.

## Rejected alternatives

### Generic Playwright crawler

Rejected as the default. It is fragile, search-index biased, and cannot override source access, download, storage or training terms.

### yt-dlp/gallery-dl as universal acquisition service

Rejected as the default. Open-source downloader support is not a rights grant and does not override platform restrictions. An approved downloader may be added for a source whose license explicitly permits that method.

### Permanent raw metadata/ID archive from public APIs

Rejected without a suitable retention basis. Local SQLite records have policy-aware expiry; durable deduplication is retained only where the source agreement permits it.

### Train as each video downloads

Rejected. Dataset QA, creator/time splits, reproducible batch scheduling and evaluation require collection and training to be separate stages.

## Revisit criteria

Revisit this decision when:
- YouTube approves the project/company as a third-party AI-training recipient and documents its delivery protocol;
- Meta provides an approved media-use/delivery agreement for the project;
- a licensed data vendor contract grants automated file delivery and ML-training rights;
- creator agreements and an automated creator upload/handoff channel are operational.
