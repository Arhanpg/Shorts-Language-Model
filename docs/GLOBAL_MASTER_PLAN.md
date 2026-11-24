# Shorts Language Model — Global Master Plan

**Updated:** 24 November 2026  
**Status:** research-backed project direction; implementation must pass the phase gates below.  
**Research basis:** Gemini Deep Research report (94 pages), independent technical reconciliation, and current repository documentation/source search.  
**Current acquisition policy:** retain the existing non-official-API discovery toolchain unless the project owner explicitly changes it.

## 1. Vision and product definition

ShortsLM is a multimodal short-form video intelligence system for YouTube Shorts and Instagram Reels. It must answer four distinct questions:

1. **What is happening?** Identify speech, languages/code-switching, on-screen text, people as anonymous tracks, actions, objects, scenes, music, sound events and editing.
2. **How does it unfold over time?** Align all evidence to the media timeline; detect hooks, cuts, beat changes, action intervals, reveals, transitions, narrative structure and loops.
3. **What observable factors are associated with performance?** Study platform-native engagement snapshots while controlling for creator history, duration, publication age, category and platform.
4. **What can a creator improve?** Generate evidence-grounded suggestions tied to timestamps and measurable observations, not unsupported claims of causality.

Content understanding and performance prediction are separate tasks with separate targets, datasets and evaluation. A high view count is not ground truth for quality or a causal label for virality.

## 2. Non-negotiable project principles

- Local-first, low-friction setup. No ten-vendor onboarding, no mandatory Hugging Face token, and no mandatory paid API key for baseline feature extraction.
- One default ASR model/runtime, one OCR engine, one selected pose model at most; optional fallbacks are activated only by measured quality gaps.
- Sequential model loading on the RTX 3050 4 GB. Do not assume all models fit simultaneously.
- Reuse existing FFmpeg/ffprobe, SQLite, discovery, rights-gate, VidTrace ASR/OCR adapters and current CLI where practical. Do not rebuild working components without evidence.
- Canonical time axis uses media presentation timestamps (PTS), not assumed constant frame indices.
- Every feature carries source, extractor/version, timestamp or interval, confidence/quality and semantic missingness.
- A missing modality is not a zero value. Distinguish absent-in-media, not-applicable, unavailable-from-source, permission-denied, extraction-failed and below-confidence.
- Store raw metric snapshots separately from derived normalized metrics. Preserve platform-native semantics (views ≠ plays).
- No training until item-specific training permission, quality review, deduplication, splits and baseline evaluation are in place.
- No foundation model training from scratch.
- No public claims of “viral prediction accuracy” or throughput/cost estimates without reproducible held-out evidence.
- Never bypass login, CAPTCHA, DRM, rate limits, or platform access controls. Public visibility and successful extraction do not grant rights.

## 3. Existing project baseline to preserve

The current README describes a non-official-API acquisition toolchain using ytscrape/yt-dlp for YouTube surfaces, DDGS/Instaloader for Instagram discovery/metadata, optional Instagram user session, SQLite for candidate state, FFmpeg/yt-dlp/Instaloader for permission-gated media acquisition, and existing local analyzer/VidTrace ASR/OCR adapters. Current docs also describe an RTX 3050 local workflow and sequential ASR/OCR execution.

The current repository already contains:
- `docs/ARCHITECTURE.md`, `docs/GLOBAL_MASTER_PLAN.md`, `docs/ROADMAP.md`;
- `docs/DATASET_AND_LABELING.md`, `docs/DATA_AND_COMPLIANCE.md`, `docs/RIGHTS_MANIFEST.md`;
- `docs/COMPUTE_AND_COSTS.md`, `docs/MODEL_AND_TRAINING.md`;
- phase-specific acquisition, processing, catalogue and QA workflows.

This master plan supersedes older model-name shopping lists where they conflict with the minimal-stack decision, but does not silently change discovery thresholds, platform providers, downloader behavior or rights policy. Review existing phase documentation before code changes.

## 4. Final system architecture

