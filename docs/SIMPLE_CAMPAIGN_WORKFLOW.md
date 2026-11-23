# Simple randomized discovery and feature-extraction workflow

This workflow uses the committed v0.2 catalogue. It removes the need to prepare or pass a separate `rights.jsonl` file for ordinary catalogue sampling and metadata discovery.

## 1. Build the normalized catalogue once

```powershell
shorts-lm phase4 catalogue `
  --catalogue-dir data/seed_catalogue/v0.2 `
  --output-dir outputs/phase4/catalogue
```

## 2. Randomly sample creators and hashtags

```powershell
shorts-lm campaign sample `
  --catalogue-dir outputs/phase4/catalogue `
  --output-dir outputs/campaign `
  --creators 100 `
  --hashtags 100
```

The command writes separate Instagram and YouTube creator and hashtag seed files. Use `--seed 42` (or another integer) when a repeatable sample is needed. YouTube creator sampling accepts stable `UC...` channel IDs only; handle-only records remain in the candidate CSV and are not guessed into channel IDs. The current hashtag catalogue is platform-neutral, so its tags are independently sampled for each platform unless a source row explicitly labels a platform.

## 3. Discover creator videos and hashtag results

Instagram creator + hashtag discovery:

```powershell
shorts-lm discover graph-run `
  --platform instagram `
  --instagram-seeds-file outputs/campaign/instagram_creator_seeds.txt `
  --instagram-hashtags-file outputs/campaign/instagram_hashtag_seeds.txt `
  --max-creators 100 `
  --instagram-max-hashtags 100 `
  --max-runtime-seconds 600 `
  --target-new 200 `
  --min-metric 0 `
  --database .shortslm/discovery.sqlite3 `
  --report outputs/campaign/instagram_discovery.json
```

YouTube creator discovery:

```powershell
shorts-lm discover graph-run `
  --platform youtube `
  --youtube-channel-ids-file outputs/campaign/youtube_creator_seeds.txt `
  --youtube-hashtags-file outputs/campaign/youtube_hashtag_seeds.txt `
  --max-creators 100 `
  --max-seed-queries 0 `
  --max-hashtag-queries 100 `
  --continue-graph-after-target `
  --max-runtime-seconds 600 `
  --target-new 200 `
  --min-metric 0 `
  --database .shortslm/discovery.sqlite3 `
  --report outputs/campaign/youtube_discovery.json
```

Discovery stores candidate metadata and platform-native engagement metrics. Instagram plays and YouTube views remain distinct. The processing queue orders eligible candidates by their observed platform-native metric (descending), not by a cross-platform combined score. Provider search surfaces are best-effort; the result is not guaranteed to be the globally most popular content for a creator.

## 4. Run ASR, OCR, transcripts and multimodal features

The existing processing command runs acquisition (where configured) followed by the local analyzer, transcript/OCR artifact writers and dataset-manifest export:

```powershell
shorts-lm discover process `
  --platform all `
  --limit 25 `
  --min-metric 0 `
  --database .shortslm/discovery.sqlite3 `
  --download-dir data/private/acquired `
  --artifact-dir data/private/processed `
  --dataset-manifest outputs/dataset/processed-videos.jsonl `
  --asr-model small `
  --device cuda
```

Only use acquisition and processing on media you are entitled to access and process. Public metadata discovery does not itself authorize downloading or retaining video, transcripts, OCR, frames, or derived artifacts. No workflow should bypass login challenges, CAPTCHAs, rate limits, or other platform restrictions. If you already have authorized local media, use the local analysis command instead of acquiring it again.

## 5. Outputs

- `outputs/campaign/*_creator_seeds.txt` and `*_hashtag_seeds.txt`: randomized inputs.
- `.shortslm/discovery.sqlite3`: deduplicated discovery inventory and processing state.
- `data/private/acquired/`: acquired media, when authorized.
- `data/private/processed/`: analysis, transcript, OCR and per-video artifacts.
- `outputs/dataset/processed-videos.jsonl`: cumulative processed-video feature manifest.

This phase produces observations and features. Model training and train/validation/test construction belong to subsequent phases.
