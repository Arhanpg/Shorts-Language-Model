# Model Selection and Training Plan

**Updated:** 24 November 2026  
**Status:** candidate policy; no final pretrained VLM is selected yet.

## 1. Decision summary

ShortsLM will not train a foundation model from scratch. It will first build deterministic timestamped telemetry, benchmark existing extractors and establish frozen baselines. Only then will it train a compact task-specific temporal fusion model and a separate performance estimator.

The default path should not require a Hugging Face token or multiple model-provider accounts. Use existing local adapters and public checkpoints. Any gated model is optional and must justify its setup burden with measured benefit.

## 2. Minimal model/tool policy

| Task | Default | Optional candidate | Do not make default |
|---|---|---|---|
| ASR | Existing faster-whisper adapter; benchmark one `large-v3-turbo` INT8 candidate | Sarvam Saaras API only if Indic/code-switch evaluation demonstrates a gap | Canary + Parakeet + IndicConformer + SraVaani + ElevenLabs + NeMo ensemble |
| OCR | Existing PaddleOCR adapter | Targeted script-specific fallback after evaluation | Multiple OCR engines in every run |
| VAD | Existing VAD implementation | Silero VAD if current implementation fails quality/runtime gate | Several parallel VADs |
| Audio | NumPy/librosa signal features | One lightweight sound-event model | BEATs + MERT + CLAP + Beat This! + HTDemucs all at once |
| Shot/motion | Existing shot logic + OpenCV baseline | TransNetV2 if it adds measurable cut recall | RAFT/GMFlow by default |
| Pose/action | One selected pose model after benchmark | General action head trained from reviewed labels | Multiple detectors, pose systems and video encoders simultaneously |
| Video reasoning | Deterministic evidence-first outputs | One optional Gemini API key for selected clips | Multiple VLM APIs and local 7B/30B model downloads |
| Engagement | CatBoost baseline | LightGBM/ranking/survival after data sufficiency | A single opaque “viral score” |

The existing project dependencies and adapters are the source of truth for what is currently installed. Do not replace a working component solely because a research report lists a newer model.

## 3. Candidate bake-off

Use the same 100–300 authorized clips, frame budget, audio/transcript/OCR inputs, prompts and locked evaluation sample.

### ASR comparison
- Current configured faster-whisper model.
- One `large-v3-turbo` INT8 candidate.
- Optional Sarvam Saaras only if a measured language-specific gap remains and the user explicitly enables it.

Measure normalized WER/CER, code-switch-region error, language-span F1, timestamp error, entity preservation, non-speech hallucination rate, throughput and peak VRAM/RAM. Report per-language/script and music/noise subgroup metrics. Do not select from vendor leaderboard claims alone.

### VLM comparison
At most one compact open-weight checkpoint and one optional Gemini API comparison. Verify:
- exact model/checkpoint license and commercial restrictions;
- supported image/video input path and temporal handling;
- model card, tokenizer, processor and inference runtime;
- peak VRAM/RAM, latency and cost at fixed frame/token budget;
- grounded temporal QA, action recognition, OCR robustness, multilingual understanding and speech-free performance.

The candidates in older docs (Qwen3-VL, Qwen3.5, VideoLLaMA3, SmolVLM2 and others) remain candidates only. The exact 2B/4B model, checkpoint, license and runtime must be checked at decision time. Do not promise 4 GB local fit from parameter count or quantization alone.

## 4. Baselines before training

Run the following:
1. Majority/prior baseline for each label.
2. Transcript-only.
3. OCR-only.
4. Audio-only.
5. Visual/pose-only where available.
6. Metadata-only.
7. Combined deterministic features.
8. Frozen embedding + CatBoost only if the embedding model license permits use.

This establishes whether expensive multimodal learning adds value beyond interpretable telemetry.

## 5. ShortsLM temporal fusion model

