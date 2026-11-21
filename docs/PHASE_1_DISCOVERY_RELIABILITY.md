# Phase 1 Discovery Reliability and Windows Troubleshooting

**Updated:** 21 November 2026  
**Document type:** historical troubleshooting note; current implementation is documented in [PHASE_1_DISCOVERY_COVERAGE.md](PHASE_1_DISCOVERY_COVERAGE.md).  
**Scope:** YouTube Shorts and Instagram Reel discovery, metadata filtering and local SQLite inventory. This is separate from the existing single-video telemetry analyzer.

## 1. What the earlier run showed

The reported run returned 215 candidate records, including 161 repeated source IDs and 34 provider errors. It produced zero new eligible records. The earlier CLI did not show enough reason counts to determine whether the remaining unique records failed because of missing view metrics, below-threshold counts, uncertain format or provider lookup failure. The new run report separates these cases.

The old YouTube adapter used yt-dlp's default playlist processing behaviour. That resolves search result entries as individual video URLs. An unavailable, deleted, private or restricted item can therefore produce an extractor error even though the search page returned a candidate. A long list of such messages overwhelmed the console.

## 2. Current YouTube search fix

The earlier yt-dlp flat search path has been superseded. The current provider uses ytscrape v2.2+ with YouTube's dedicated `SearchFilter.SHORTS` option. It returns a typed video result and can paginate up to the configured result cap.

The new provider:
- selects Shorts results directly rather than inferring format from generic video results;
- reads typed view counts, duration, title, channel and approximate publication metadata when supplied;
- reuses one HTTP client per language/region pair in the run;
- applies a bounded request timeout, short retry policy and request interval;
- selectively fetches detailed metadata for at most `--metadata-enrichment-limit` new incomplete records;
- stops on rate-limit or bot-detection exceptions instead of trying to evade them.

The client uses internal InnerTube web endpoints, not the official YouTube Data API. These endpoints are not a stable public contract and may change or become unavailable. The detailed design and limitations are in [PHASE_1_DISCOVERY_COVERAGE.md](PHASE_1_DISCOVERY_COVERAGE.md).


## 3. YouTube EJS and JavaScript runtime

There are two separate yt-dlp requirements:

1. **Flat search:** reads the search page and metadata; it does not intentionally open every video URL.
2. **Full video extraction/download through yt-dlp:** current YouTube media acquisition may need the yt-dlp EJS challenge scripts and a supported JavaScript runtime. ytscrape Shorts search does not use yt-dlp.

The discovery optional extra installs yt-dlp's default extras for the separate downloader (including the EJS companion package). It also installs ytscrape for Shorts-only search. The user must still install a supported JavaScript runtime.

Recommended:
- Deno 2.3 or newer.
- Node.js 22 or newer is an alternative.

Check from PowerShell:

    yt-dlp --version
    deno --version
    node --version
    shorts-lm doctor

Official setup:
- https://github.com/yt-dlp/yt-dlp/wiki/EJS
- https://github.com/yt-dlp/ejs
- https://docs.deno.com/runtime/getting_started/installation/
- https://nodejs.org/en/download/

The doctor command now detects the yt-dlp package, yt-dlp-ejs, Deno and Node.js. Missing EJS/runtime is shown as a YouTube full-extraction/download prerequisite warning; it is not treated as an FFmpeg or discovery-package failure.

## 4. Current Instagram discovery improvement

DDGS searches public indexed Reel links using an explicit primary backend set, a single fallback engine, and an eight-second request timeout. The default Instagram query pool rotates topic and language strata; it is not a complete Instagram catalogue.

Instaloader is configured with a 12-second per-request timeout and one connection attempt, instead of its upstream defaults of 300 seconds and three attempts. A maximum of 40 individual metadata lookups is allowed by default. Repeated metadata failures, timeouts, rate-limit responses or login/challenge conditions open a circuit for the rest of the run.

The provider uses short, bounded retries and records its failure reason in the JSON report. It does not rotate proxies or bypass access restrictions. See [PHASE_1_DISCOVERY_COVERAGE.md](PHASE_1_DISCOVERY_COVERAGE.md) for exact options and upstream references.


## 5. Eligibility and run diagnostics

The console and JSON report now distinguish:

- raw YouTube search records;
- indexed Instagram Reel links found;
- unique candidates evaluated;
- repeated IDs inside the current run;
- IDs already known in SQLite;
- new eligible candidates;
- already eligible candidates;
- missing view metric;
- below-threshold metric;
- uncertain short-form format;
- non-Short/non-Reel items;
- provider and metadata errors;
- candidate status by platform;
- full database status totals.

The default threshold is still 1,000,000 views. Missing counts remain unknown and do not pass. Instagram view_count and play_count remain separate; --instagram-use-play-count is an explicit opt-in.

A target of 100 new eligible records is not a promise that 100 will be found. The report now tells us why the run yields less.

## 6. Database metadata preservation

An earlier upsert path could preserve an old non-null view count in SQL while calculating the new status using only the incomplete incoming candidate. That allowed a partial search result to downgrade an already eligible row to metric_unknown.

The updated store calculates status from the merged view/play metrics and format classification. A missing field on a repeat search no longer erases previously available metadata. A genuinely refreshed lower view count or an explicit not_short result can still change eligibility.

## 7. Windows installation and rerun

After the branch is merged into main, from the repository root in PowerShell:

    git pull origin main
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    pip install -e ".[dev,discovery,audio]" --upgrade
    shorts-lm doctor

Install Deno 2.3+ from the official installation page and reopen PowerShell so the updated PATH is loaded. Alternatively, install Node.js 22+.

Run YouTube by itself first:

    shorts-lm discover run --platform youtube --target-new 100 --min-views 1000000 --max-candidates 1500

Then test Instagram independently:

    shorts-lm discover run --platform instagram --target-new 100 --min-views 1000000 --max-candidates 1500 --instagram-region in-en --instagram-pages 2

Then run both:

    shorts-lm discover run --platform all --target-new 100 --min-views 1000000 --max-candidates 1500

The existing .shortslm/discovery.sqlite3 is preserved. Do not delete it just to hide duplicate counts; repeat source IDs are intentionally excluded from new candidate totals. Existing rows with missing metrics can be updated when a later search returns better metadata.

The report is saved to outputs/discovery/latest.json.

## 8. Generated package files and Git warnings

The latest user commit added src/shorts_language_model.egg-info/ files generated by editable package installation. These are build metadata, not source code. The fix:
- removes the generated files from the tracked branch;
- adds *.egg-info/, build/ and dist/ to .gitignore;
- adds .gitattributes rules so source/text files use LF consistently across Windows and Unix.

The LF-to-CRLF messages were Git line-ending notices, not the reason discovery failed.

## 9. Validation

The new tests cover:
- ytscrape Shorts-filter search and typed result parsing;
- no per-result terminal error flood;
- raw result count versus deduplicated candidate count;
- metric preservation across incomplete repeat searches;
- database status summaries per platform.

GitHub Actions must pass Ruff and the complete pytest suite on Python 3.11 and 3.12 before the branch is considered validated. Live YouTube/Instagram response availability still needs to be verified from the user's Windows laptop because it depends on current platform access and search results.