```text
Existing URL discovery + SQLite inventory
              |
              v
Source metadata snapshots + rights/provenance gate
              |
              v
Permission-approved media acquisition (existing workflow)
              |
              v
FFmpeg decode-once / PTS-normalized media manifest
              |
       +------+-------------------------------+
       |                                      |
       v                                      v
Audio lane                              Visual lane
VAD + one ASR model                     adaptive frames / shots
audio signal features                   OCR / motion / pose
music & sound indicators                objects / actions / scenes
       |                                      |
       +------------------+-------------------+
                          v
              Timestamped evidence timeline
        confidence + missingness + provenance
                          |
              +-----------+-----------+
              |                       |
              v                       v
     Deterministic feature       Optional VLM
     aggregation + QA            reasoning fallback
              |                       |
              +-----------+-----------+
                          v
                Versioned feature bundle
               JSONL now; Parquet later
                          |
                Human review / annotation
                          |
                 leakage-safe data splits
                          |
             +------------+-------------+
             |                          |
             v                          v
    Content understanding         Performance modelling
    temporal fusion model         CatBoost baseline first
    + grounded explanations       creator/cohort ranking
             |                          |
             +------------+-------------+
                          v
               calibrated reports / API
                          |
             quantized local deployment
```

### 4.1 Audio lane

**Default:** one faster-whisper adapter/checkpoint, selected by a reproducible comparison on representative short-form audio. Candidate checkpoint to benchmark: `large-v3-turbo` with INT8. Retain the currently working model until the new candidate passes WER, language/code-switch, timestamp, hallucination and resource tests.

Audio features initially include:
- speech presence/occupancy and VAD intervals;
- timestamped transcript segments and language probabilities;
- non-speech hallucination flags;
- music/speech/silence occupancy;
- RMS/loudness, energy curve, spectral flux/onset and tempo/beat candidates;
- coarse sound-event flags when supported by the chosen lightweight model.

Do not require multiple ASR vendors, diarization packages, music encoders, source-separation models or gated downloads in the baseline. Sarvam Saaras is the only optional Indic-ASR API candidate if local Whisper has a demonstrated Indic/code-switch quality gap. It must remain opt-in and cost-capped. No other speech API is required.

### 4.2 Visual lane

- Decode once; store PTS and frame dimensions/FPS/VFR metadata.
- Adaptive frame selection: denser in the first 3 seconds, around shot boundaries, high motion and audio events; sparse elsewhere.
- Existing OCR adapter (PaddleOCR) is the default. Validate Latin, Devanagari and code-mixed overlays on a manually reviewed sample.
- Existing shot/motion logic plus OpenCV baselines first. Add TransNetV2 only if its measured cut recall justifies installation.
- Select at most one pose estimator after license, install, runtime and accuracy checks. Run sequentially; store anonymous video-local track IDs and keypoint visibility/confidence.
- General action and object labels are initially hypotheses grounded in temporal evidence. Fine-grained dance styles are P1/P2 and must abstain on uncertain classes.
- Do not add YOLO + RT-DETR + GroundingDINO + SAM + VideoMAE + V-JEPA as a single dependency bundle.

### 4.3 Optional multimodal reasoning

One optional Gemini API key may be used for a small selected subset of difficult clips, if rights permit external processing. It is not required for baseline runs. Send only approved clips or approved derived frames/audio; never upload private or non-consented media by default. Store provider/model/prompt/version, input scope, cost and evidence references. Enforce a monthly spend cap and sampling cap.

Do not use VLM captions as unquestioned ground truth. Verify claims against timestamps, OCR/ASR, pose, shot and audio evidence; mark model-generated labels as pseudo-labels until reviewed.

### 4.4 Data and feature storage

- Existing SQLite remains the discovery/job ledger.
- Per-video component outputs remain versioned JSON/JSONL during the pilot.
- Introduce Parquet only after schema stabilization and volume justifies it.
- Store dense embeddings in Safetensors/Parquet-compatible arrays or a vector store only when retrieval/contrastive experiments need them; do not deploy Lance/another database on day one.
- Keep media, raw transcripts, private metadata, session files, rights evidence and credentials outside Git. Follow platform-specific retention and deletion requirements.

## 5. Canonical timeline and evidence contract

Every event is an interval or point on the media timeline:
- `start_s`, `end_s`, optional source PTS/time-base;
- modality and event type;
- payload (text, class, vector reference, measurement);
- confidence and quality flags;
- extractor name/version/config fingerprint;
- evidence reference (frame/audio window/tracklet);
- missingness/status enum;
- rights/provenance lineage.

