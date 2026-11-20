# Supplied Proposal Notes — Preserved and Consolidated

The long pasted proposal set from 20 November 2026 is consolidated rather than reproduced verbatim because several versions repeat and conflict. The complete decision-by-decision assessment is in the Research Comparison document.

## Proposal families received

1. Hybrid neuro-symbolic telemetry + Qwen3.5 2B/4B + optional 235B teacher + SFT/GRPO + GGUF.
2. ReelScope-style product: upload/link analysis, structured JSON and creator feedback.
3. Video-language model fine-tuning with OCR/ASR/scene/motion specialists.
4. Scale-first ingestion and cloud architecture with provider adapters and sharded artifacts.
5. Creator-relative performance with same-creator matched controls.
6. Small-model route: SmolVLM2-500M for smoke tests, Qwen3-VL-2B candidate, predictor baseline before VLM fine-tuning.

## Consolidated final position

- Keep deterministic telemetry, evidence-grounded VLM and separate tabular performance estimator.
- Keep creator-relative matched-control sampling as a hypothesis to evaluate.
- Start with 300 videos, then 1K–2K and 5K–10K; grow only when gains justify cost.
- Benchmark model candidates; do not hard-code one family before tests.
- Use model-specific supported LoRA/DoRA training; Qwen3.5 4-bit QLoRA is not the default because current Unsloth guidance warns against it.
- Treat teacher distillation and GRPO as optional later-stage techniques.
- Treat cost, VRAM and speed numbers as unverified until measured on actual hardware and billing accounts.
- Use only rights-cleared media and approved metadata access.
