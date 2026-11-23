# Phase 4 full-catalogue master run

The `shorts-lm phase4 run-all` command is the single orchestration entry point for the complete catalogue. It rebuilds the normalized catalogue, randomizes source order, visits every Instagram creator candidate, every seedable YouTube channel ID, and every normalized hashtag on both platforms, then drains the discovered-media queue after each discovery batch.

## Before the full run

1. Install the project and its discovery/analysis extras:

   ```powershell
   pip install -e ".[all,legacy-discovery]"
   ```

2. Install FFmpeg/ffprobe and a supported YouTube JavaScript runtime (Deno 2.3+ recommended, or Node.js 22+). Confirm the local GPU and Python engines with `shorts-lm doctor`.

3. Prepare the normal Instagram browser profile once:

   ```powershell
   shorts-lm discover instagram-browser-login
   ```

   Sign in manually in the opened Chrome profile, complete any official verification yourself, and close every Chrome window using that profile before starting discovery. Do not use this workflow to bypass login challenges, CAPTCHAs, rate limits, or platform restrictions.

4. Ensure you have authorization to acquire and analyze the media you intend to process. Public visibility and catalogue membership do not automatically grant download, derived-artifact retention, or model-training rights.

## One master command

Run from the repository root in PowerShell:

```powershell
shorts-lm phase4 run-all --all-catalogue --min-metric 1000000
```

The command uses conservative defaults suitable for a resumable long-running campaign. To use an explicitly authenticated local Instagram session for the downloader, add `--instagram-session-user YOUR_USERNAME --instagram-session-file .shortslm/instagram.session` only if you created that session through the supported interactive login flow. The browser profile is still required for graph discovery.

## What it does

- Rebuilds `outputs/phase4/catalogue` from `data/seed_catalogue/v0.2`, including Instagram person, organization/publisher and unknown-entity lead files. Creator identity parsing accepts `account_handle` and `account_url` as well as generic handle/URL columns.
- Randomizes creator and hashtag order with a recorded seed.
- Processes Instagram creators in bounded batches (up to 100 by default).
- Processes stable YouTube `UC...` channel IDs in bounded batches. Handle-only/unresolved YouTube records are counted and skipped rather than guessed.
- Submits all normalized hashtags to Instagram and YouTube independently, in provider-safe batches (50 Instagram / 20 YouTube by default).
- Uses a persistent SQLite discovery inventory and creator frontier, so rerunning the command resumes known state instead of starting from scratch.
- Runs acquisition and local ASR, OCR, audio and visual analysis for eligible confirmed Shorts/Reels.
- Deletes each temporary downloaded video after its processing attempt. JSON analysis, transcript, OCR, metadata, hashes and the cumulative feature manifest remain.
- Caps processing attempts (2 by default), checkpoints reports after each batch, and stops further discovery for a platform when an access restriction is reported.

## Outputs

- `.shortslm/discovery.sqlite3`: persistent candidate inventory, processing states, creator frontier and hashes.
- `outputs/phase4/catalogue/`: normalized candidate catalogue and batch files.
- `outputs/phase4/runs/`: per-batch discovery reports and `master-run-summary.json`.
- `data/private/processed/`: per-video analysis, transcript, OCR and metadata artifacts.
- `outputs/dataset/phase4-features.jsonl`: cumulative structured feature manifest.
- `data/private/acquired/`: temporary acquisition directory; successfully processed or failed-attempt video files are removed by this command.

## Important expectations

The default qualifying threshold is 1,000,000 native views/plays. Set `--min-metric 0` only for a deliberate unfiltered test. This is a multi-hour or multi-day campaign, not a promise of 10,000 successful account resolutions or 10,000 processed videos. Catalogue rows are candidate leads; some accounts may be inactive, inaccessible, invalid, private, blocked, or have no eligible short-form videos. YouTube handle-only rows cannot be resolved from a handle by guessing. Provider results are best-effort samples and do not prove a globally complete popularity ranking. Instagram plays and YouTube views are stored as separate metrics.

The runner checkpoints discovery and processing state. If interrupted, run the same command again. It has bounded processing retries and no unbounded retry loop. A reported restriction stops further discovery on that platform; wait for the platform to restore ordinary access before manually restarting. It does not bypass restrictions.

Feature extraction is not the same as dataset release or training authorization. Phase 4 output should be audited and annotated before Phase 5 model development.