Use half-open intervals `[start_s, end_s)`. Clip all timestamps to the validated duration. Do not round timestamps during extraction; round only for display.

Semantic statuses:
- `PRESENT`
- `ABSENT_IN_MEDIA`
- `NOT_APPLICABLE`
- `UNAVAILABLE_FROM_SOURCE`
- `PERMISSION_DENIED`
- `EXTRACTION_FAILED`
- `BELOW_CONFIDENCE_THRESHOLD`
- `NOT_YET_PROCESSED`

## 6. Feature extraction scope

### P0 — pilot release (must complete first)

1. Media integrity: duration, dimensions, FPS, VFR, audio presence, codec, PTS, decode errors.
2. ASR: transcript segments, timestamps, segment-level language probabilities, confidence/status, VAD and hallucination checks.
3. OCR: text, script/language, normalized bounding box, timestamp/tracklet, confidence.
4. Audio: speech/music/silence ratios, loudness/RMS curve, onset/spectral features, beat/tempo candidates.
5. Visual: adaptive frame manifest, shot boundaries, shot-duration distribution, cut density, motion magnitude and scene-change candidates.
6. Opening hook: timestamped verbal/visual/text/audio candidates in 0–3 seconds; no forced subjective hook label without evidence.
7. Metadata: source-native engagement observations with metric type, observation timestamp, video age and source.
8. Provenance: media rights, processing permission, extractor versions, source and missingness.

### P1 — after P0 passes

- Anonymous person tracks and 2D pose trajectories.
- General action intervals and coarse activity taxonomy.
- Object tracks and person-object interaction candidates.
- Sound-event classifier and music embeddings.
- Text-to-speech relation (reinforcement/complement/contradiction).
- Editing taxonomy: jump cuts, speed changes, overlays, transitions, split-screen, loop, reveal and CTA.
- Narrative structure as timestamped spans, including non-narrative performance/music-only cases.

### P2 — research extensions

- Fine-grained dance style/choreography labels.
- Speaker diarization and active-speaker matching using video-local anonymous IDs.
- Source separation, high-capacity temporal encoders, open-vocabulary HOI.
- Dense joint embeddings, graph neural network ablation, native omni-modal model comparisons.
- Model-hidden-state regression and cloud VLM cascade optimization.

## 7. Feature schema and quality requirements

See [FEATURE_EXTRACTION_SPEC.md](FEATURE_EXTRACTION_SPEC.md) for the canonical groups and JSON example.

Core schema rules:
- One video can have multiple metadata observations and extractor versions.
- Raw metrics are immutable snapshots with source and `observed_at`.
- Keep YouTube views, Instagram views and Instagram plays distinct.
- Preserve native scripts and raw transcript; normalized text is a separate field.
- Word-level timestamps are optional; segment-level is minimum.
- Action labels require time intervals and confidence.
- A person ID is video-local and non-biometric.
- Clothing records describe visible garments/colors only; never infer protected or sensitive attributes.
- Store embedding reference and dimension/model/version; do not inline huge vectors in JSON.
- Confidence values are not assumed comparable across models; calibrate per task.

## 8. Model and training strategy

### 8.1 Baselines before neural training

- Transcript-only, OCR-only, audio-only, visual-only, metadata-only and combined deterministic baselines.
- CatBoost/LightGBM for structured task labels and engagement prediction.
- Frozen visual/audio embeddings only when licensing and compute are acceptable.
- A single compact VLM candidate for grounded video description comparison; no multi-model leaderboard in the production path.

### 8.2 ShortsLM temporal fusion model

After P0 feature data and gold labels exist, train a compact model over 1–2 second windows:
- modality-specific input projections;
- explicit presence masks and confidence channels;
- temporal Transformer/TCN with PTS-aware positional encoding;
- confidence-gated cross-modal fusion;
- task heads for event/action labels, hook/edit spans, quality flags and grounded summary support.

A 5M–30M parameter target is a starting design range, not a fixed requirement. Train from scratch only this small task-specific fusion head if data permits; do not pretrain a foundation VLM from scratch.

### 8.3 Engagement model (separate)

