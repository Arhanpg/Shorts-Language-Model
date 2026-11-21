# Non-API Discovery and Downloader Toolchain

**Updated:** 21 November 2026  
**Current discovery implementation:** `feature/discovery-coverage-reliability`

This document describes the open-source tools used by ShortsLM. No YouTube Data API key, Instagram Graph API token or Meta app is used by the discovery command. YouTube search uses an open-source client for internal website endpoints; this is not the official Data API.

## 1. Selected projects

| Project | Role | Licence / note |
|---|---|---|
| [ytscrape](https://github.com/vsmutok/ytscrape) | Primary YouTube Shorts search and metadata | MIT; inspected v2.2.0; uses internal InnerTube web endpoints |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | YouTube media download; fallback Instagram extractor | Open-source downloader; EJS/JS-runtime requirements apply to current YouTube downloads |
| [DDGS](https://github.com/deedy5/ddgs) | Search public web index for Instagram Reel URLs | Search aggregator; not a complete Instagram catalogue |
| [Instaloader](https://github.com/instaloader/instaloader) | Resolve Reel shortcode and read public post metadata; primary Instagram downloader | Per-post metadata fields may be unavailable or blocked |
| [gallery-dl](https://github.com/mikf/gallery-dl) / [Codeberg](https://codeberg.org/mikf/gallery-dl) | Optional Instagram media downloader fallback | Not used for global Reel discovery |
| SQLite | Persistent identity, query history and job database | Built into Python; local database is gitignored |

## 2. YouTube: dedicated Shorts search

The generic yt-dlp `ytsearchN` path is no longer the primary discovery path. In the user's earlier run, generic search returned many old IDs and incomplete format evidence:
- 592 IDs from 600 search records;
- 453 IDs already in SQLite;
- 177 format-uncertain;
- 57 missing view metrics;
- only one new eligible ID.

The revised provider uses `ytscrape.YouTube.search(..., filter=SearchFilter.SHORTS)`. The v2.2.0 source defines a dedicated `SearchFilter.SHORTS` option, a paginated `SearchResults` iterator, a typed `Video` model and configurable client timeout/retry/rate-limit settings.

Search results can expose:
- video ID, title, channel/channel ID;
- view count and rendered view text;
- duration;
- publication-time text and approximate parsed datetime;
- thumbnails and description snippet.

The discovery adapter uses one client per language/region pair per run. It uses a bounded timeout, one retry and a minimum interval between requests. A capped second pass calls the provider's detail method for a limited number of new candidates whose search result is missing a view count or duration. This is a metadata lookup only; it does not download the media.

**Important endpoint distinction:** ytscrape does not use the official YouTube Data API. It calls YouTube's internal/private InnerTube web endpoints. These can change, return different results or be blocked. The MIT software licence permits use of the client code, but does not grant rights to underlying YouTube videos or guarantee platform permission for a particular data-collection purpose. Do not bypass consent screens, CAPTCHA, login or rate limits.

For actual MP4 download, the separate Phase 2 downloader still uses yt-dlp/FFmpeg where the item-specific rights gate allows it. Full YouTube media extraction may require yt-dlp EJS scripts and Deno 2.3+ or Node.js 22+; this is a downloader prerequisite, not a ytscrape search prerequisite.

## 3. Instagram: indexed URL search plus bounded metadata lookup

There is no selected open-source tool that guarantees a complete, global public Reel catalogue. ShortsLM uses two separate steps:

1. DDGS searches public web indexes for `site:instagram.com/reel/` results using topic and language variants.
2. Instaloader resolves a result shortcode and reads the metadata fields that Instagram currently exposes.

The provider defaults are deliberately bounded:
- primary DDGS backends: `bing,brave,duckduckgo`;
- one fallback engine: `google`;
- DDGS timeout: 8 seconds;
- indexed result pages per query: 1;
- Instaloader request timeout: 12 seconds;
- Instaloader connection attempts: 1;
- individual metadata lookups per run: 40;
- consecutive metadata or DDGS failures open a circuit for the remainder of that run.

The inspected Instaloader v4.16 constructor defaults were a 300-second request timeout and three connection attempts. Those defaults caused the long wait shown in the user's terminal logs, so ShortsLM overrides them.

Instagram metric handling remains explicit:
- `video_view_count` is stored as `view_count`;
- `video_play_count` is stored separately as `play_count`;
- play_count is only eligible when the explicit `--instagram-use-play-count` option is supplied;
- missing counts remain unknown and never pass the 1M threshold.

A public search index entry does not guarantee that Instaloader can read its metadata. A page may be deleted, restricted, login-gated, rate-limited or unavailable to the current network. The provider now stops after repeated failures instead of spending five minutes per attempt or flooding output.

## 4. Query rotation and deduplication

The query pool spans categories, languages and regions. Each exact combination of platform, query text, language, region and query strategy gets a stable hash key. The SQLite `discovery_queries` table stores last-used time, number of uses, search hits and usable candidate count.

Each run:
1. selects never-used query keys first;
2. selects queries outside the default seven-day cooldown next;
3. only then revisits the least recently used searches;
4. randomizes ordering by default; `--seed` is optional for a reproducible experiment;
5. collapses repeated records by `(platform, source_id)`;
6. processes unseen IDs before previously known IDs.

A new item is defined by a platform/source ID absent from the local database before the current run. Merely finding an already-known video through a different query does not count as new. Cross-platform re-encodes are not guaranteed to be detected before downloading; SHA-256 detects identical downloaded bytes later.

Search engines rank and filter their result sets. Query rotation improves coverage but does not create a uniform random sample of YouTube or Instagram.

## 5. Installation

From Windows PowerShell in the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,discovery,audio]" --upgrade
shorts-lm doctor
```

The `discovery` extra installs ytscrape, yt-dlp with its default extras, Instaloader and DDGS. FFmpeg/ffprobe must be installed separately and available on PATH. For YouTube video downloads, install Deno 2.3+ or Node.js 22+.

## 6. Recommended run commands

```powershell
# YouTube Shorts only
shorts-lm discover run --platform youtube --target-new 100 --min-views 1000000 --max-search-queries 30

# Instagram indexed link discovery + bounded metadata
shorts-lm discover run --platform instagram --target-new 100 --min-views 1000000 --instagram-max-search-queries 8 --instagram-max-lookups 40 --instagram-timeout 8 --instagram-request-timeout 12

# Both providers
shorts-lm discover run --platform all --target-new 100 --min-views 1000000 --max-candidates 1500
```

Do not delete `.shortslm/discovery.sqlite3` between runs. It holds source IDs that prevent repeat work and query keys that rotate coverage. Query-history tables are created automatically when the revised program opens the existing database.

## 7. What the reports measure

The report separates:
- raw search hits by platform;
- queries executed and query-history size;
- repeated IDs in the current run;
- IDs already in SQLite;
- new eligible IDs, known IDs newly eligible and already eligible IDs;
- missing view metric, below-threshold view count and uncertain format;
- YouTube metadata enrichment attempts/successes;
- Instagram metadata lookups/successes/failures, DDGS errors and circuit-breaker reason.

A target of 100 is best-effort. It is not a promise that 100 new videos above 1M views exist in the search result pool for that run. The raw search count is not the success metric; new unique eligible IDs are.

## 8. Media acquisition and rights boundary

The `discover run` command does not download media. The separate `discover download` command still requires a private item-specific rights-manifest entry. A publicly accessible link or an open-source downloader does not grant permission for media retrieval, persistent storage, analysis, derived-artifact retention or model training. No private media, cookies, credentials, session files, raw videos or non-redistributable artifacts may be committed to this repository.

See [PHASE_1_DISCOVERY_COVERAGE.md](PHASE_1_DISCOVERY_COVERAGE.md) for the detailed architecture, research notes, limits, test coverage and troubleshooting guide.
