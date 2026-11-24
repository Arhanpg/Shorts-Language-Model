# ShortsLM — Gemini Research Reconciliation and Independent Technical Review

**Date:** 24 November 2026  
**Input:** *ShortsLM Multimodal Video Research Foundation* (Gemini Deep Research, 94 pages)  
**Repository context:** current `main` documentation and source-search results were inspected during this review.  
**Status:** research synthesis; not a claim that every cited result or model-card detail has been independently reproduced.

## 1. Executive decision

Gemini's central thesis is sound: ShortsLM must represent synchronized visual, speech, music, sound-event, text-overlay, motion, editing and platform-observation evidence. Transcript + OCR alone is insufficient. A pretrained foundation model should be adapted only after deterministic telemetry, quality checks and baseline evaluation; training a multimodal foundation model from scratch is outside this project's hardware and budget.

**Final direction:** build a local-first, modular telemetry pipeline that produces a versioned temporal evidence record; use a single optional multimodal reasoning API for difficult clips; train a compact temporal fusion model and a separate engagement estimator only after enough rights-cleared, human-reviewed examples exist.

Do not implement Gemini's entire 12-specialist stack in one release. Its model count, gated downloads, dependencies, licensing checks, GPU memory, and operational complexity conflict with the owner's explicit requirement for minimal setup.

## 2. What is accepted from Gemini

| Gemini proposal | Decision | Reason / implementation |
|---|---|---|
| Canonical shared timeline using container presentation timestamps (PTS) | **Accept** | Essential for variable-frame-rate media and aligning ASR, OCR, shots, beats and actions. Store seconds and source PTS/time-base where available. |
| Confidence-aware multimodal fusion with explicit missingness | **Accept** | Missing speech is not a failed transcript; failed extraction is not absence. Store status, confidence, model/version and evidence references. |
| Separate content understanding from performance prediction | **Accept** | Different labels, datasets, confounders and evaluation protocols. Never train a single opaque “viral score” as a substitute. |
| Speech-free content path | **Accept** | Music, dance, comedy, sports and visual edits remain informative without dialogue. |
| Code-switching-aware transcript evaluation | **Accept** | Evaluate language spans and switch regions, not only aggregate WER. Preserve native script and Romanized forms where observed. |
| Shot boundaries, beat/cut alignment, pose/motion, HOI and temporal editing signals | **Accept in stages** | Strong measurable features; prioritize low-cost deterministic features before heavy learned models. |
| Creator- and age-normalized engagement | **Accept with safeguards** | Preserve raw metric snapshots; normalize only within comparable platform/metric/cohort/time windows and only where policy allows. |
| Creator/time/audio/template-disjoint splits | **Accept** | Necessary to reduce creator memorization, repost leakage and trending-audio leakage. |
| Human-reviewed gold set, annotation agreement and evidence audit | **Accept** | Pseudo-labels are not ground truth. Report agreement by label family. |
| Pretrained encoders, frozen baselines, then adapters/fusion training | **Accept** | More feasible and scientifically testable than pretraining from scratch. |
| Conformal intervals and calibration | **Accept later** | Only after a valid independent calibration set and drift monitoring exist. |
| Explicit legal, privacy and source provenance gates | **Accept** | Public visibility or extractor success is not permission to retrieve, retain or train. |

## 3. Corrections, qualifications and items not adopted

### 3.1 Throughput and hardware estimates are hypotheses, not capacity commitments

Gemini estimates approximately 8.8 seconds of GPU compute / 11.44 seconds wall time for a 30-second clip across a large specialist stack and roughly 315 clips/hour on the 4 GB RTX 3050. This must **not** be used as a planning guarantee. The estimate depends on model variants, image sizes, precision, frame rates, batching, decoding, CPU/GPU transfer, model load/unload, Windows WDDM use, thermal limits, and whether each model actually fits simultaneously or sequentially. The report's own component list includes several substantial models. Benchmark each stage on a fixed, representative 30–300 clip sample and record peak allocated/reserved VRAM, RAM, wall time, retries and output quality.

The reported 1M-video cloud cost ranges are also scenarios, not vendor quotes or measured project costs. They omit or may undercount rights acquisition, human review, storage/egress, retries, orchestration, provider minimums, taxes and API token variation. The repository's existing [compute and cost note](COMPUTE_AND_COSTS.md) is retained: measure cost per accepted example, not cost per discovered URL.

### 3.2 ASR: do not install a routing zoo on day one

