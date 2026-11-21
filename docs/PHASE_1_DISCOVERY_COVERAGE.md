# Phase 1 — Discovery Coverage, Query Rotation and Provider Reliability

**Status:** implementation on `feature/discovery-coverage-reliability`  
**Design date:** 21 November 2026  
**Scope:** unattended public-link discovery, metadata qualification and persistent deduplication. No MP4 download occurs in the `discover run` command.

## 1. What the user's latest runs demonstrate

The reported YouTube-only run returned 600 search records but only one new eligible item:

| Observed result | Interpretation |
|---|---|
| 600 raw search records | Search was returning pages, but did not provide 600 new candidate IDs |
| 592 unique IDs in the current run | A small number repeated within the same query batch |
| 453 already in SQLite | The current search phrases were mostly rediscovering inventory collected by previous runs |
| 177 format-uncertain | Generic search metadata did not provide enough evidence to classify a Short |
| 57 missing view metrics | The search-page extraction did not expose a numeric view count |
| 330 below 1M | Their observed count was genuinely below the requested threshold |
| 1 new eligible | Only one unseen ID passed both the threshold and the format/metadata checks |

The Instagram run exposed a different failure mode: Instaloader waited on GraphQL requests with its default 300-second timeout and three connection attempts. DDGS also used automatic backend selection; the user log showed a Yahoo timeout. That means a single discovery run can spend a long time on a failing search engine or post lookup without producing useful candidates.

The important distinction is that search hits, unique source IDs, qualifying view metrics and new eligible records are four different quantities. The revised system reports them separately and does not turn an old source ID into a “new” item just because another query found it.

## 2. Open-source projects evaluated

The search and metadata layer has been changed from generic yt-dlp search to a dedicated Shorts search provider.

