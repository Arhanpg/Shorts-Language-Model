# Implementation Roadmap

## Phase 0 — Repository foundation

- Define package structure, Python version and lockfile.
- Define rights capability model and source registry.
- Define versioned Pydantic schemas.
- Add environment template, ignore rules, logging and tests.
- Add synthetic/authorized smoke fixtures (do not commit unlicensed media).
- Add CI for lint, types, schema and unit tests.

**Exit:** clean install and schema/rights tests pass.

## Phase 1 — Single-video telemetry MVP

Command:

    shorts-lm analyze --input ./authorized_clip.mp4 --output ./out/analysis.json --rights-basis creator_owned

Implement media validation/ffprobe; temporary audio extraction; faster-whisper; PaddleOCR; bounded hook-aware frames; cut candidates; OpenCV motion; librosa features; Pydantic evidence report.

**Exit:** local Windows/WSL validation on 25–50 diverse clips, including rapid edits, dialogue-free music edits and multilingual speech. The code is implemented; laptop acceptance remains a user-side validation gate.

## Phase 2 — 300-video diagnostic pilot

Implemented workflow:
- Rights-capability-gated private JSONL candidate manifest.
- Local path, file size, checksum, ffprobe and duplicate validation.
- HMAC creator pseudonyms using a private local salt.
- Deterministic stratified selection across platform, language, topic, duration, performance tier and speech mode.
- Creator-relative metrics within same creator/platform/language/topic/metric/age cohorts (minimum three records).
- Same-creator positive/control comparison candidates with documented matching thresholds.
- Private selected manifest, coverage report and human-review queue.
- Sequential, configuration/checksum/permission-expiry-aware resumable Phase 1 processing.
- Processing wall-time, file/artifact-size, extractor-status and per-stratum quality reports.
- Setup guide, tests and CI integration.

**Important:** code implementation is not the same as a completed empirical 300-video pilot. The exit gate requires the repository owner to supply 300 unique local videos with valid rights, run the pipeline, audit 25–50 outputs, review coverage/missingness and record human-review effort. A documented shortfall is acceptable for a diagnostic pilot; rights checks must not be bypassed.

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

Avoid creating a large empty scaffold with every cloud service before the data and telemetry pipeline works.
