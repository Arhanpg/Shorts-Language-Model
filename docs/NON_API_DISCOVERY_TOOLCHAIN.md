# Non-API Discovery and Downloader Toolchain

**Decision date:** 21 November 2026  
**Implementation branch:** feature/non-api-discovery-ytdlp-instaloader  
**Purpose:** remove the previous official-platform-API-first approach from the acquisition workflow. Discovery uses public web search and open-source extractor repositories. No YouTube Data API key, Instagram Graph API token or Meta app is used by these commands.

## 1. Selected open-source projects

| Project | Repository / docs | Role in ShortsLM | Notes |
|---|---|---|---|
| yt-dlp | https://github.com/yt-dlp/yt-dlp | YouTube search, metadata extraction and MP4 download; also a secondary Instagram extractor | Supports ytsearchN:query; site support can break as platforms change |
| Instaloader | https://github.com/instaloader/instaloader | Instagram Reel shortcode metadata, view/play counts, hashtag/profile post iteration and primary Reel download | Post.video_view_count and Post.video_play_count are separate fields; hashtag discovery requires login |
| DDGS | https://github.com/deedy5/ddgs | Search public web index for Instagram Reel links | Searches indexed web pages; it is not Instagram's official API and does not guarantee complete results |
| gallery-dl | https://github.com/mikf/gallery-dl (active development: https://codeberg.org/mikf/gallery-dl) | Optional secondary Instagram media extractor/download fallback | Useful alternate extractor; project development has moved from GitHub to Codeberg |

### Why these choices

**YouTube:** yt-dlp already contains YouTube's search extractor and supports the ytsearch prefix. The same package handles the returned video URL and writes the local media file; no platform developer key is required.

**Instagram:** there is no single open-source tool with guaranteed global Reel search and download. The implemented combination first searches public indexed pages for instagram.com/reel/ links through DDGS, then resolves each shortcode through Instaloader. Instaloader exposes caption, caption hashtags, video duration, view count and play count, and can download a Post object. Hashtag/profile paths can expand discovery when a user session is available.

**Fallbacks:** the Instagram download order is Instaloader → yt-dlp's Instagram extractor → gallery-dl. Extractor compatibility is not guaranteed. The report retains failures rather than silently inventing candidates.

## 2. Actual capabilities and limits

### YouTube

- Search runs with yt-dlp's ytsearchN:search phrase extractor.
- Metadata such as title, description, duration, upload date, dimensions, tags and view count is captured when returned.
- A candidate is confirmed as short when a Shorts URL is returned or metadata supports a square/vertical format and the duration/upload-date rule.
- For standard channels, the current Shorts format guidance allows eligible square/vertical videos up to three minutes for uploads on/after 15 October 2024. Older uploads use the earlier shorter-duration rule.
- Search results are indexed and ranked. A 100-video target is a target, not a guaranteed yield.

### Instagram

- DDGS searches public indexed Reel links using site:instagram.com/reel/.
- Instaloader resolves a result via Post.from_shortcode.
- The code stores video_view_count as view_count and video_play_count separately as play_count.
- The default 1M filter uses view_count only. --instagram-use-play-count explicitly permits using play_count only when view_count is missing; the source metric name remains visible.
- Missing counts remain unknown and do not pass the 1M threshold.
- A public page may be unavailable, deleted, restricted or login-gated. Those are recorded as skipped lookup errors.
- Hashtag search through Instaloader requires a valid local session. The session file stays on the user's computer. Do not place session cookies or passwords in GitHub.

## 3. SQLite and uniqueness

The local database is .shortslm/discovery.sqlite3 and is never committed. It stores:
- discovery runs and query-level outcomes;
- platform + source ID unique candidate rows;
- permitted title/caption, description, creator handle, view/play snapshots, tags/hashtags and duration;
- short-format confidence and eligibility status;
- download job status, private local path and failure reason;
- SHA-256 after media delivery.

Uniqueness happens in two layers:
1. (platform, source_id) prevents the same source item from being reselected on later runs.
2. SHA-256 prevents identical bytes cross-posted on YouTube and Instagram from being processed twice after both have been downloaded.

A perceptual near-duplicate check (for re-encoded files) is a later extension; byte-level SHA-256 alone will not detect visually identical videos encoded differently.

## 4. Workflow

### Install on the local laptop