Gemini's candidate list includes faster-whisper, Canary/Parakeet, IndicConformer, SraVaani, Sarvam Saaras, ElevenLabs, WhisperX and NeMo. This is useful research inventory, not a practical install list.

**Initial default:** the repository's existing faster-whisper integration, using one selected Whisper checkpoint and a single documented compute mode. Benchmark `large-v3-turbo` INT8 against the currently working configured model on a curated multilingual short-form sample; choose one default from measured quality/runtime/VRAM. Do not install a second ASR stack merely because it exists.

**One optional exception:** if Hinglish/Indic code-switching quality is a demonstrated blocker, evaluate one managed Indic-capable ASR service (Sarvam Saaras) behind an opt-in adapter. It is not required for baseline runs. Do not add gated Hugging Face model access, multiple billing accounts or per-language manual model selection in the default path.

Word timestamps must be validated. Use an aligner only if timestamp quality is inadequate and the selected aligner can run without another gated account. Speaker diarization is deferred; initially store anonymous speaker turns only when the selected ASR backend returns reliable segments. Do not require pyannote/Hugging Face login for the standard install.

### 3.3 Music and sound: separate cheap signal features from expensive semantics

Accept audio analysis, but start with one audio pass and inexpensive features: speech probability/VAD, RMS/loudness curve, spectral flux/onsets, tempo/beat candidates, music/speech occupancy, silence, clipping and duration-aligned audio embeddings only if justified. A lightweight sound-event model may be added after a benchmark. BEATs + MERT + Beat This! + CLAP + HTDemucs is not the first-run dependency set. Source separation is conditional, expensive and can introduce artifacts; invoke only when speech/music overlap materially harms ASR or the research task.

### 3.4 Visual action and dance labels need careful scope

Person detection is not action understanding. Pose trajectories, object interaction, temporal evidence and context are needed to distinguish sitting, speaking, singing, dancing, sports and specific dance styles. Start with general observable action intervals and pose/motion primitives; treat fine-grained labels (belly dance, breakdance, twerking, regional/classical dance forms) as multi-label hypotheses with confidence and abstention. Build a human-reviewed taxonomy and evaluate class-wise precision/recall before publishing these labels. Do not infer identity, protected traits, socioeconomic status or internal mental state from appearance.

### 3.5 Model choice: no commitment to three large architecture candidates yet

Gemini proposes A (specialist fusion), B (specialist-to-VLM cascade) and C (omni-modal MLLM hidden-state regression), then projects B1 as the likely winner. That is a useful experimental framing, but a projected winner and cost-per-1K estimate are not results from this repository.

**Chosen engineering path:** implement the low-complexity specialist telemetry + compact trainable temporal fusion (A-lite) first. Add one optional cloud VLM escalation for ambiguous/high-value clips (B-lite) only after baseline comparisons show a measurable benefit. Defer native omni-modal 30B+ models and hidden-state regression requiring model internals/cloud GPUs until a later research phase. Do not hard-code B1 as winner.

### 3.6 Public engagement data does not expose the complete outcome

The report correctly flags platform asymmetry. Public counts are snapshots, not retention curves or impressions. Creator-owned analytics may expose richer metrics only through authorization and platform-specific permissions. The current project intentionally uses a non-official-API discovery toolchain; do not silently switch it to YouTube Data API or Instagram Graph API. Keep views, plays, likes, comments, shares, saves, average watch time and skip-rate as distinct metric definitions with source, timestamp, permission and availability status. A missing value is not zero.

### 3.7 Licensing and rights must be checked at the exact checkpoint/data release

A paper's license, code license, pretrained weight license, dataset license and commercial-use rights can differ. Model cards and terms change. The report's broad “MIT/Apache” labels are leads, not blanket clearance. Before adding a dependency, record exact repository/checkpoint, version, code/weight license, attribution, restrictions, commercial eligibility, gated access, download requirements and maintenance status. The current rights manifest is an explicit local assertion/evidence pointer, not legal verification; keep the default-deny gate.

## 4. Practical minimal-dependency decision

The default user workflow should require **zero new developer tokens** for local telemetry. Existing platform sign-in/session workflows remain only where the current discovery implementation needs them.