After a reviewed gold set exists, train a compact temporal model over 1–2 second windows:
- modality-specific projection layers;
- explicit presence/missingness masks;
- confidence/quality inputs;
- PTS-aware temporal encoding;
- confidence-gated fusion;
- task heads for action/event labels, hook/edit localization and temporal summaries.

A 5M–30M parameter range is an initial engineering target, not a fixed specification. Start with a temporal convolution or small Transformer and compare against CatBoost/LightGBM. The model is trained from scratch only as a task-specific fusion head, not as a foundation VLM.

### Candidate objectives
- Multi-label classification: weighted BCE or focal loss only if class imbalance justifies it.
- Temporal localization: interval regression or start/end classification with temporal IoU evaluation.
- Contrastive audio/video/text alignment (InfoNCE): later experiment, with false-negative masking for repeated trending audio and repost templates.
- Multi-task learning: share representations only where task labels and missingness semantics are consistent.
- Confidence calibration: temperature scaling or task-specific calibration on a held-out calibration split.

Do not add graph neural networks, MoE routing, GRPO or reinforcement learning before a simpler model has a reproducible failure that these methods can address.

## 6. Engagement model (separate from content understanding)

First baseline: CatBoost regression and/or ranking using structured features.

Potential targets, only when data is sufficient and permitted:
- creator-relative performance percentile/uplift;
- platform/category/duration/age cohort rank;
- time-to-threshold with censoring;
- engagement-rate targets where valid denominators exist.

Store raw snapshots and derived targets separately. Use observation age, creator baseline, duration, category, language and platform as confounder controls. Do not use future snapshots or post-publication information in pre-publication prediction. Keep platform metric definitions separate.

Evaluation: MAE/RMSE/Huber, Spearman/Kendall/NDCG, calibration, interval coverage and subgroup metrics. Creator-disjoint and forward-time splits are mandatory. A public view counter cannot reveal impressions or retention; richer watch-time/skip labels require creator-authorized analytics.

## 7. Training procedure

1. Verify rights for training for every media item.
2. Deduplicate exact and perceptual copies; group creator/audio/template/repost relationships.
3. Produce human-reviewed annotations with versioned instructions and adjudication.
4. Lock creator-disjoint and forward-time splits.
5. Freeze deterministic extractor versions and feature schema.
6. Run baseline metrics.
7. Train a compact temporal head; record seed, config, data manifest hash, code commit and environment.
8. Compare with baseline and run ablations.
9. Calibrate on a distinct calibration set.
10. Publish a model card and dataset card with limitations and rights provenance.

Only after the frozen VLM comparison should LoRA/adapter SFT be attempted. Use a rented GPU and checkpointed training. The RTX 3050 4 GB is for local extraction, smoke tests and small quantized inference—not multimodal 2B/4B training.

## 8. Evaluation and release gates

- ASR: WER/CER, code-switch boundary F1, language-span accuracy, hallucination rate, timestamp error.
- OCR: script-wise CER, recall, bbox and timing accuracy.
- Audio: event F1/mAP, beat/onset error, speech/music occupancy error.
- Action: per-class precision/recall/F1, temporal IoU, abstention quality.
- Multimodal: grounded evidence precision, hallucination rate, speech-free subgroup, modality ablation.
- Engagement: ranking/regression metrics, calibration, creator/time split results and cohort stability.
- Operations: latency, VRAM/RAM, failure/retry, cost per accepted example and model/license provenance.

No model is promoted based on a demo or training loss alone.

## 9. Deployment

Keep Transformers/PyTorch or the selected model's official runtime as the reference path. Test quantization and GGUF/llama.cpp only when the exact architecture, projector and multimodal input path are supported. Record quality delta, context, frame count, peak memory and end-to-end latency.

Provisional names:
- ShortsLM-Lite — smallest tested deployment;
- ShortsLM-Fusion — temporal feature-fusion model;
- ShortsLM-VLM — optional adapted VLM, only if trained and released.

Do not use these names to imply that weights already exist.
