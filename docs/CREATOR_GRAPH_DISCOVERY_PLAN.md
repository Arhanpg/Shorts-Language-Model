# Creator-Graph Discovery — Implementation Plan

**Revision:** 1.0  
**Date:** 22 November 2026  
**Status:** Architecture approved for staged implementation; live-provider validation required  
**Decision:** No official YouTube Data API, Instagram Graph API, or Meta API.

## 1. Executive decision

Replace the first-generation stateless pipeline (keyword search → URL collection → per-item metadata lookup) with a persistent creator/video graph. The new engine uses YouTube Shorts surfaces and their recommendation sequence as the primary high-yield discovery path. Instagram discovery is a separate local-browser workflow that observes responses produced by a user-operated, logged-in Playwright browser.

This is a change in the discovery model, not another retry patch. The existing database and download/rights workflow are retained. The legacy `discover run` command remains available until the new engine has passed live Windows validation.

## 2. Terminology and data contracts

| Term | Definition |
|---|---|
| Seed query | A low-frequency topic/hashtag query used to find initial Shorts |
| Seed video | A confirmed Short used to start recommendation-graph expansion |
| Creator frontier | Persistent queue of creators whose Shorts/Reels surfaces have not been harvested recently |
| Expansion seed | A video whose related-Shorts sequence has not yet been traversed |
| Recommendation edge | Observed relationship between a source Short and a returned related Short |
| Harvest batch | One bounded creator-tab or recommendation-sequence retrieval |
| Candidate | A normalized video record, not yet necessarily eligible |
| Platform metric | The raw platform-specific count used for thresholding |
| Eligible-new yield | Newly inserted candidates meeting both format and metric rules |

Metric semantics are explicit:
- YouTube uses numeric `view_count` from detailed TubeScrape video metadata.
- Instagram retains raw `view_count` and `play_count` separately. An Instagram `play_count` may qualify as the platform's Reel plays metric, but it is never rewritten into the `view_count` column. Reports must label it as plays, not YouTube-style views.
- Approximate display counts (e.g. `ShortResult.views`) are hints for prioritizing enrichment, not final eligibility evidence.
- Missing or ambiguous metrics remain `metric_unknown`; no inferred counts.

## 3. Architecture

```text
                         SQLite persistent graph
   creator_frontier | expansion_seeds | creator_edges | candidates
                              |
              +---------------+----------------+
              |                                |
        Seed discovery                    Existing inventory
   TubeScrape Shorts search             Eligible historical Shorts
   sort_by=view_count                   and creator identities
              |                                |
              +---------------+----------------+
                              |
                    Async Discovery Engine
                 bounded request + time budgets
                              |
            +-----------------+------------------+
            |                                    |
      YouTube graph harvester              Instagram browser
      TubeScrape 0.6.0                     Playwright persistent
      popular channel Shorts              user-owned browser profile
      related Shorts sequence             passive response observation
      batch detail enrichment             Reels-tab pagination
            |                                    |
            +-----------------+------------------+
                              |
                 Normalize → qualify → deduplicate
                              |
              Persist candidates + observations + edges
                              |
               Adaptive frontier scheduling by yield
```

### YouTube path

1. Seed with curated search queries and hashtag Shorts (`aget_hashtag_shorts`), plus previously eligible local Shorts.
2. Use TubeScrape `search(type="short", sort_by="view_count")` as a seed finder, not as the main harvesting loop.
3. Resolve seed details in bounded batches and add confirmed Shorts to `expansion_seeds`.
4. Call `get_related_shorts` / `aget_related_shorts` on eligible seeds. This returns a small related-Shorts sequence with detailed video metadata; store each observed source→related edge.
5. Enqueue newly observed channel IDs in `creator_frontier`.
6. Harvest creator Shorts tabs with `get_channel_shorts(sort_by="popular")`. Use listed approximate counts only to prioritize detail enrichment.
7. Enrich selected IDs through `get_videos_info` / `aget_videos_info`, concurrency capped at five by default.
8. Revisit creators only after a cooldown; never repeatedly crawl an exhausted creator on every run.

**Cutoff safety:** The word “popular” is a platform ordering label, not a contractual guarantee of strict numeric descending view counts. The first implementation must not assume a globally monotonic sequence. It may stop early only after a configurable ordering-validation policy succeeds; otherwise it uses a hard per-creator scan cap and records why cutoff was disabled.

### Instagram path

