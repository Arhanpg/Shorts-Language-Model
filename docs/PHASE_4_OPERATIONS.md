# Phase 4 — Catalogue Coverage, Dataset QA and Annotation

Phase 4 does not rerun Phase 3. It consumes the committed v0.2 candidate catalogue and the private rights-cleared media manifest created by the existing pilot workflow.

## 1. Materialize the complete catalogue

Run from the repository root in PowerShell:

```powershell
shorts-lm phase4 catalogue `
  --catalogue-dir data/seed_catalogue/v0.2 `
  --output-dir outputs/phase4/catalogue `
  --batch-size 100 `
  --hashtag-batch-size 20
```

This reads all supported CSV files, deduplicates normalized handles and hashtags, and writes:
- Instagram account seed list and bounded 100-account batches.
- YouTube channel candidate CSV, plus a seed file only for stable UC channel IDs.
- Hashtag candidates, Instagram hashtag input and bounded hashtag batches.
- Source counts, invalid rows, unresolved YouTube handles and catalogue limitations.

The source catalogue is not a verified list of active Shorts/Reels publishers. AI verification labels remain source claims; generated hashtags have no assumed popularity.

## 2. Run bounded discovery batches

The graph runner accepts at most 500 creators and 100 hashtags per run. Use one batch per command, keep the same SQLite database, and name each report distinctly. Example:

```powershell
shorts-lm discover graph-run `
  --platform instagram `
  --instagram-seeds-file outputs/phase4/catalogue/batches/instagram_creators_0001.txt `
  --instagram-hashtags-file outputs/phase4/catalogue/batches/hashtags_0001.txt `
  --max-creators 100 `
  --instagram-max-hashtags 100 `
  --max-runtime-seconds 600 `
  --target-new 200 `
  --min-metric 0 `
  --database .shortslm/discovery.sqlite3 `
  --report outputs/phase4/discovery/instagram_batch_0001.json
```

To run every generated batch from PowerShell, use the controlled runner (choose one or more scopes):
```powershell
# Every Instagram account batch
.\\scripts\\run_phase4_discovery_batches.ps1 -RunInstagramCreators

# Every hashtag batch (20 tags per run)
.\\scripts\\run_phase4_discovery_batches.ps1 -RunInstagramHashtags

# Every stable YouTube channel-ID batch
.\\scripts\\run_phase4_discovery_batches.ps1 -RunYouTubeChannels

# All three campaigns (long-running; run separately if you want to inspect each stage)
.\\scripts\\run_phase4_discovery_batches.ps1 -RunInstagramCreators -RunInstagramHashtags -RunYouTubeChannels
```
The script keeps the same SQLite database, creates a distinct report per batch, pauses between batches and stops on a non-zero CLI exit. Inspect each report for provider restrictions before restarting. Account-only batches use `--instagram-max-hashtags 0`; hashtag-only batches use `--max-creators 0` and an empty creator seed file. Do not use `--force` unless intentionally requeueing completed seeds.

YouTube channel candidates are not all directly usable channel IDs. Phase 4 exports only IDs matching the stable `UC...` shape to `youtube_channel_id_seeds.txt`. The graph runner now accepts this file directly. Example:
```powershell
shorts-lm discover graph-run `
  --platform youtube `
  --youtube-channel-ids-file outputs/phase4/catalogue/youtube_channel_id_seeds.txt `
  --max-creators 100 `
  --max-seed-queries 0 `
  --max-hashtag-queries 0 `
  --max-runtime-seconds 600 `
  --target-new 200 `
  --min-metric 0 `
  --database .shortslm/discovery.sqlite3 `
  --report outputs/phase4/discovery/youtube_channel_batch_0001.json
```
Use subsequent batches under distinct report names. Handle-only entries remain in the CSV for human verification; they are not guessed into IDs.

Stop when the provider reports a login challenge, CAPTCHA, rate limit, 403/429, or other access restriction. Do not rotate identities/proxies or bypass access controls.

## 3. Create a private rights-cleared annotation queue

Use the existing `shorts-lm pilot template` and fill the local manifest only with evidence-backed, item-specific permissions. Public visibility, a creator name, a hashtag, a view count, or a successful extractor response is not permission.

Validate media and permissions first:

```powershell
shorts-lm pilot validate --manifest data/private/phase4-rights-manifest.jsonl --report outputs/phase4/validation.json
```

Create the human review queue:

```powershell
shorts-lm phase4 annotation-template `
  --manifest outputs/pilot/selected_manifest.jsonl `
  --output outputs/phase4/annotation_queue.csv
```

Annotators must review the actual media and fill labels with grounded evidence. Draft/model-generated descriptions are not gold labels. Use `approved` or `adjudicated` only after review. Preserve reviewer, disagreement and tool/model/prompt versions.

## 4. Release gate and splits

```powershell
shorts-lm phase4 release `
  --manifest outputs/pilot/selected_manifest.jsonl `
  --annotations outputs/phase4/annotation_queue.csv `
  --output-dir outputs/phase4/release `
  --golden-fraction 0.10
```

Release requires explicit, unexpired, unrevoked permission for media analysis, temporary processing, derived-artifact retention and model training; valid media SHA-256 and duration; and approved human annotation with core labels. Any blocker fails closed and is written to `release_blockers.json`.

Known creator groups and exact SHA-256 duplicates are unioned before splitting. Remaining groups are ordered by publication time and allocated approximately 80/10/10. A creator or duplicate group cannot cross splits. Perceptual near-duplicate/transcode detection and inter-annotator agreement remain required manual quality gates. The golden holdout is locked by workflow, not cryptographically access-controlled by this CLI.

## 5. Recommended first campaign

Start with 50–100 assets whose relevant permissions are documented. Audit quality and annotation agreement before scaling toward 1,000–2,000 reviewed examples. Do not attempt to download millions of videos in one batch. Keep media, databases, private manifests, rights evidence, sessions and reports outside Git.
