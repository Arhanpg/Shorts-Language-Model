# Phase 4–5 dataset and evaluation plan

This plan builds on DATASET_AND_LABELING.md, ROADMAP.md and the reconciled research catalogue v0.1. It does not rerun or change Phase 3.

## Phase 4 — dataset QA and annotation

### 4.1 Candidate selection

Use the 71-language registry, 30-domain taxonomy, creator leads, hashtag candidates and diversity cells as discovery-planning inputs only. Start the first evaluation pilot with Kannada (spanning multiple Karnataka regions/registers), Hindi, Tamil, Telugu and English, while reserving explicit low-resource language/dialect cells. Do not promote a creator from a source report without checking the official profile, recent Shorts/Reels activity, language/register and original-publisher status.

Keep a candidate if short-form status is confirmed even when its metric is low or missing; preserve platform-native metric kind, estimate status, source and observation time. Treat one-million views as an optional high-virality cohort, not a global data-quality threshold. The current graph default remains a known mismatch until a separate implementation decision changes it.

### 4.2 Rights gate before media acquisition

For each video candidate, create a private item-level rights record before retrieving media or retaining derived artifacts. Keep download_media, store_media, analyze_video_frames, transcribe_audio, ocr_visual_text, retain_derived_artifacts, train_model and redistribution permissions separate. Unknown, expired, revoked or incomplete permissions block the relevant action. Keep consent/contract evidence and media outside Git.

### 4.3 Pilot and quality gates

Recommended first pilot: 50–100 rights-cleared assets, with actual size determined by supply and permissions. Validate:

- source identity, duration, dimensions, frame/audio presence and SHA-256;
- perceptual duplicate/repost/cross-post grouping before splits;
- ASR and OCR status, including explicit not-present/failed/low-confidence values;
- script/language/code-switch labels and human review for low-resource speech;
- frame-grounded hook, scene, editing and narrative labels with timestamps inside duration;
- audio/music/silence events and transcript alignment;
- annotation reviewer, disagreement and tool/model/prompt versions;
- metadata completeness, missingness, quality flags and item-level rights coverage.

Only labels accepted by the review workflow enter gold data. Model-generated descriptions are drafts, not ground truth. The release's 50 synthetic JSONL fixtures are unit/contract tests only; they are not part of training or accuracy evaluation.

### 4.4 Split policy

Create split groups using:

1. creator/account identity group (when legitimately known), never random rows alone;
2. video publication time (time-forward holdout);
3. exact and perceptual media duplicate/repost/cross-post group;
4. platform-specific and cross-platform transfer cohorts;
5. a frozen, access-controlled golden holdout that is not used for prompt tuning or model selection.

Report per-language, script, region/dialect, domain, platform and duration slices. Preserve YouTube views and Instagram views/plays as distinct metrics; estimated display counts must not enter exact metric buckets.

### Phase 4 exit

The roadmap target remains 1,000–2,000 reviewed examples plus a locked holdout. Do not assume AI catalogues supply these assets. Exit only when rights, source provenance, media integrity, duplicate leakage, annotation quality/agreement, coverage and retention checks pass.

## Phase 5 — baselines and model bake-off

1. Freeze the permitted dataset release, split manifest, frame sampling, resolution, audio/transcript availability and token/frame budgets.
2. Build deterministic telemetry/tabular baselines first (duration, shot density, motion, OCR/ASR coverage, audio energy, pace, edit events and other measured features).
3. Compare small pretrained multimodal candidates on the same locked data and input budget; record model licence, checkpoint, prompt, inference settings, code commit and hardware.
4. Score tasks separately: grounded summary, event/shot localization, hook detection, editing-event F1 and timestamp error, OCR exact/CER by script, ASR WER/CER by language, language identification/code-switching and calibrated abstention.
5. Report macro and per-stratum results alongside micro averages. Show uncertainty, missing modalities and failure slices; do not allow English/Hindi or a few large creators to dominate the aggregate.
6. Measure latency, peak RAM/VRAM, throughput, inference cost and reproducibility. Keep the locked holdout inaccessible to model selection.

### Phase 5 exit

Publish a frozen baseline/bake-off report with repeatable evaluation, per-language/category regressions, chosen model/checkpoint licence, hardware resource estimate and explicit limitations. A good aggregate score is not sufficient if low-resource language, script or editing tasks regress materially.

## Local catalogue installation

The complete catalogue is distributed as ShortsLM_Research_Catalogue_v0.1.zip alongside the PR review. After saving it locally, install from the repository root:

    python scripts/install_research_catalogue.py --archive ./ShortsLM_Research_Catalogue_v0.1.zip
    python scripts/validate_research_catalogue.py

The installer checks the archive manifest and hashes before extracting to data/research_catalogue/v0.1/. The release contains CSV/JSON/JSONL and Markdown research files only; no media, database, credentials or consent documents.