1. Use a dedicated local Playwright Chromium profile under `.shortslm/browser/instagram/`.
2. The user signs in manually in the visible browser. No cookie export, cookie upload, or automated login.
3. Navigate to a creator's Reels tab and passively observe only JSON responses generated by that page.
4. Parse known Reel identifiers and raw metric fields (`view_count`, `play_count`, `video_play_count`) using defensive, fixture-tested parsing.
5. Treat response schema and metric availability as volatile. Unknown payloads are counted as unparsed, not guessed.
6. Expand only from explicit collaborator/co-author metadata. Caption mentions are lower-priority leads, not proof of collaboration.
7. If Instagram presents a login challenge, checkpoint, restriction, or rate limit, stop that creator/backend and ask for normal manual resolution. Do not bypass it.

The browser adapter is a local collector, not an endpoint client: it does not construct GraphQL requests, replay captured requests, rotate identities, or circumvent access controls.

## 4. Persistence and migrations

Additive SQLite tables:
- `creator_frontier`: platform, creator ID/handle, discovery provenance, priority, depth, status, lease, cooldown, failure count, last error.
- `expansion_seeds`: platform/video ID, source creator, graph depth, status, attempts, lease, last expansion time.
- `creator_edges`: observed creator/video relationships and provenance.
- `candidate_observations`: timestamped metric observations, metric kind/source, response evidence fingerprint, and run ID.

Keep `candidates`, `discovery_runs`, and download/rights tables. Migrations must be additive and tested against a copy of an existing database. Never delete or recreate the user's SQLite inventory.

## 5. Orchestration and reliability

- Async engine with bounded semaphores; initial YouTube detail concurrency: 5; recommendation expansion concurrency: 2; Instagram browser: one profile/context at a time.
- Separate per-request timeout from total run deadline.
- Circuit breaker is per backend and failure class. Explicit access/rate-limit/challenge signals stop that backend; they do not trigger a second scraper to evade the restriction.
- Transient transport failures use bounded retry with jitter; partial results are persisted.
- Creator leases prevent duplicate work and recover cleanly after process termination.
- Cooldown defaults are configurable (initial creator revisit: 14 days).
- A hard max request count, max creators, max expansions, max depth and total runtime prevent runaway graph traversal.
- Discovery never downloads media. Existing rights-manifest and acquisition controls remain separate.

## 6. Success metrics

Do not use query count as the primary coverage measure. Every run reports:
- new eligible candidates per request;
- new eligible candidates per creator harvest;
- new creators discovered per expansion seed;
- graph depth and unique nodes/edges;
- duplicate rate and database-overlap rate;
- metric availability and format-confirmation rate;
- enrichment calls per eligible candidate;
- per-backend latency, errors, cooldowns and stop reasons;
- popular-order validation result and early-cutoff reason;
- YouTube views and Instagram plays as separate metric series.

The initial quality gate is not “100 results in 180 seconds”. It is a reproducible increase in unique eligible-new yield without uncontrolled requests or data-quality regressions.

## 7. Dependency policy

- `tubescrape==0.6.0`: primary YouTube Shorts/channel/related-sequence adapter; pin exact version and contract-test methods.
- `ytscrape==2.2.0`: legacy provider only; the new graph engine does not use it as a fallback or as a way to evade TubeScrape access restrictions.
- `playwright`: optional `instagram-browser` extra; install Chromium separately.
- `ddgs` and `instaloader`: moved to `legacy-discovery`; not required by the new graph engine.
- `yt-dlp`: remains the separate authorized acquisition/downloader tool, not the discovery engine.

TubeScrape uses YouTube's web/InnerTube interface; it is not the official YouTube Data API. Platform changes may break it. No proxy rotation or access-control bypass is part of this design.

## 8. Delivery phases

| Phase | Deliverable | Exit criteria |
|---|---|---|
| 0 | ADR, data contract, additive frontier schema, migrations and fixtures | Existing DB migration tests pass; no inventory loss |
| 1 | TubeScrape provider contract + seed search + creator popular harvest | Contract tests pass; live smoke test returns exact metadata and creator IDs |
| 2 | Recommendation-graph expansion + persistent scheduling | Restart-safe frontier; no duplicate expansion; graph edges persisted |
| 3 | Playwright Instagram Reels collector | Manual login, response capture, parser fixtures, no cookie leakage |
| 4 | Unified async engine, adaptive budgets and run reports | End-to-end bounded run, reproducible yield metrics |
| 5 | Windows validation and legacy retirement decision | Multiple runs improve unique eligible yield; old command retained until proven |

## 9. Explicit non-goals

- Official platform APIs or API credentials.
- Downloading media during discovery.
- Scraping private accounts or content unavailable to the logged-in user.
- CAPTCHA/checkpoint bypass, proxy rotation, fingerprint spoofing, session farming, or rate-limit evasion.
- Assuming every creator or recommendation chain contains 1M+ content.
- Promising 100 new eligible results in a fixed runtime.
