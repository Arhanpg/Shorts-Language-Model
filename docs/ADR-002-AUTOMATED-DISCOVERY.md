# ADR-002: Use Open-Source Search and Extractors for Non-API Discovery

- **Status:** supersedes previous API-first discovery decision
- **Date:** 21 November 2026
- **Chosen by:** project owner
- **Implementation:** feature/non-api-discovery-ytdlp-instaloader

## Context

The previous PR #5 plan proposed YouTube Data API and Instagram Graph API discovery. The project owner explicitly rejected that direction and requested open-source GitHub tools which can search links and download the media locally.

## Decision

Use:
1. yt-dlp search extractor and downloader for YouTube;
2. DDGS public web search for Instagram Reel links;
3. Instaloader for Instagram shortcode metadata, view/play metrics, optional hashtag/profile expansion and primary media downloading;
4. yt-dlp Instagram extractor as secondary downloader;
5. gallery-dl as optional third downloader;
6. local SQLite for source-ID uniqueness and job state;
7. SHA-256 for exact cross-platform file deduplication.

No official YouTube/Instagram/Meta platform API credentials are used by the discovery commands.

## Why this stack

yt-dlp offers an integrated YouTube search and download path, avoiding a separate YouTube link-harvesting API. DDGS supplies public indexed Reel URL search; Instaloader resolves the Reel shortcode and exposes available post metadata and download support. gallery-dl provides an optional alternate extractor if the primary route is unavailable.

There is no open-source tool here that guarantees a complete global index of every public Instagram Reel. Search engine indexes are ranked and incomplete. Instaloader can be throttled or require a normal local session. All extractors can break as upstream sites change.

## Permission and reliability boundary

The toolchain's ability to download a URL is a technical capability, not proof of ownership, license or model-training permission. Downloading/training is separated from discovery by an item-specific local rights manifest. It requires retrieval, analysis, temporary processing, derived artifact retention and model-training scopes. The code validates the record but cannot authenticate underlying consent. Keep rights evidence private.

Do not bypass login, CAPTCHA, challenge pages, DRM, technical controls or rate limits. The system does not scrape browser cookies or rotate proxies to evade restrictions. A blocked source is logged/skipped.

## Consequences

Positive:
- No platform developer API keys or quotas are part of the chosen discovery workflow.
- Search and extractor packages are open source.
- Automated local persistence and source-ID deduplication.
- YouTube and Instagram use separate providers with independent failure reporting.
- Exact byte duplicates are detected after download.

Trade-offs:
- Search result coverage is incomplete and biased.
- Instagram may require the owner's own Instaloader session for some query modes.
- Some Instagram metrics are absent; missing counts remain unknown.
- Extractors may stop working after upstream changes.
- 100/200 new high-view candidates per run is a best-effort target, never guaranteed.
- SHA-256 only catches exact byte duplicates, not re-encoded near-duplicates.

## Revisit criteria

Reassess when upstream extractor support breaks, the search source no longer returns useful Instagram pages, or near-duplicate leakage materially affects the dataset. Any alternative must preserve provider-neutral schemas, local deduplication and rights metadata.
