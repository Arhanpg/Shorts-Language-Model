# ADR-003: Persistent Creator-Graph and Popularity-First Discovery

- **Status:** Accepted for staged implementation; production default remains unchanged pending live Windows validation
- **Date:** 22 November 2026
- **Supersedes:** the discovery-method decision in ADR-002
- **Official APIs:** explicitly excluded by project-owner decision

## Context

The first-generation system searched broad keywords, returned relevance-ranked candidate URLs, then resolved metadata one item at a time. The user's production runs returned hundreds of raw search records but almost no new eligible records. Instagram's search-engine-indexed URLs and anonymous per-post lookups were especially unreliable. The previous fixes improved error handling but did not change the low-yield discovery model.

## Decision

Adopt a persistent graph-harvesting architecture. YouTube uses TubeScrape's Shorts-specific search, channel Shorts tabs (popular ordering), related-Shorts sequence, and bounded batch metadata methods. Instagram uses a local, visible Playwright browser profile; the collector passively observes JSON responses produced by the user's own Reels-tab navigation. No official platform API is used.

The full terminology, data contracts, SQLite schema, runtime policy, success metrics and phase gates are specified in [CREATOR_GRAPH_DISCOVERY_PLAN.md](CREATOR_GRAPH_DISCOVERY_PLAN.md).

## Verified library contract

The inspected TubeScrape repository is [misterzaidxpy/tubescrape](https://github.com/misterzaidxpy/tubescrape), version 0.6.0, MIT. Its actual client exposes:
- `asearch(..., type="short", sort_by="view_count")`
- `aget_channel_shorts(..., sort_by="popular")`
- `aget_hashtag_shorts(...)`
- `aget_related_shorts(...)`
- `aget_videos_info(..., concurrency=5)`
- `aget_channel_about(...)`

It exposes async methods on `YouTube`; it does not export an `AsyncYouTube` class. TubeScrape uses YouTube web/InnerTube endpoints, not the official YouTube Data API. The package is alpha and pinned exactly so interface changes are visible in CI.

## Important correction to the proposal

A channel tab's `popular` sort must not be treated as a guaranteed globally monotonic numeric view-count ordering. The provider records ordering observations; early cutoff is disabled unless a validation policy passes. TubeScrape's `ShortResult.views` is an approximate integer derived from display text. It is only a prioritization hint. Final YouTube qualification uses detailed numeric `VideoInfo.view_count`.

Instagram's `play_count` remains a distinct raw metric. It is never written into `view_count`. The eligibility model may evaluate the platform-specific Instagram plays metric, but reports and stored records preserve the distinction.

## Safety and reliability constraints

- Playwright observes only responses created by normal browser navigation. It does not replay requests or construct private GraphQL calls.
- The user signs in manually; browser profile data remains local and is gitignored.
- Challenges, checkpoints, rate limits and access restrictions stop the affected backend. No bypass, identity rotation, or alternate scraper fallback to evade a block.
- Discovery does not download media. Rights authorization remains a separate gate.
- Existing SQLite inventory is preserved by additive migrations.

## Consequences

The old `discover run` path remains available as legacy while the new `discover graph-run` path is validated. New modules are isolated from the legacy CLI and provider implementation. The graph engine becomes the future default only after multiple real Windows runs demonstrate better unique eligible yield and stable data quality.
