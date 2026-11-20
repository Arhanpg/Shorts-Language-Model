# Phase 2 — 300-Video Diagnostic Pilot

## Objective

Build a reproducible diagnostic corpus of up to 300 **rights-cleared local video files**, determine whether the Phase 1 telemetry pipeline behaves reliably across the target strata, measure processing time/storage and failures, and prepare a human-review queue.

Phase 2 does not scrape platforms, fetch video URLs, generate LLM labels, train a VLM or claim causal virality drivers.

## Workflow

    Private candidate JSONL manifest
             |
             v
    Schema + rights-capability gate
             |
             v
    Local path / size / checksum / ffprobe validation
             |
             v
    Duplicate removal + data-quality summary
             |
             v
    Creator pseudonymization (local HMAC salt)
             |
             v
    Six-axis deterministic stratified selection
             |
             +--> Creator-relative performance (when comparable posts exist)
             +--> Same-creator comparison candidates
             +--> Human-review queue
             |
             v
    Private selected manifest
             |
             v
    Sequential Phase 1 telemetry (resumable)
             |
             v
    Processing metrics + pilot report
             |
             v
    Human audit and Phase 2 exit gate

## Candidate manifest

Create a JSONL template:

    shorts-lm pilot template --output data/private/manifest.example.jsonl

Copy/edit it to `data/private/candidates.jsonl`. Each line is one JSON object.

Important fields:

- unique `record_id`;
- `platform` and a local `media_path`;
- private `creator_id` where known and lawfully retained;
- `rights.basis` and a private `rights.evidence_ref`;
- explicit booleans for media analysis, temporary processing, derived-artifact retention, raw retention, model training and public redistribution;
- language, topic and speech mode;
- optional timezone-aware publication date;
- optional metric snapshot with metric name, value, source and observation timestamp.

Media paths may be absolute or relative to the manifest file. The pipeline never fetches URLs.

The candidate manifest is private working data. Its raw creator IDs, source references, consent references and local paths must never be committed to GitHub. Do not put consent documents or personal information in `evidence_ref`; use a private internal reference identifier.

## Rights semantics

For pilot telemetry processing, a record must have current:

- `media_analysis=true`;
- `temporary_processing=true`;
- `derived_artifact_retention=true`.

Raw media retention is not required. Phase 1's extracted WAV is temporary and deleted after processing. `model_training` is independent and defaults to false. Use `--require-training-rights` only when validating a candidate pool intended specifically for model training.

A user-entered permission field is not proof of permission. Check the actual agreement, dataset license and third-party rights (including music, performers, overlays and any personal data). A public URL, view count or API metadata record is not a media/training license.

The selected manifest carries the permission-expiry timestamp. Processing checks that timestamp again before processing/resuming. If consent is revoked or changed, update the private candidate manifest and re-run validation and sampling; the tool cannot independently query a private consent registry.

## Sampling methodology

The selector allocates marginal coverage across six dimensions:

1. platform;
2. language;
3. topic;
4. duration band;
5. performance tier;
6. speech mode.

It calculates proportional marginal quotas and greedily selects records that fill the largest outstanding deficits. A fixed seed makes selection repeatable. By default, no more than five selected videos are taken from one pseudonymous creator group.

This is a **coverage heuristic**, not a uniform or probability sample. It may not produce a statistically representative sample of all Reels/Shorts. The candidate-pool and selected counts are preserved in `coverage.csv`. A future population study needs a defined sampling frame, inclusion probabilities and weights.

## Creator pseudonymization

Creator IDs are converted to platform-scoped HMAC-SHA256 pseudonyms using a local random 32-byte salt stored at `.shortslm/creator_salt`. The selected manifest contains only the pseudonym, not the source creator ID. Keep this salt private and back it up securely if consistent pseudonyms are needed in future runs. Losing it means the pseudonyms cannot be reproduced.

## Creator-relative performance

A relative outcome is calculated only when at least three comparable posts exist for the same pseudonymous creator, platform, language, topic, metric definition and coarse video-age band.

    relative_log_score = log1p(video_metric) - median(log1p(comparable_creator_metrics))
    relative_multiple = exp(relative_log_score)

This can reduce the effect of a creator's typical reach. It does not correct exposure, promotion, geography, recommendation systems, topic differences within a category or viewer retention. Different platform metric definitions are kept separate. The age bands are coarse and are a first diagnostic control, not a validated statistical adjustment.

## Same-creator matched controls

The matcher proposes comparison candidates where:

- positive relative multiple >= 2.0;
- control relative multiple <= 0.5;
- same pseudonymous creator, platform, language, topic and metric name;
- publication gap <= 60 days;
- duration difference <= 30%.

A control can be used once. Matching is greedy and deterministic. A match is an observational comparison, not a causal pair.

## Outputs

The private pilot output folder contains:

- `validation_summary.json`: accepted/rejected/duplicate counts and issues;
- `selected_manifest.jsonl`: selected local paths, checksums, permissions and pseudonymous creator IDs;
- `selection_report.json`: requested target, actual selection, shortfall, seed and coverage;
- `coverage.csv`: candidate vs. selected counts by sampling dimension;
- `matched_pairs.csv`: same-creator comparison candidates;
- `review_queue.csv`: blank fields for human annotation;
- `telemetry/*.analysis.json`: Phase 1 reports per video;
- `telemetry/*.run.json`: local resume fingerprints;
- `processing_metrics.jsonl/.csv`: per-video wall time, input/report/artifact sizes, extraction counts and status;
- `processing_summary.json`: totals and quality slices;
- `final_pilot_report.json`: combined diagnostic summary.

These are private local data products. Git ignores `data/`, `outputs/` and `.shortslm/`.

## Resume behavior

Pilot processing runs sequentially. A completed report may be reused only when:

- the current input file still matches the selected manifest checksum and size;
- the report checksum matches the selected record;
- the hashed rights reference and expiry match;
- the pipeline configuration fingerprint matches.

Change `--asr-model`, OCR/ASR toggles, keyframe budget or other configuration and the previous report is recomputed. Permission expiry is checked before reusing a report. For a rights change/revocation, edit the private candidate manifest and rebuild the selected manifest.

## Quality and cost measurement

The processor measures:
- local wall time;
- input file size per selected record;
- JSON report and generated keyframe artifact bytes;
- number of frames/cut candidates, ASR segments and OCR spans;
- status for each extractor;
- processing success/failure and quality slices by platform, language, topic, speech mode and duration band.

Byte totals are file/artifact sizes, not disk-controller I/O counters. The tool does not infer a cloud bill, GPU rental expense, license fee or human-review cost. Add provider invoices and reviewer minutes separately before publishing any cost-per-video claim.

## Phase 2 exit gate

Phase 2 can be called empirically complete only after the actual run and human audit:

- up to 300 accepted, unique, rights-cleared records are selected and processed, or a shortfall is documented;
- source/rights coverage, missingness and duplicate rates are reviewed;
- language/topic/duration/platform/speech strata are reviewed;
- 25–50 clips receive manual audit for transcript, OCR, cut and motion telemetry;
- music-only and silent/no-speech examples are included;
- partial/failed ASR/OCR stages are reported honestly;
- suggested matched pairs are checked by a human and never treated as causal evidence;
- wall time, artifact sizes and reviewer time are recorded;
- model-training eligibility is separated by explicit permission.

A 300-video diagnostic pilot is not automatically a representative sample of the global platforms or a model-training-ready gold dataset.
