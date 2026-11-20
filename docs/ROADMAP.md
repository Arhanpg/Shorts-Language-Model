# Revised Implementation Roadmap

**Revised on:** 21 November 2026  
This roadmap replaces the prior assumption that candidates are manually placed in a local MP4 manifest.

## Phase 0 — Provider and rights foundation

- Lock source matrix and permission-capability schema.
- Register YouTube Data API project/quota and local secrets.
- Decide whether to apply for YouTube's third-party AI-training company list.
- Check whether the project can apply for Meta Content Library through a qualified research institution.
- Define policy-aware API-data retention/deletion and SQLite schema.
- Add provider contracts and mock fixtures.

**Exit:** each enabled source has documented discovery scope, permitted fields, quota, retention rules and media-delivery status. No provider is marked as a downloader by assumption.

## Phase 1 — Automated discovery and SQLite inventory

- Implement YouTube Data API metadata discovery.
- Implement Instagram Business Discovery provider interface for eligible known professional accounts.
- Add optional Meta research metadata provider only if access is approved.
- Generate seeded stratified queries across language/region/topic/date.
- Filter on a current 1M+ metric snapshot.
- Track Shorts/Reels format confidence rather than infer from one field.
- Deduplicate source items in SQLite within source-specific retention rules.
- Expose target-new 100/200 and maximum candidate/query budget.
- Add quota, retention, duplicate and partial-yield reports.

**Exit:** replaying provider pages creates no duplicate rows; a second run returns unseen candidates where available; expired metadata is refreshed/deleted; report shows actual yield and API quota.

## Phase 2 — Rights-gated automatic media delivery

Implement only media providers with a real authorized delivery contract:
- YouTube third-party training share, if project/company is approved and required creators/rightsholders opted in;
- creator-authorized media inbox or connected cloud-drive delivery;
- licensed dataset/provider downloads;
- approved platform/research handoff only where agreement permits media export.

Keep metadata-only candidates in a deferred state. No yt-dlp or browser-scraping fallback.

**Exit:** every acquired asset has delivery provenance, rights evidence, model-training permission, SHA-256, file properties, retention period and revocation/deletion route.

## Phase 3 — Automated multimodal processing

- Reuse existing Phase 1 single-video analyzer as processing engine.
- Add batch workers, checksums, retries and resumable state.
- Extract transcript/ASR, OCR, frames, scenes/cuts, motion, audio and VFX candidates.
- Store per-stage tool versions, confidence and error state.
- Process 10 videos, then 100, then 300 rights-cleared assets.

**Exit:** processing metrics and manual audit demonstrate acceptable quality by language/topic/speech mode.

## Phase 4 — Dataset QA and annotation

- Deduplicate byte-identical and perceptually similar cross-posts.
- Add review queue for hook, editing taxonomy, OCR/ASR, narrative and retention hypothesis.
- Create gold labels with reviewer/version provenance.
- Split by creator and time; lock golden holdout.

**Exit:** 1K–2K reviewed examples with coverage and inter-annotator agreement reported.

## Phase 5 — Model bake-off and baselines

- Compare compact VLM prompting against visual, text, telemetry and retrieval baselines.
- Benchmark Qwen3-VL-2B, Qwen3.5-2B, SmolVLM2-500M and VideoLLaMA3-2B candidates.
- Add platform-specific performance models only where provider policy/rights permit.
- Separate descriptive editing analysis from performance estimation.

**Exit:** model decision report and measured frozen baseline on locked test data.

## Phase 6 — Cloud fine-tuning

- Build training shards from rights-cleared, training-permitted examples only.
- Apply LoRA/DoRA with exact model-supported settings.
- Use cloud GPUs, checkpoints, experiment tracking and budget caps.
- Keep creator/time/platform leakage out of evaluation splits.

**Exit:** repeatable improvement over the frozen model on predeclared tasks without material multilingual regressions.

## Phase 7 — Quantized local deployment

- Export only a supported multimodal checkpoint.
- Benchmark CPU, RTX 3050 4 GB and other target devices.
- Measure peak VRAM/RAM, end-to-end latency, context/frame budget and quantization quality.
- Package CLI/API/UI and publish model card.

**Exit:** real hardware acceptance matrix; do not promise fit on every 4 GB GPU.

## Phase 8 — Controlled expansion

Expand 1K → 5K → 20K → 50K+ only when previous tier demonstrates quality, rights coverage, unit economics and marginal model improvement. Crore-scale acquisition requires platform agreements/licensed feeds and distributed infrastructure; it is not implied by local database design.

## Existing work mapping

- Original Phase 1 local-video analyzer is retained for revised Phase 3.
- Earlier Phase 2 local-manifest code/PR #4 may be reused as downstream QA/processing support, but it does not implement automated discovery or authorized media delivery. Reconcile it with Phases 1–3 before treating it as the new ingestion layer.
