# Model Selection and Training Plan

## 1. Candidate evaluation, not model-name commitment

Benchmark candidates on the same 100–300 authorized clips, frame budget, transcript/OCR package and prompts.

| Candidate | Role | Key question |
|---|---|---|
| Qwen3-VL-2B | Initial compact VLM baseline | Does it understand short clips and produce useful time-grounded outputs? |
| Qwen3.5-2B | Alternative compact candidate | Does exact checkpoint and runtime support required video/frame inputs, multilingual OCR and local deployment? |
| Qwen3.5-4B | Higher-quality stretch candidate | Does quality justify cloud training and local resource cost? |
| VideoLLaMA3-2B | Video-centric comparison | Is temporal understanding stronger on our tasks? |
| SmolVLM2-500M | Low-resource baseline | Can it validate pipeline and CPU fallback? |

Confirm exact model ID, model card, license, code dependencies, Transformers version, processor/video conventions, training recipe, quantization and inference backend at time of use. Family names alone are insufficient.

## 2. Frozen baseline first

Compare:
- rules/telemetry + templated report;
- metadata-only LightGBM;
- transcript/OCR text model;
- frozen visual embeddings + classifier;
- frozen VLM with structured prompting;
- retrieval over reviewed examples.

Fine-tuning is justified only when a base model has a repeatable weakness and we have labels that can improve it.

## 3. SFT data

Input package: timestamped keyframes, evidence JSON, transcript segments, OCR spans and metadata permitted for the task. Keep private media references outside public JSONL. Each task example should have one target schema and evidence references.

Train concise and verifiable outputs; long opaque chain-of-thought traces are not required. Short rationale fields linked to evidence are preferable.

## 4. Fine-tuning recipe

Start with LoRA/DoRA if the selected model and library support them. Freeze vision tower initially; test projector/language adapter choices. Use the model-specific chat template and multimodal collator. Do not copy a YAML recipe from a different model generation without verifying support.

For Qwen3.5, Unsloth's published guidance currently reports approximate BF16 LoRA memory of 5 GB for 2B and 10 GB for 4B, and advises against 4-bit QLoRA due to quantization differences. This points to rented GPU training. Exact memory depends on frames, resolution, context, batch, optimizer, checkpointing and framework; these figures are not a guarantee.

Experiment order:
1. 100–300 examples: data collator and one-step smoke test.
2. 1K reviewed examples: intentionally overfit a tiny subset to validate loss and output formatting.
3. 5K–10K approved examples: first real SFT experiment, conservative epochs and early stopping.
4. Compare base vs adapter and run ablations.
5. Expand to 20K–50K only when gains are stable across held-out creators and languages.

Pin seeds, package versions, checkpoint hashes, data version, tokenizer/chat template and training config. Test adapter recovery from checkpoints.

## 5. Teacher models

A teacher can draft labels, but is optional. Prefer open-weight teachers with compatible licenses and reproducible execution. Before using a hosted model API, verify current terms permit creating training data for another model and that outputs can be published. Open weights alone do not automatically clear every training-data issue.

Store teacher draft, verifier output and human correction separately. Do not count teacher outputs as ground truth without audit.

## 6. Reinforcement learning

Defer GRPO/other RL until SFT outputs are schema-valid and useful; deterministic reward checks cover factual claims; reward-hacking tests exist; training infrastructure is stable; and added benefit can be measured against SFT-only.

Possible verifiable rewards later: JSON schema validity, timestamp within duration, evidence-reference existence, no contradiction with measured cut/OCR/audio values, and pairwise rank accuracy on held-out matched examples. These rewards do not prove that a subjective “why it worked” explanation is true.

## 7. Quantization and deployment

After a quality-validated checkpoint:
- merge adapters only if compatible and required;
- benchmark supported formats/runtimes;
- test quantization levels on real clips;
- verify multimodal projector compatibility and exact video/image path;
- compare quantized outputs with full-precision checkpoint;
- record memory, context, frame count, latency and error rate.

Do not promise GGUF support until llama.cpp has a matching architecture/projector implementation. Keep Transformers inference as reference path.

## 8. Provisional release names

- ShortsLM-Lite — smallest tested deployment variant;
- ShortsLM-2B — 2B-class candidate;
- ShortsLM-4B — optional 4B-class candidate.

Do not call them trained models or publish weights until gates pass. Include base-model license and training-data provenance in each model card.