- First model: CatBoost regression/ranking baseline.
- Use platform/metric-specific targets and creator/category/duration/age cohorts.
- Prefer creator-relative uplift or within-cohort rank only when sufficient valid history exists.
- Account for right-censoring and observation age; use survival analysis only after enough time-series snapshots.
- Keep prediction-time features free of future observations and post-publication leakage.
- Calibrate and report uncertainty only on a separate calibration set.
- Use SHAP for model-reliance explanations, not causal claims.

### 8.4 Fine-tuning a pretrained VLM

Only after frozen baseline and gold-set gates:
- compare one small open-weight model with documented license/runtime support;
- inspect exact model card and supported video/frame path;
- run LoRA/adapter SFT on a rented GPU, not the laptop;
- use a cloud VLM teacher only for selected clips and reviewed pseudo-labels;
- do not adopt GRPO/RLHF until there is a stable, auditable reward and adequate human preference data;
- keep training checkpoints, dataset manifests and evaluation split hashes versioned.

Do not commit to Qwen3-VL-2B, Qwen3.5-2B/4B, VideoLLaMA, Qwen3-Omni or Gemini as final model without a controlled bake-off. A benchmark candidate is not a project decision.

## 9. Performance modelling: target definitions

Never use raw total views alone as a universal “viral” label. For each observation store:
- platform-native metric name/value and source;
- published time and observed time;
- observation age;
- duration, category, language, creator-size context if lawfully available;
- metric availability and permission scope.

Targets to compare after sufficient data:
- within-creator percentile/uplift;
- within-platform/category/duration/age cohort percentile;
- engagement rates only where denominator is valid and available;
- time-to-threshold/survival outcomes where repeated snapshots exist.

Public view/play counts do not expose impressions, exposure allocation or retention. Creator-authorized analytics may be needed for richer watch-time/skip labels. Cross-platform metrics must not be merged without a defensible mapping. Observational findings are correlations, not causal effects.

## 10. Dataset, annotation and split plan

1. Start with 10–30 manually inspected, rights-cleared videos to validate pipeline contracts.
2. Expand to 100–300 representative assets for throughput and quality benchmarking.
3. Build a 1,500–3,000-video human-reviewed gold benchmark only if lawful supply and budget permit; it is a research target, not an immediate requirement.
4. Include low-performing and ordinary controls, not only high-view items.
5. Stratify by platform, language/script, code-switching, topic, duration, speech/no-speech, creator scale, editing style and observation age. Report achieved coverage, not promised quotas.
6. Use human annotation instructions, adjudication, per-label agreement and timestamp tolerance.
7. Separate draft machine labels from corrected labels; no pseudo-label enters gold truth.
8. Group creators, exact/perceptual duplicates, reposts, templates and trending audio before splitting.
9. Use creator-disjoint and forward-time holdouts; report cross-platform and cross-language transfer separately.
10. Keep the final gold holdout locked until model selection.

## 11. Research hypotheses and ablations

Required controlled experiments:
- P0 modality ablation: ASR, OCR, audio, visual, editing, metadata, combined.
- Speech-free subgroup vs speech-bearing subgroup.
- Uniform vs adaptive frame sampling.
- Open 0–3 seconds vs whole-video features.
- Beat-to-cut and pose-to-beat features vs no synchronization features.
- General action model vs pose primitives + temporal features.
- Confidence gating vs naïve concatenation.
- CatBoost vs compact temporal fusion vs ensemble.
- Creator-random vs creator-disjoint vs forward-time split inflation.
- Native metric vs creator-normalized target; report cohort definitions.
- Optional VLM escalation: quality lift per dollar and latency.
- Transcript evaluation across language pairs, script variants and music-heavy clips.

## 12. Hardware and operational policy

### Local ASUS TUF / RTX 3050 4 GB
Use for development, discovery, FFmpeg, CPU preprocessing, current ASR/OCR in sequential stages, small pose/model smoke tests and quantized inference experiments. Keep a CPU fallback. Measure peak VRAM; do not assume 3.5 GB usable is constant. Do not train 2B/4B multimodal models locally.

### Cloud
Use one rented GPU provider only when the experiment needs it. Start with a 24 GB-class GPU for small adapter training if the exact recipe fits; larger teacher models require more memory. Use persistent storage, checkpointing, bounded spend, idle shutdown and provider-neutral scripts. Prices are dynamic; recheck before each run.

