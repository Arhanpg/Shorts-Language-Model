# Automated Non-API Discovery and Media Acquisition

**Updated:** 21 November 2026  
**Selected tools:** yt-dlp, DDGS, Instaloader, optional gallery-dl, SQLite.

## 1. Requirements

The system should search for new YouTube Shorts and Instagram Reels without the owner pasting URLs or manually downloading MP4s. It should collect available metadata, filter candidates by a 1M+ view/play threshold, save source identity in SQLite, avoid repeats, and download media automatically through open-source extractors for items whose intended acquisition/training rights are documented.

No YouTube Data API, Instagram Graph API, Meta Content Library API or platform developer token is used by the discovery commands.

## 2. Tool selection

| Task | Tool | Why selected |
|---|---|---|
| YouTube search | yt-dlp | Contains the ytsearch extractor; no Data API key |
| YouTube metadata/download | yt-dlp | Same tool resolves URL, metadata and local media |
| Instagram URL discovery | DDGS | Searches publicly indexed Reel URLs via search engine |
| Instagram metadata | Instaloader | Resolves shortcode; exposes available caption, hashtags, duration, view/play metrics |
| Instagram hashtag expansion | Instaloader | Supported post iterator; login may be required |
| Instagram downloader | Instaloader | Native Post download support |
| Instagram fallback | yt-dlp extractor | Second independent extractor |
| Instagram secondary fallback | gallery-dl | Optional third-party URL extractor |
| Persistent store | SQLite | Local candidate identity, state and dedup |
| Binary dedup | SHA-256 | Exact duplicate cross-platform media check |

Repository links:
- https://github.com/yt-dlp/yt-dlp
- https://github.com/instaloader/instaloader
- https://github.com/deedy5/ddgs
- https://github.com/mikf/gallery-dl
- https://codeberg.org/mikf/gallery-dl

## 3. Provider workflow

### YouTube

1. Build topic/language search phrases.
2. Call yt-dlp's search extractor with `ytsearchN:phrase`.
3. Parse returned video entries.
4. Keep title, description, channel, tags, view_count, upload date, duration and dimensions when provided.
5. Confirm short status from a Shorts URL or format evidence; otherwise use candidate/unknown.
6. Store the normalized candidate in SQLite.
7. Use yt-dlp to download a permitted item and FFmpeg to remux to MP4.

### Instagram

1. DDGS searches `site:instagram.com/reel/` with configured topic phrases.
2. Extract and deduplicate public Reel shortcodes from results.
3. Use Instaloader `Post.from_shortcode` to retrieve available Reel metadata.
4. Preserve caption, hashtags, creator, duration, view_count and play_count separately.
5. Use view_count for the default 1M threshold; if not returned, classify metric as unknown. The optional play-count switch is explicit and keeps its metric name.
6. Optional hashtag discovery uses Instaloader's hashtag iterator and requires a user-created local session for login-restricted queries.
7. Download via Instaloader, then yt-dlp, then optional gallery-dl.

The providers use public indexed search and upstream extractors. They do not guarantee full Instagram coverage or availability of every metadata field. Deleted, restricted, challenge-gated or unavailable items may be skipped and reported.

## 4. SQLite data model

Default path: `.shortslm/discovery.sqlite3`.

- discovery_runs: requested target, threshold, time, provider results, duplicate and error counts.
- candidates: unique (platform, source_id), canonical URL, title/caption, description, creator, metric snapshots, tags/hashtags, format status, download status, local path, error.
- media identity: SHA-256 and downloaded timestamp.

The source identity key prevents a discovered Reel/Short from appearing again on future runs while the local inventory exists. SHA-256 catches exact same-file cross-posts after download; re-encoded visual duplicates require a future perceptual hash stage.

The SQLite DB is local and excluded from Git. It is not a shared multi-user database. Back it up locally if the user wants to preserve discovery history.

## 5. Run configuration

Command design:

```powershell
shorts-lm discover run --platform all --target-new 100 --min-views 1000000 --max-candidates 1500
```

Parameters:
- platform: all, youtube, instagram.
- target-new: new eligible source records to find, default 100.
- min-views: threshold, default 1,000,000.
- max-candidates: upper bound on result records to inspect.
- results-per-query: number of results requested from each query.
- query: repeatable custom search phrase.
- seed: reproducible query/result shuffle.
- database/report: local paths.
- Instagram session/hashtags: optional, private session file only.
- instagram-use-play-count: opt-in fallback metric; separate from view_count.

The target is best-effort. Search result indexes may not return sufficient new high-view records. A shorter yield is reported honestly.

## 6. Download state machine and rights

A candidate is not automatically a training asset. Before acquiring media, the download command requires a local rights manifest row keyed by platform/source_id. The permission record must separately grant:
- media_retrieval;
- media_analysis;
- temporary_processing;
- derived_artifact_retention;
- model_training.

It also needs a basis, private evidence reference, expiry and revocation state. The code checks the declaration but cannot independently authenticate the underlying evidence; the owner must ensure it is genuine. An example rights manifest is deliberately non-authorizing.

The downloader's order:
- YouTube: yt-dlp.
- Instagram: Instaloader → yt-dlp → optional gallery-dl.

No login, CAPTCHA, technical protection, DRM, rate limit or platform access control bypass is implemented. Instaloader sessions are supplied as local files created through its normal login flow; password and cookies are never committed or placed on a CLI argument.

After download:
1. require non-empty MP4;
2. attach private metadata/rights JSON sidecar;
3. calculate SHA-256;
4. compare with already downloaded assets across platforms;
5. mark exact duplicate and remove redundant bytes;
6. retain download failures in a retryable state.

## 7. Metrics and format uncertainty

- YouTube view_count: store as observed by yt-dlp.
- Instagram video_view_count: store as view_count.
- Instagram video_play_count: store separately as play_count.
- Default view threshold checks view_count only.
- Play count is optionally allowed when view_count is absent, never relabeled as views.
- Missing metric remains unknown.
- YouTube Shorts: an explicit /shorts/ URL confirms format; otherwise dimensions, duration and upload date provide evidence. Missing dates/dimensions keep the status as candidate/unknown.
- Instagram search URL under /reel/ confirms the link type, but the resolved post must still be a video.

## 8. Acceptance tests

- YouTube and Instagram URLs normalize to canonical URL + stable ID.
- Same source item reappearing across runs does not create a second row.
- 999,999 metrics fail a 1,000,000 threshold.
- Missing metrics stay unknown.
- Instagram play count is not counted unless explicitly enabled.
- Horizontal YouTube metadata is rejected as a Short.
- Unknown upload date does not over-confirm the three-minute Shorts rule.
- Expired/revoked/incomplete rights block download.
- A failed download can be retried.
- Byte-identical media discovered under two platforms downloads only once into the processing corpus.
- No SQLite, MP4, session, rights file, cookie or token is committed.

## 9. Known limits

- DDGS returns search-engine-indexed results, not every Instagram Reel.
- Search engine ranking means sampling is biased and not uniform.
- Instagram extractor metadata can be missing or stale.
- Upstream extractors can break following site changes.
- Exact file hashes do not catch re-encoded duplicate clips.
- A fixed target such as 100 new items per run is not guaranteed.
- A local rights manifest is an attestation/evidence pointer, not an automated legal clearance engine.

See [NON_API_DISCOVERY_TOOLCHAIN.md](NON_API_DISCOVERY_TOOLCHAIN.md) for installation and exact commands.
