# Proposal 1 — Hybrid ViralLens with Qwen3.5

## Original direction

Build a multilingual short-form video forensic model using deterministic audiovisual telemetry as a front-end and a compact multimodal decoder as the reasoning student. The proposal emphasized a single platform-conditioned model shared across YouTube Shorts and Instagram Reels, with a separate performance research objective.

## Proposed architecture

### Data and sampling

- Target a 50,000-video research corpus as the proposed production sweet spot.
- Suggested 70/30 mix: 35,000 positive/outlier videos and 15,000 same-creator matched controls.
- Stratify across language, geography, content niches and creator baselines.
- Avoid training only on >1M-view videos; include underperforming uploads from the same creators.
- Use creator-relative performance, e.g. log outcome relative to a robust creator baseline.

### Deterministic telemetry

| Lane | Proposed tools | Proposed outputs |
|---|---|---|
| Shot/cut | TransNetV2, AutoShot | cut times, average shot length, hook cut density |
| Motion/VFX | RAFT/GMFlow, OpenCV | optical flow, zoom/pan/shake candidates, speed changes |
| OCR | PaddleOCR | timed text, hook text, position and overlay density |
| Speech | faster-whisper, IndicConformer | language ID and timestamped transcript |
| Audio | librosa, CLAP | tempo, onsets, loudness, beat-to-cut relationship, sound-event candidates |
| Keyframes | hook-aware selector | dense opening frames, cut-adjacent frames, climax and loop seam |

The proposal suggests 12–16 carefully selected keyframes plus structured telemetry, rather than sending every raw frame to the VLM.

### Model and training

- Primary student proposal: Qwen3.5-4B.
- Smaller companion: Qwen3.5-2B.
- Optional larger teacher: Qwen3-VL-235B-A22B-Instruct or another open-weight teacher with compatible terms.
- SFT with BF16 LoRA/DoRA; freeze the vision tower initially.
- Include general multimodal replay data to reduce catastrophic forgetting.
- Optional GRPO with verifier-based rewards for JSON validity, telemetry consistency and pairwise ranking.
- Merge and quantize for GGUF/llama.cpp local inference.

### Local deployment idea

- Use 4B as a higher-quality tier and 2B as a Lite tier.
- CPU-offload the vision projector where the runtime permits.
- Keep language-model layers on GPU where possible.
- Measure VRAM, context, frame budget, latency and decode speed on the RTX 3050 instead of relying on theoretical estimates.

## What the combined plan accepts

1. The neuro-symbolic architecture: deterministic facts first, language-model interpretation second.
2. Fine-grained temporal telemetry for short edits.
3. Hook-aware sampling rather than a fixed sparse frame rate.
4. Shared cross-platform video-editing representation, with platform metrics kept separate.
5. Creator-relative matched controls as an experiment to reduce creator-size confounding.
6. A small model release paired with optional stronger cloud analysis.
7. Evidence verification and explicit uncertainty.

## What remains unverified or is deferred

- **50K as the optimum:** not established; size follows measured learning curves and task coverage.
- **235B teacher:** optional; cost, terms, latency and label quality need an audited pilot.
- **GRPO:** deferred until SFT is stable and verifiable rewards are shown not to be gameable.
- **Exact 4GB fit and token speeds:** require runtime-specific measurements; theoretical memory arithmetic is not an acceptance test.
- **Qwen3.5 BF16 LoRA:** current Unsloth guidance reports approximately 5 GB VRAM for 2B and 10 GB for 4B, and discourages 4-bit QLoRA for this family. Rented-GPU training is therefore the safer planning assumption.
- **Exact cloud costs and teacher rates:** no project-specific benchmark or account quote has validated them.
- **Long chain-of-thought traces:** not required; concise, evidence-linked explanations are more auditable.

## Final disposition

**Accepted as the core architecture, not as the fixed recipe.** The telemetry-first approach is central to the project. Model checkpoint, teacher, training method, data size, cost and quantization configuration are decided through benchmarks and rights audits, not by adopting the proposal's unverified numeric claims.
