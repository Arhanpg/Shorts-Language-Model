# Phase 2 — Local Setup and Validation Commands

## Where to run

Run manifest validation, sampling and Phase 1 telemetry on your **local Windows/WSL laptop**. Phase 2 is a 300-video data-engineering pilot, not a model-training run. Colab is unnecessary. Use a local SSD with sufficient free space. CPU is the default; your RTX 3050 is optional and is not required.

Keep media, manifests, creator salt, reports and consent references in private folders. Do not upload them to GitHub.

## 1. Update the repository after the PR is merged

    git checkout main
    git pull origin main
    .\.venv\Scripts\Activate.ps1
    pip install -e ".[dev,audio]"

If you installed VidTrace previously, ensure the same virtual environment can import it. Confirm:

    shorts-lm doctor
    shorts-lm pilot --help

## 2. Create a manifest template

    shorts-lm pilot template --output data/private/manifest.example.jsonl

Copy it to `data/private/candidates.jsonl` and create one JSON object per permitted video.

For each record:
- use a unique ID such as `clip_0001`;
- identify its source/platform category;
- use a local file path, not a public URL;
- record a creator identifier only where appropriate and protected;
- set rights flags according to actual permission, not assumptions;
- set `model_training=true` only when the agreement explicitly permits model training;
- provide language, topic and speech mode;
- add a timezone-aware publication timestamp;
- add a metric snapshot with metric name, observed value, source and timezone-aware observation timestamp only where permitted.

Example rights object:

    {
      "basis": "creator_permission",
      "evidence_ref": "private-consent-record-001",
      "media_analysis": true,
      "temporary_processing": true,
      "derived_artifact_retention": true,
      "raw_media_retention": false,
      "model_training": false,
      "public_redistribution": false,
      "expires_at": null,
      "revoked": false
    }

This declaration is not automatic legal verification. Check the underlying agreement and third-party music/performer rights. The template uses placeholders; it is not valid permission.

## 3. Validate candidate records

    shorts-lm pilot validate --manifest data/private/candidates.jsonl --report outputs/pilot/validation.json

A valid record must pass the JSON schema and rights gate, point to a local supported video, remain within the default 500 MB / 180-second limits, pass ffprobe and not duplicate an earlier accepted SHA-256.

Read `outputs/pilot/validation.json`. Resolve permission, path, codec and duplicate errors before sampling. To require model-training permission for every candidate:

    shorts-lm pilot validate --manifest data/private/candidates.jsonl --report outputs/pilot/training-validation.json --require-training-rights

This strict option is not required for general analysis/telemetry.

## 4. Select a stratified sample of 300

    shorts-lm pilot sample --manifest data/private/candidates.jsonl --output-dir outputs/pilot --target 300 --seed 42 --max-per-creator 5

The default requires 300 valid unique records and stops if fewer are available. Do not weaken the rights gate to reach 300.

For a smaller diagnostic run, explicitly allow a shortfall:

    shorts-lm pilot sample --manifest data/private/candidates.jsonl --output-dir outputs/pilot --target 300 --seed 42 --allow-shortfall

The requested target and actual shortfall remain in `selection_report.json`.

Outputs include selected manifest, coverage table, validation summary, matched-pair suggestions and review queue. The creator HMAC salt is created at `.shortslm/creator_salt`. Back it up privately if you need stable pseudonyms across future runs. Never upload the salt.

## 5. Process 5–10 videos first

    shorts-lm pilot process --manifest outputs/pilot/selected_manifest.jsonl --output-dir outputs/pilot --limit 10 --asr-model tiny --asr-device cpu

For a fast media-only smoke test:

    shorts-lm pilot process --manifest outputs/pilot/selected_manifest.jsonl --output-dir outputs/pilot-smoke --limit 10 --no-asr --no-ocr

The first faster-whisper run may download model weights. It will use the local cache on subsequent runs. Do not run multiple CPU-heavy jobs concurrently at the start.

## 6. Process the complete selected pilot

When the first 5–10 clips work:

    shorts-lm pilot process --manifest outputs/pilot/selected_manifest.jsonl --output-dir outputs/pilot --asr-model small --asr-device cpu

The processor is sequential and resumable. Re-running the same command reuses reports only when file checksum, size, rights reference/expiry and pipeline configuration fingerprint still match. Use `--no-resume` to reprocess all entries. Changing ASR model, toggles or keyframe budget invalidates prior reports and recomputes affected records.

If rights are revoked or changed, update the private candidate manifest and rerun validation and sampling. The local tool does not query a consent provider automatically.

## 7. Build the combined report

    shorts-lm pilot report --pilot-dir outputs/pilot --output outputs/pilot/final_pilot_report.json

Review:
- `validation_summary.json`;
- `selection_report.json`;
- `coverage.csv`;
- `matched_pairs.csv`;
- `review_queue.csv`;
- `processing_metrics.csv`;
- `processing_summary.json`;
- `final_pilot_report.json`.

The processing summary contains status counts and quality slices by platform/language/topic/speech mode/duration. It measures local processing time and file/artifact sizes, not a cloud invoice or human-review cost.

## 8. Human audit (25–50 clips)

Audit a varied subset: Hindi, Hinglish, English and other available languages; cricket/sports, talking head, meme, tutorial, travel and visual edits; music-only, speech-heavy and silent clips; rapid and slow editing; different durations and creator sizes.

For each clip, review:
- duration, dimensions, FPS and audio status;
- transcript against actual audio;
- OCR against visible on-screen text;
- cut candidates against the frame sequence;
- optical-flow peaks against visible movement;
- timestamp bounds and evidence references;
- warnings, skipped/partial/failed extractor states;
- source/rights basis and whether training permission is explicit.

Use the CSV review queue to record reviewer, correctness, notes and final review status. An unreviewed automated analysis is not a gold label.

## 9. Automated tests

    ruff check src tests
    pytest -q

## Troubleshooting

- **ffprobe/ffmpeg missing:** install FFmpeg, reopen PowerShell and re-run `shorts-lm doctor`.
- **Rights rejection:** fix the record only after checking the actual permission; do not change flags just to pass validation.
- **Fewer than 300 eligible clips:** add more authorized files or use `--allow-shortfall` and report the smaller sample.
- **Creator cap reduces selection:** inspect creator coverage and, where justified, increase `--max-per-creator`.
- **Creator-relative scores unavailable:** provide at least three comparable creator uploads per platform/language/topic/metric and comparable age bands.
- **Matched-pair count is low:** the sample may not contain pairs meeting the matching criteria. Do not weaken rules merely to inflate pair count.
- **ASR/OCR skipped:** install the Phase 1 audio/OCR extras or VidTrace integrations and rerun `shorts-lm doctor`.
- **Disk pressure:** omit `--keep-artifacts` initially; inspect generated frame artifact sizes.
- **Resume does not skip a record:** a media checksum, rights reference/expiry or config changed. This is intentional; the record is reprocessed.