Use Windows PowerShell in the cloned repository:

    py -3.11 -m venv .venv
    .venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    pip install -e ".[dev,discovery,audio]"

Install FFmpeg and make sure both ffmpeg and ffprobe are on PATH. For the optional gallery-dl fallback:

    pip install -e ".[instagram-fallback]"

Check installation:

    shorts-lm doctor

### Discover 100 new eligible candidates

    shorts-lm discover run --platform all --target-new 100 --min-views 1000000 --max-candidates 1500 --query "cricket viral shorts India" --query "education facts short videos" --query "comedy viral reels India"

For YouTube-only search:

    shorts-lm discover run --platform youtube --target-new 100 --min-views 1000000

For Instagram-only indexed Reel search:

    shorts-lm discover run --platform instagram --target-new 100 --min-views 1000000

For Instagram hashtag discovery, first create a normal Instaloader session using its interactive login (password is prompted rather than passed on the command line). Then:

    instaloader --login YOUR_USERNAME --no-posts --no-profile-pic YOUR_USERNAME
    shorts-lm discover run --platform instagram --instagram-session-user YOUR_USERNAME --instagram-hashtag cricket --instagram-hashtag comedy --target-new 100 --min-views 1000000

The user's own session file is never read from a browser by this code. No CAPTCHA, login wall, challenge, rate limit or access control is bypassed. If Instagram requires login or returns an error, stop/skip that result and report it.

### Download a candidate

A candidate is a discovery record, not automatic permission to copy/train on its media. The local rights JSONL must contain an item-specific grant for:
- media retrieval;
- media analysis;
- temporary processing;
- derived-artifact retention;
- model training;
- a provenance/evidence reference and current expiry/revocation status.

The example at examples/rights_manifest.example.jsonl is deliberately non-authorizing. Replace it only with real permission records. Keep the actual file under data/private/.

    shorts-lm discover download --rights-manifest data/private/rights.jsonl --limit 25 --output-dir data/private/acquired

The acquisition command refuses items without a matching rights row. It writes the MP4 and a private metadata/rights sidecar. FFmpeg is used by yt-dlp to remux to MP4.

## 5. Run output states

- eligible: current metric meets threshold and short-format status is at least candidate.
- metric_unknown: view/play field unavailable; never treated as zero or as 1M+.
- below_threshold: the available configured metric is below 1M.
- format_unknown: not enough metadata to classify the item.
- not_short: duration/aspect-ratio metadata rules disqualify it.
- downloaded: authorized MP4 exists locally.
- download_failed: extractor or delivery failed and can be retried.
- duplicate_media: SHA-256 matches an already downloaded item.

The run report distinguishes new source candidates from actual MP4 files. A discovery target of 100 does not imply 100 successful downloads.

## 6. Known reliability boundaries

- yt-dlp's supported-site list warns that support may break when websites change.
- Instagram public search engines may surface incomplete or stale results.
- Instaloader may need a logged-in session for some hashtag/content pages and is subject to Instagram's current throttling.
- The gallery-dl project has moved active development from GitHub to Codeberg; keep it an optional fallback, not the main dependency.
- Private/restricted content and unavailable media are not retrieved by using stealth, proxy rotation, copied browser cookies or challenge bypass.
- View and play counts are platform-specific metrics and should not be combined into one unlabeled column.
- Search engine result ranking is biased; shuffled queries/results are not a uniform platform-wide sample.

## 7. References checked

- yt-dlp repository and search extractor: https://github.com/yt-dlp/yt-dlp
- yt-dlp supported-site list: https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md
- Instaloader repository: https://github.com/instaloader/instaloader
- Instaloader Post fields: https://instaloader.github.io/module/structures.html
- Instaloader hashtags and Posts: https://instaloader.github.io/module/structures.html
- Instaloader basic usage and Reels target: https://instaloader.github.io/basic-usage.html
- Instaloader session/login and rate-limit guidance: https://instaloader.github.io/troubleshooting.html
- DDGS repository: https://github.com/deedy5/ddgs
- gallery-dl README and Codeberg migration: https://github.com/mikf/gallery-dl
- gallery-dl release notes: https://codeberg.org/mikf/gallery-dl/releases

This is a non-official-API implementation. The search and extractors are open source, but their access is best-effort and depends on upstream platform changes.
