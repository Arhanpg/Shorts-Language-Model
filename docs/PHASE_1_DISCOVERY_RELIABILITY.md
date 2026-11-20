# Phase 1 Discovery Reliability and Windows Troubleshooting

**Updated:** 21 November 2026  
**Base commit:** b57ea0faa37b67f1f2d52754fbe8868736243bbf  
**Scope:** YouTube Shorts and Instagram Reel discovery, metadata filtering and local SQLite inventory. This is separate from the existing single-video telemetry analyzer.

## 1. What the earlier run showed

The reported run returned 215 candidate records, including 161 repeated source IDs and 34 provider errors. It produced zero new eligible records. The earlier CLI did not show enough reason counts to determine whether the remaining unique records failed because of missing view metrics, below-threshold counts, uncertain format or provider lookup failure. The new run report separates these cases.

The old YouTube adapter used yt-dlp's default playlist processing behaviour. That resolves search result entries as individual video URLs. An unavailable, deleted, private or restricted item can therefore produce an extractor error even though the search page returned a candidate. A long list of such messages overwhelmed the console.

## 2. YouTube search fix

The provider now sets the yt-dlp option extract_flat = "in_playlist".

yt-dlp documents this mode as leaving entries inside a playlist/multi-video result unresolved. It keeps the search-page entries available for parsing without opening every individual video page. Search-page metadata such as title, duration and view count is used where present. The YouTube search extractor itself parses view count from its metadata rows when that field is available.

The provider:
- runs the search query once per phrase;
- reads the returned flat entries;
- normalizes ID, canonical URL, title, channel, duration, approximate date and view count;
- drops duplicate IDs within that search query;
- captures yt-dlp warnings/errors using a quiet logger instead of printing each item failure to the terminal.

This does not make every search result available for download. A later download may still fail, and the separate rights gate remains required.

## 3. YouTube EJS and JavaScript runtime

There are two separate yt-dlp requirements:

1. **Flat search:** reads the search page and metadata; it does not intentionally open every video URL.
2. **Full video extraction/download:** current YouTube extraction may need the yt-dlp EJS challenge scripts and a supported JavaScript runtime.

The discovery optional extra now installs yt-dlp's default extras, which include the EJS companion package. The user must still install a supported JavaScript runtime.

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

## 4. Instagram discovery improvement

DDGS search now defaults to India English (in-en) instead of DDGS' default US English region. It inspects multiple result pages per query and supports selecting the DDGS backend and region from the CLI.

The DDGS text API explicitly supports region, backend, page and maximum-result parameters. The returned links are still search-engine-indexed links, not a complete Instagram catalogue.

Instaloader still resolves Reel shortcodes and reads available metadata. Metadata errors remain captured per Reel; a failed Reel does not abort an entire query. Login-restricted, deleted and unavailable posts are skipped instead of using bypass methods.

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
- yt-dlp search using flat playlist mode;
- no per-result terminal error flood;
- raw result count versus deduplicated candidate count;
- metric preservation across incomplete repeat searches;
- database status summaries per platform.

GitHub Actions must pass Ruff and the complete pytest suite on Python 3.11 and 3.12 before the branch is considered validated. Live YouTube/Instagram response availability still needs to be verified from the user's Windows laptop because it depends on current platform access and search results.
