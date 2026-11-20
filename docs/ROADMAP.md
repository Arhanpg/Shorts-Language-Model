# Implementation Roadmap

## Phase 0 — Repository foundation

- Define package structure, Python version and lockfile.
- Define rights capability model and source registry.
- Define versioned Pydantic schemas.
- Add environment template, ignore rules, logging and tests.
- Add 25–50 synthetic/authorized smoke fixtures (do not commit unlicensed media).
- Add CI for lint, types, schema and unit tests.

**Exit:** clean install and schema/rights tests pass.

## Phase 1 — Single-video telemetry MVP

Command target:

    python -m shorts_intelligence analyze --input ./authorized_clip.mp4 --output ./out/analysis.json

Implement incrementally: media validation/ffprobe; audio extraction and faster-whisper; OCR; PySceneDetect and/or TransNetV2; OpenCV motion; librosa features; hook-aware keyframes; JSON report and Pydantic validation.

**Exit:** manually audit 25–50 clips including rapid edits, dialogue-free music edits, Hindi/English and at least one non-Indic language. Report extraction errors and unsupported labels.

## Phase 2 — Pilot data and annotation

- Register 300 permitted videos.
- Build stratified selection manifest.
- Deduplicate and group creator identities pseudonymously.
- Produce telemetry packages.
- Draft labels with a model only where permitted.
- Human-review priority labels and uncertain cases.
- Build cost and data-quality dashboard.

**Exit:** provenance, coverage, measured costs and annotation quality.

## Phase 3 — Model bake-off

- Test Qwen3-VL-2B, Qwen3.5 candidates, VideoLLaMA3-2B and SmolVLM2-500M where runtime permits.
- Compare frozen model with non-LLM baselines.
- Version exact inputs and prompts.

**Exit:** decision memo naming best candidates per resource tier.

## Phase 4 — Dataset v1 and SFT

- Expand reviewed samples to 1K–2K, then 5K if pilot supports it.
- Build creator/time-disjoint splits.
- Run smoke/overfit checks.
- Train LoRA/DoRA on rented GPU with exact model-supported recipe.
- Save adapters, checkpoints, configs, logs and benchmark outputs.

**Exit:** repeatable improvement over frozen base on locked test set.

## Phase 5 — Creator-relative performance model

- Build outcomes from authorized snapshots and creator analytics.
- Create matched controls.
- Train LightGBM/ranker baseline.
- Test creator/time holdout and subgroup calibration.
- Separate descriptive hypotheses from causal conclusions.

**Exit:** adds measurable value over metadata-only baseline and reports uncertainty.

## Phase 6 — Local deployment

- Merge/quantize only supported checkpoints.
- Verify exact multimodal input path.
- Test on Windows and Linux where available.
- Measure peak VRAM/RAM, CPU fallback, speed, latency and quality degradation.
- Publish CLI and model card.

**Exit:** documented hardware matrix with honest limits.

## Phase 7 — Product UI and expanded research

- Gradio/Streamlit first; Next.js only when required.
- Add batch queue, saved reports and user review.
- Expand 10K → 20K → 50K+ only when cost/quality/rights gates pass.
- Add optional teacher distillation and RL only after SFT evaluation.

## First pull-request-sized tasks

1. Add rights-aware source and telemetry schemas.
2. Add ffprobe and bounded FFmpeg preprocessing.
3. Add scene/keyframe manifest.
4. Add ASR and acoustic feature adapters.
5. Add OCR and motion adapters.
6. Validate evidence-linked analysis JSON.

Avoid creating a large empty scaffold with every cloud service before Phase 1 works.
