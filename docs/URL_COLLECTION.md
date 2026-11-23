# Metadata-only Shorts/Reels URL collection

The `shorts-lm urls collect` command discovers public short-form metadata and exports canonical URLs only. It does not download video or audio media and does not run feature extraction.

## Outputs

The default output directory is `data/discovered_urls/`:

- `instagram_reels.txt` — one unique canonical Instagram Reel URL per line.
- `youtube_shorts.txt` — one unique canonical YouTube Shorts URL per line.

These files are intentionally **not** ignored by Git, so the project owner can review and commit the resulting URL inventories. The SQLite discovery database, browser profile, YouTube handle-resolution cache, and run reports remain local/private.

Only records with an explicit confirmed short-form classification are exported. View/plays count is not used as a minimum threshold: low counts and missing counts are retained. Instagram plays remain distinct from YouTube views in SQLite metadata. Duplicate URLs are removed.

## Setup

Install discovery dependencies:

```powershell
pip install -e ".[discovery,instagram-browser]"
playwright install
```

For Instagram, open a normal Chrome window and sign in manually once:

```powershell
shorts-lm discover instagram-browser-login
```

Complete any platform verification normally, then close every Chrome window using the dedicated ShortsLM profile.

## Full catalogue collection

Run from the repository root:

```powershell
shorts-lm urls collect
```

Optional controls:

```powershell
shorts-lm urls collect `
  --creator-batch-size 100 `
  --instagram-hashtag-batch-size 50 `
  --youtube-hashtag-batch-size 20 `
  --runtime-seconds 900
```

The command:

1. Materializes the complete seed catalogue.
2. Resolves YouTube @handles to stable channel IDs using metadata-only yt-dlp extraction; resolved IDs are cached in `.shortslm/youtube_channel_resolution.csv`.
3. Runs bounded creator and hashtag discovery jobs against the existing SQLite database.
4. Uses a zero metric threshold; unknown metrics remain unknown and are not treated as zero.
5. Writes URL checkpoints after each successful discovery batch.
6. Stops a platform campaign when an access restriction is reported. It does not bypass CAPTCHAs, login challenges, rate limits, or other access controls.
7. Reuses the SQLite database and resolution cache on subsequent runs.

A full catalogue run is potentially long-running. A 10,000-creator seed list and 10,000+ hashtags do not guarantee that all creators are active, all hashtags return results, or all videos are accessible. Providers impose their own result limits and availability constraints. The command reports actual candidate and URL counts rather than claiming full coverage.

## Commit the URL lists

After reviewing the files:

```powershell
git add data/discovered_urls/instagram_reels.txt data/discovered_urls/youtube_shorts.txt
git commit -m "Add discovered Instagram Reel and YouTube Shorts URL inventories"
git push
```

Do not commit `.shortslm/`, session/profile data, cookies, or the SQLite database.