### Notebooks
Colab/Kaggle are for short demos and experiments, not production job orchestration. Persist outputs externally and never rely on ephemeral disk.

### Scale gates
Pilot 10 → 30 → 100 → 300 videos. Then 1K → 2K → 5K → 20K → 50K → 100K only after quality, rights, unique yield, storage and unit cost are measured. The 10M+ URL aspiration is not a guaranteed lawful or technically reachable training corpus.

## 13. Minimal human setup policy

**Required for baseline:** existing local Python environment, FFmpeg/ffprobe and existing discovery/session workflow. No new developer token.

**Optional integrations, never both mandatory:**
- Gemini API key: selected multimodal reasoning/caption fallback.
- Sarvam API key: selected Indic ASR fallback if measured need exists.

No default requirement for Hugging Face account/token, pyannote gated access, ElevenLabs, NVIDIA NGC, separate music API, multiple OCR services or multiple cloud GPU accounts. If a chosen checkpoint requires gated access, prefer a public alternative unless its measured benefit justifies a documented exception.

## 14. Phases and exit gates

| Phase | Work | Exit gate |
|---|---|---|
| 0 | Audit current code, dependencies, licenses, rights and output contracts | Written implementation map; no duplicate component |
| 1 | P0 timeline/media manifest and deterministic telemetry | 10-video smoke test, schema-valid outputs, timestamps correct |
| 2 | ASR/OCR/audio/shot quality benchmark | 100–300 sample, language/script/task metrics, resource profile |
| 3 | P1 pose/action/object/editing modules | Each module adds measurable held-out value and passes license review |
| 4 | Dataset QA, annotations, dedup and splits | Rights-cleared reviewed gold set and locked holdout |
| 5 | Frozen model bake-off and baselines | Baseline report and selected checkpoint with license/runtime record |
| 6 | Train temporal fusion and engagement model separately | Held-out gains over baseline, subgroup metrics and calibration |
| 7 | Optional VLM adapter/cascade and explanation layer | Measurable quality lift, evidence audit, spend cap |
| 8 | Quantized deployment and scale | Quality/resource parity, reproducible cost and operations |

Do not skip gates because a model appears impressive in a demo.

## 15. Success criteria

A useful ShortsLM release must:
- return grounded timestamped events and transcripts, not only a prose summary;
- handle silent/music-only clips without hallucinated speech;
- preserve code-switching and native scripts;
- identify general actions with measurable class-wise accuracy and abstain when uncertain;
- describe editing/audio synchrony with reproducible measurements;
- distinguish missing data from zero;
- produce separate content-understanding and performance estimates;
- report uncertainty and evidence limitations;
- operate with minimal setup and no mandatory paid API token;
- reproduce its outputs from versioned code, model, config and provenance.

## 16. Governance and safety

Use only media and datasets with appropriate permission for the specific operation. Retrieval, analysis, temporary processing, derived artifact retention and model training are distinct permissions. Keep evidence private. Respect provider retention/deletion requirements. Do not store raw media or source-derived data in Git. Use video-local anonymous person/speaker identifiers. Do not perform cross-video identity recognition or infer sensitive traits from appearance, voice or clothing. Avoid collecting or profiling minors.

## 17. Document map

- [Gemini report reconciliation and independent review](GEMINI_RESEARCH_RECONCILIATION.md)
- [Feature extraction specification](FEATURE_EXTRACTION_SPEC.md)
- [Model selection and training](MODEL_AND_TRAINING.md)
- [Architecture](ARCHITECTURE.md)
- [Dataset and labeling](DATASET_AND_LABELING.md)
- [Data and compliance](DATA_AND_COMPLIANCE.md)
- [Compute and costs](COMPUTE_AND_COSTS.md)
- [Roadmap](ROADMAP.md)

## 18. Final decision

Implement a **measured local-first P0 telemetry system**, then add only those P1 modules that pass quality, licensing and resource gates. Use one default ASR, one OCR, a small number of deterministic audio/video measurements and a unified timestamped evidence schema. Use at most one optional VLM API and one optional Indic ASR API, neither mandatory. Train a compact temporal fusion head and a separate CatBoost engagement estimator only after a lawful, reviewed and leakage-safe dataset exists. This is the master plan to follow; changes require an ADR and evidence.