| Capability | Initial choice | Extra account/token? | Defer / trigger |
|---|---|---:|---|
| Decode, timestamps, frames, audio extraction | Existing FFmpeg/ffprobe | No | Keep; decode once and reuse PTS. |
| ASR + language detection | Existing faster-whisper adapter; select one checkpoint | No | Optional Sarvam API only after measured Indic gap. |
| Word alignment | Use timestamps from ASR; validate | No | Add one local aligner only if benchmark fails. |
| OCR | Existing PaddleOCR adapter; test Devanagari, Latin and mixed scripts | No | Add another OCR engine only for documented failure classes. |
| Shot/scene changes | OpenCV baseline + existing scene/shot code | No | TransNetV2 only if measurable recall improvement offsets dependency. |
| Music/sound | Librosa-style signal features + VAD | No | One lightweight event model after validation; no default source separation. |
| Pose/action | One selected open-source pose model, sequentially loaded | No | General actions first; fine-grained dance classifier only with gold labels. |
| Objects/clothing/scenes | Existing detector if license/quality pass; otherwise sampled-frame VLM | No | Do not add YOLO/RT-DETR/GroundingDINO/SAM all at once. |
| Multimodal reasoning/captioning | **One optional Gemini API key** for selected clips | 1 optional key | Not required for local extraction; enforce cost cap and no automatic upload of unapproved media. |
| Indic ASR escalation | **One optional Sarvam API key** | 1 optional key | Mutually optional; do not require both Gemini and Sarvam. |
| Speaker diarization | Defer | No | Add only when speaker-turn task justifies gated model complexity. |
| Model training | PyTorch + selected open-source training recipe on rented GPU | Cloud account/billing only when training begins | No training on RTX 3050 4 GB. |
| Data/feature store | Existing SQLite + JSONL; add Parquet when scale warrants | No | Embedding store only when retrieval experiments require it. |

**Account policy:** do not create ten vendor accounts. The initial pipeline works locally without paid API tokens. If the VLM fallback is activated, use one Gemini API key. If Indic ASR is separately proven necessary, choose Sarvam as the one optional ASR service. No routine Hugging Face token should be required; prefer publicly downloadable weights. If a model is gated, it is excluded from the default path.

## 5. Feature extraction priorities

**P0 — required foundation**
- Media integrity: duration, dimensions, frame rate, VFR flag, audio presence, PTS/time-base, decode status.
- Speech: speech presence/occupancy, transcript segments, timestamps, language probabilities at segment level, confidence/quality flags, non-speech hallucination checks.
- OCR: timestamped text tracklets, script, normalized bounding boxes, OCR confidence, language/script, opening-hook and CTA candidates.
- Audio: speech/music/silence occupancy, loudness/RMS, onset/energy curves, tempo/beat candidates, coarse sound-event flags.
- Visual/temporal: adaptive frames, shot boundaries, shot durations, cut density, opening 0–3 second measurements, scene changes, simple motion/optical-flow statistics.
- Metadata: immutable platform-native metric snapshots and observation age; never combine incompatible metric types.
- Provenance: source, permission scopes, extractor/model versions, timestamp, confidence and semantic missingness.

**P1 — after P0 quality gates**
- Anonymous person tracks and 2D pose sequences.
- General action intervals (walking, running, sitting, standing, jumping, dancing, talking, singing, cooking, sports, etc.).
- Object detections and person-object interaction candidates.
- Music embedding/genre/mood and richer sound events.
- Text-to-speech semantic relation (reinforcement, complement, contradiction).
- Editing taxonomy: jump cuts, speed changes, transitions, overlays, split-screen, loop/reveal/CTA candidates.

**P2 — research extensions**
- Fine-grained dance styles and choreography similarity.
- Active speaker detection and diarization-to-visible-person association using video-local anonymous IDs.
- Source separation, high-capacity temporal encoders, open-vocabulary HOI.
- Dense multimodal embeddings, graph ablations and VLM hidden-state regression.

## 6. Modeling plan and mathematical choices

1. **Deterministic baseline:** handcrafted audio/visual/editing/metadata features + CatBoost/LightGBM; strong, interpretable baseline for tabular engagement and taxonomy tasks.
2. **Temporal encoder:** small Transformer or temporal convolution over 1–2 second windows with PTS positional encoding; explicit modality masks and confidence features. Keep the first custom model modest (roughly 5M–30M parameters is a target range, not a required architecture).
3. **Confidence-gated fusion:** modality features are gated by availability and calibrated extraction confidence. Do not treat confidence values from unrelated models as calibrated probabilities until tested.
4. **Self-supervised alignment:** contrastive audio/video/text segment alignment (InfoNCE) is an experiment after false-negative controls for reused music/templates. Not a day-one training requirement.
5. **Multi-task supervision:** action/event labels, hook/edit labels, transcript/OCR quality tasks, temporal localization and grounded summaries can share a representation only when label definitions and missingness are explicit.
6. **Performance estimator:** separate model using only pre-publication content features and allowed pre-publication metadata; separate target heads per platform/metric/cohort where required. CatBoost first; ranking/survival models only if data supports them.
7. **Uncertainty:** calibrate on a held-out set; add conformal intervals only after coverage is empirically tested under time drift.
8. **Explanation:** produce evidence-linked descriptions with timestamps and citations to extracted events. SHAP indicates model reliance, not causality. Never claim “this caused virality” from observational correlation.

