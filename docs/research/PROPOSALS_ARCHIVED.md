# Supplied Proposal Notes — Preserved and Consolidated

The long proposal set supplied on 20 November 2026 contained repeated sections and conflicting assumptions. The distinct proposal families are now preserved as separate, detailed research notes rather than one enormous duplicated transcript.

## Detailed proposal archives

1. [Hybrid ViralLens: deterministic telemetry, Qwen3.5, SFT/GRPO and local GGUF](proposals/01-hybrid-virallens-qwen35.md)
2. [ReelScope: upload-first creator copilot](proposals/02-reelscope-upload-first.md)
3. [Creator-normalized 20K dataset and small-model route](proposals/03-creator-normalized-20k.md)
4. [Scale-first cloud pipeline and distributed data factory](proposals/04-scale-first-cloud-pipeline.md)

See the [proposal index](proposals/README.md) for the full archive and the [research comparison](RESEARCH_COMPARISON.md) for accepted/rejected insights and final decisions.

## Consolidated final position

- Keep deterministic telemetry, evidence-grounded VLM and separate tabular performance estimator.
- Keep creator-relative matched-control sampling as a hypothesis to evaluate.
- Start with 300 videos, then 1K–2K and 5K–10K; grow only when measured gains justify cost.
- Benchmark model candidates; do not hard-code one family before tests.
- Use model-specific supported LoRA/DoRA training; Qwen3.5 4-bit QLoRA is not the default because current Unsloth guidance warns against it.
- Treat teacher distillation and GRPO as optional later-stage techniques.
- Treat cost, VRAM and speed numbers as unverified until measured on actual hardware and billing accounts.
- Use only rights-cleared media and approved metadata access.