| Project | Current inspected version / licence | Use in ShortsLM | Important limitation |
|---|---|---|---|
| [ytscrape](https://github.com/vsmutok/ytscrape) | v2.2.0, MIT | YouTube search using `SearchFilter.SHORTS`, typed view counts, duration, title/channel and paginated result objects | Uses YouTube's internal, undocumented InnerTube web endpoints; upstream changes or blocking can break it |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | existing optional tool | Media acquisition/downloading for sources where the exact item has explicit permission; also fallback Instagram extractor | Not used as the primary YouTube search engine after this change |
| [Instaloader](https://github.com/instaloader/instaloader) | v4.16 | Resolve indexed Instagram Reel shortcodes and read available post metadata; optional authenticated hashtag discovery | Public GraphQL fields can disappear or be throttled; a public search result does not guarantee metadata access |
| [DDGS](https://github.com/deedy5/ddgs) | v9.16.1 | Search engines for indexed public Instagram Reel URLs | Search engine index is incomplete and ranked; backend outages are possible |
| [gallery-dl](https://github.com/mikf/gallery-dl) / [Codeberg releases](https://codeberg.org/mikf/gallery-dl/releases) | optional fallback | Media downloader fallback only | Not an Instagram discovery catalogue |

### Why ytscrape is a better YouTube search fit

The project's source exposes a dedicated `SearchFilter.SHORTS` filter (the current implementation maps it to YouTube's Shorts search filter), rather than searching generic videos and trying to infer the format from missing aspect-ratio fields. The search result model exposes typed fields including:

- video ID and canonical URL;
- title, channel and channel ID;
- view count and rendered view-count text;
- duration and rendered publication-time text;
- thumbnail and a short description snippet.

Its result iterator supports pagination. The client has configurable request timeout, minimum interval and retry/backoff. ShortsLM reuses one client per language/region pair within each run rather than rebuilding a connection/context for every query.

**Endpoint distinction:** ytscrape does not use the official YouTube Data API v3 and does not require a Google API key. Its README states that it uses YouTube's internal/private InnerTube web endpoints and that they may change. This is not a platform-approved data API, a licence to download media, or permission to train on content. The project is pinned to the inspected major version range and must be rechecked before upgrades.

### Why the Instagram provider is deliberately conservative

Instaloader v4.16 exposes `request_timeout` and `max_connection_attempts` constructor settings. Its inspected source defaults were 300 seconds and three attempts. The discovery adapter now sets a 12-second timeout and one connection attempt, with HTTP 401/403/429 configured as fatal statuses.

DDGS v9.16.1 accepts a timeout and a comma-separated backend list. The discovery adapter uses:
- primary: `bing,brave,duckduckgo`;
- one fallback engine: `google`;
- default per-request timeout: 8 seconds;
- one indexed result page per query by default;
- a cap of 15 individual Instagram metadata lookups per run by default.

A provider circuit breaker stops further work after repeated metadata failures or rate-limit/login/timeout/connection conditions. The purpose is to make a run finish and report failure rather than wait five minutes repeatedly. A circuit-breaker stop is a deliberate safety/reliability decision, not proof that no additional Reels exist.

## 3. Revised architecture

```text
                    SQLite query history
                           |
                           v
              Locale/topic query planner
               |                      |
               v                      v
        YouTube Shorts search    Instagram index search
          (ytscrape)                   (DDGS)
               |                      |
               v                      v
       Typed search records     Indexed Reel URLs
               |                      |
               v                      v
       Search-result parse      Instaloader shortcode
               |                 metadata lookup
               |                      |
               +----------+-----------+
                          |
                          v
                Platform/source ID dedupe
                          |
                          v
                Existing-ID prioritization
                 new IDs first, known later
                          |
                 +--------+--------+
                 |                 |
                 v                 v
          Selective detail    Keep observed
           enrichment         search metadata
           (YouTube only)
                 |                 |
                 +--------+--------+
                          |
                          v
                Metric and format rules
                          |
                          v
               Persistent SQLite upsert
                          |
                          v
             JSON report and diagnostics
```

The discovery stage does not download videos. Download is a later command with an item-specific rights manifest. The data-access boundary is unchanged: discovering a public URL is not permission for persistent copying, analysis, derived-artifact retention or model training.

## 4. Query coverage and rotation

The old planner used a fixed list of twelve broad phrases. A fixed seed (the previous default was `42`) also repeated the same order on each run. That combination made later runs likely to revisit nearly identical result sets.

The new planner builds a larger pool across topics and language/region strata:

- English: India, United States and United Kingdom;
- Indian languages: Hindi, Marathi, Kannada, Tamil, Telugu and Bengali;
- additional language/region strata: Spanish/Spain, Portuguese/Brazil and Indonesian/Indonesia;
- categories: cricket/sports, comedy, memes, cooking, education, facts, technology, gaming, dance, music, fitness, travel, beauty, pets, science, motivation, storytelling and related niches.

Instagram indexed search uses a smaller region-aware pool, including India English/Hindi/Tamil/Telugu/Marathi/Kannada plus selected international regions.

Each query has a stable key derived from platform, normalized query text, language, region and strategy. SQLite stores:
- last use time;
- total times used;
- raw search results returned;
- usable candidate count.

At each run, the planner prefers never-used searches, then searches outside the configured cooldown, and only later revisits recently used queries. The default cooldown is seven days. The default selection is shuffled with a fresh random source; `--seed` is available only when a reproducible query order is required.

This is **coverage rotation**, not uniform random sampling of the whole platform. Search engines and YouTube's search page rank results, omit some videos and change their results over time. The system must not describe search results as a statistically representative platform-wide sample.

## 5. New versus known candidates

A candidate's stable uniqueness key is:

```text
(platform, source_id)
```

That identity is enforced by SQLite's primary key and checked before scoring the current run.

The revised run does the following:

1. Merge duplicate search appearances within the current run.
2. Keep the observation with the stronger known metric while preserving the source-query provenance.
3. Split returned candidates into IDs never seen before and IDs already in SQLite.
4. Evaluate unseen IDs first; evaluate known IDs afterwards so they can refresh incomplete metrics without taking the entire fresh-candidate budget.
5. Count an item toward `new_eligible` only when its platform/source ID was absent before this run and the current merged record passes the threshold and format conditions.
6. Report a known item that becomes eligible after enrichment separately as `known_ids_became_eligible`.

A YouTube video cross-posted on Instagram may have two different platform IDs. It is only guaranteed to be merged at the media stage once both copies are legally downloaded and a byte-level or perceptual-media comparison can be made. Discovery alone cannot infer identical media from different URLs with certainty.

## 6. Metadata completeness and selective enrichment

The YouTube Shorts search result is the cheap first pass. If its result already contains both a view count and duration, the system does not fetch more detail for it.

For new candidates missing either field, the provider can call ytscrape's detailed video lookup. This is capped by `--metadata-enrichment-limit` (default 40 per run) and uses the same locale-specific client, configured rate limiter and short retry policy. Enrichment is not attempted on every result and does not download the MP4.

A search result's rendered publication time may be an approximate relative date. It is stored as an estimate with its original text and must not be treated as a precise publication timestamp. View counts are observations at collection time, not immutable lifetime labels.

The 1,000,000-view threshold remains the default. The configured metric must be present and explicitly reported. Missing view counts remain unknown; an absent count is never converted to zero or treated as passing 1M.

## 7. Run controls

| Option | Default | Meaning |
|---|---:|---|
| `--target-new` | 100 | Stop after this many new unique eligible source IDs, if available |
| `--min-views` | 1,000,000 | Minimum observed view count |
| `--max-candidates` | 1,500 | Maximum unique source IDs to evaluate after search |
| `--results-per-query` | 50 | Requested results for each YouTube query; provider caps this at 50 |
| `--max-search-queries` | 24 | YouTube query budget for the run |
| `--instagram-max-search-queries` | 8 | Instagram DDGS query budget |
| `--query-cooldown-days` | 7 | Minimum age before a query is considered due again |
| `--metadata-enrichment-limit` | 40 | Maximum YouTube detail lookups for new incomplete candidates |
| `--instagram-max-lookups` | 15 | Maximum individual Instaloader post lookups |
| `--instagram-timeout` | 8 sec | DDGS request timeout |
| `--instagram-request-timeout` | 12 sec | Instaloader request timeout |
| `--instagram-pages` | 1 | Number of indexed result pages per phrase |
| `--seed` | random | Optional reproducible query-order seed |

### Recommended Windows PowerShell update and commands

After the PR is merged:

```powershell
git pull origin main
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,discovery,audio]" --upgrade
shorts-lm doctor
```

Test the YouTube provider first:

```powershell
shorts-lm discover run --platform youtube --target-new 100 --min-views 1000000 --max-search-queries 30 --metadata-enrichment-limit 40
```

Then test Instagram with its bounded search/lookup budgets:

```powershell
shorts-lm discover run --platform instagram --target-new 100 --min-views 1000000 --instagram-max-search-queries 8 --instagram-max-lookups 15 --instagram-timeout 8 --instagram-request-timeout 12
```

Then run both providers:

```powershell
shorts-lm discover run --platform all --target-new 100 --min-views 1000000 --max-candidates 1500
```

The existing `.shortslm/discovery.sqlite3` database is preserved. Query-history tables are created automatically when the upgraded program opens the existing database. Do not delete SQLite just to reset duplicate counts; it contains the source IDs that prevent repeated work.

## 8. What a healthy run should tell you

The report `outputs/discovery/latest.json` records:
- query keys selected and queries executed by platform;
- how many distinct queries exist in persistent history;
- raw search hits by platform;
- unique IDs in the current search results and repeats within the run;
- known versus unseen IDs;
- new eligible, already eligible and previously-known-now-eligible records;
- missing view metrics, below-threshold values and format uncertainty;
- YouTube detail enrichment attempted/succeeded;
- Instagram DDGS errors, post lookups, metadata failures and circuit-breaker reason;
- total provider errors and a sample of error messages.

The result should be judged by **new unique eligible IDs**, not by raw page hits. A run with 600 search results but 453 existing IDs and 330 below-threshold IDs is not a provider success merely because the search endpoint returned 600 rows.

A 100-new-item target is not guaranteed. No search library can guarantee 100 new public videos above 1M views on each run, particularly when an existing database has already captured many high-view items and search providers return ranked results.

## 9. Failure and access handling

- Do not rotate proxies, steal browser cookies, bypass login/CAPTCHA, or circumvent access controls.
- Stop or skip when a provider reports a block, login requirement, rate limit or persistent timeout.
- The Instagram circuit breaker limits repeated metadata requests when the account or network is failing.
- A provider that times out can return fewer results; the JSON report records this explicitly.
- Do not interpret provider failure as proof that the platform has no qualifying videos.
- ytscrape is an unofficial InnerTube client. Its endpoint and page parser can change; test it when upgrading and expect occasional source breakage.

## 10. Validation coverage

The automated suite covers:
- locale/topic query pool coverage and cooldown selection;
- query-history persistence in SQLite;
- ytscrape Shorts filter use, typed result parsing and per-locale client reuse;
- selective metadata enrichment limits;
- DDGS timeout/backend configuration and fallback behaviour;
- Instaloader timeout/attempt/status configuration;
- Instagram circuit-breaker behaviour after repeated metadata failures;
- duration and metadata normalization;
- source-ID and media-hash deduplication.

Live provider tests are intentionally not part of the deterministic unit suite. A real Windows run is still required because current platform responses, ISP/network conditions and public search index coverage cannot be simulated in GitHub Actions.

## 11. Research references and upstream source

- ytscrape repository (MIT; v2.2.0): https://github.com/vsmutok/ytscrape
- ytscrape Shorts filter implementation: https://github.com/vsmutok/ytscrape/blob/v2.2.0/src/ytscrape/filters.py
- ytscrape typed video result fields: https://github.com/vsmutok/ytscrape/blob/v2.2.0/src/ytscrape/models.py
- ytscrape search and pagination: https://github.com/vsmutok/ytscrape/blob/v2.2.0/src/ytscrape/youtube.py
- ytscrape retry, backoff and rate limiting: https://github.com/vsmutok/ytscrape/blob/v2.2.0/src/ytscrape/client.py
- Instaloader v4.16 constructor and request configuration: https://github.com/instaloader/instaloader/blob/v4.16/instaloader/instaloader.py
- DDGS v9.16.1 constructor/backend/timeouts: https://github.com/deedy5/ddgs/blob/v9.16.1/ddgs/ddgs.py
- yt-dlp media downloader: https://github.com/yt-dlp/yt-dlp
- gallery-dl optional fallback: https://github.com/mikf/gallery-dl

The external repository's MIT licence permits use subject to its notice terms. ShortsLM uses it as a dependency and does not copy its source. Its use of internal endpoints remains an upstream and platform-policy risk independent of the dependency's software licence.