## 7. Evaluation requirements

- ASR: normalized WER/CER, language-span accuracy, code-switch boundary F1, entity preservation, hallucination rate on music/silence, timestamp error.
- OCR: script-wise CER, text-track recall, timestamp/box quality and text-function classification.
- Audio: event mAP/F1 where labels exist; beat/onset timing error; music/speech occupancy error.
- Action/pose: per-class precision/recall/F1, temporal IoU, keypoint confidence/visibility; separate general action from fine-grained dance style.
- Temporal/editing: cut F1 within tolerance, shot-duration error, hook/event localization mAP/IoU, beat-cut synchrony error.
- Multimodal: grounded QA accuracy, evidence precision, hallucination rate, modality ablations and speech-free subgroup performance.
- Engagement: MAE/RMSE/Huber for regression, Spearman/Kendall/NDCG for ranking, calibration/interval coverage, performance by platform/language/creator-size/duration/age cohort.
- Splits: creator-group disjoint, forward-time, perceptual duplicate/repost group disjoint, trending-audio/template disjoint where feasible. Report random split only as a diagnostic, never as the sole result.

## 8. Evidence ledger: confidence labels

Use these labels in the final research and implementation documents:
- **Established method:** published method with primary paper or official documentation; still validate applicability to ShortsLM.
- **Promising external result:** reported by a paper/benchmark but not reproduced on this corpus.
- **Vendor claim:** performance/feature statement from vendor material; independently benchmark before reliance.
- **Project hypothesis:** proposed feature or architecture needing an experiment.
- **Unverified estimate:** runtime, cost, coverage or quality number without a reproduced workload.
- **Decision:** selected project default, with reason and exit gate.

## 9. Primary references for the design

- Whisper: https://proceedings.mlr.press/v202/radford23a.html
- WhisperX: https://arxiv.org/abs/2303.00747
- IndicVoices: https://arxiv.org/abs/2403.01926
- SraVaani 1.0 (preprint): https://arxiv.org/abs/2608.08235
- Hindi-English code-switch ASR: https://arxiv.org/abs/1906.09426
- Code-switch LID with concatenated tokenizer: https://arxiv.org/abs/2306.08753
- BEATs: https://arxiv.org/abs/2212.09058
- MERT: https://arxiv.org/abs/2306.00107
- Beat This!: https://arxiv.org/abs/2407.21658
- HTDemucs: https://arxiv.org/abs/2211.08553
- Synchformer: https://arxiv.org/abs/2401.16423
- RTMPose: https://arxiv.org/abs/2303.07399
- FineGym: https://arxiv.org/abs/2004.06704
- FineDance: https://arxiv.org/abs/2212.03741
- TransNetV2: https://arxiv.org/abs/2008.04838
- VEU-Bench: https://arxiv.org/abs/2504.17828
- CameraBench: https://arxiv.org/abs/2504.15376
- SnapUGC: https://arxiv.org/abs/2410.00289
- LMM-EVQA: https://arxiv.org/abs/2508.02516
- KuaiRand: https://arxiv.org/abs/2208.08696
- D2Q duration bias: https://arxiv.org/abs/2206.06003
- InfoNCE: https://arxiv.org/abs/1807.03748
- CatBoost: https://arxiv.org/abs/1706.09516
- SHAP: https://arxiv.org/abs/1705.07874
- Conformal prediction: https://arxiv.org/abs/2107.07511
- Qwen3-VL report: https://arxiv.org/abs/2511.21631
- Qwen3-Omni report: https://arxiv.org/abs/2509.17765
- YouTube API quota/policy (only if reconsidered): https://developers.google.com/youtube/v3/determine_quota_cost
- Instagram insights (authorized account scope only): https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/insights/

## 10. Final research conclusion

The Gemini report is a strong research map and a useful list of hypotheses. It is not a validated implementation specification. ShortsLM should adopt its temporal, multimodal, confidence-aware and evaluation principles, but reject the temptation to install every named model. The project should move from a working, measured P0 pipeline to P1 only after an auditable pilot; train only after rights-cleared data, annotations, splits and frozen baselines exist. This is the shortest path that preserves research depth without creating an unmaintainable setup burden.
