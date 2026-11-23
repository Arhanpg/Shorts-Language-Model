# Metadata-only Shorts/Reels URL collection

The `shorts-lm urls collect` command discovers metadata and exports canonical URLs only. It never downloads video or audio media and never runs feature extraction.

## Outputs

- `data/discovered_urls/instagram_reels.txt` — unique Instagram Reel URLs.
- `data/discovered_urls/youtube_shorts.txt` — unique YouTube Shorts URLs.

The two URL files are intentionally not Git-ignored. The SQLite discovery database, Instagram browser profile, and run reports remain local/private.

## Provider architecture

- **YouTube:** yt-dlp flat metadata extraction. Each creator is visited directly at its `/shorts` tab; no channel-ID resolution stage and no TubeScrape/API provider are used by this URL-collection command. Hashtag discovery uses yt-dlp's YouTube search extractor with a `#tag #shorts` query. Entries with known duration above 180 seconds are excluded from hashtag results; unknown-duration results remain potential candidates.
- **Instagram:** the existing Playwright visible-browser workflow using the user's manually signed-in profile.

A 404, deleted channel, renamed handle, empty creator page, or other individual extraction error is counted and skipped; it does not stop the remaining YouTube creator or hashtag surfaces. The URL file is checkpointed after each creator or hashtag batch, so a later run keeps previously collected URLs.

## Setup

Install discovery dependencies:

```powershell
pip install -e ".[discovery,instagram-browser]"
playwright install
```

For Instagram, sign in manually once:

```powershell
shorts-lm discover instagram-browser-login
```

Complete verification normally and close the browser windows using the dedicated ShortsLM profile.

## Run the collector

From the repository root:

```powershell
shorts-lm urls collect
```

You can run only YouTube (no Instagram browser profile required):

```powershell
shorts-lm urls collect --platforms youtube
```

Or only Instagram:

```powershell
shorts-lm urls collect --platforms instagram
```

Batch sizes can be adjusted:

```powershell
shorts-lm urls collect `
  --creator-batch-size 100 `
  --instagram-hashtag-batch-size 50 `
  --youtube-hashtag-batch-size 20
```

The catalogue contains candidate leads, not a guarantee that every handle is active or every hashtag returns Shorts. The collector records actual processed surfaces, errors, and unique URL counts. Platform access restrictions are not bypassed.

## Commit the URL lists

After reviewing the output:

```powershell
git add data/discovered_urls/instagram_reels.txt data/discovered_urls/youtube_shorts.txt
git commit -m "Add discovered Instagram Reel and YouTube Shorts URL inventories"
git push
```

Do not commit `.shortslm/`, browser profiles, cookies, or the SQLite database.
