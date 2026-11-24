# Gemini Deep Research Report — Structured Digest

**Source document:** *Shorts Language Model (ShortsLM): Comprehensive Scientific Foundation, Multimodal Architecture, and Research Blueprint*  
**Length:** 94 pages  
**Received:** 24 November 2026  
**Purpose:** preserve the structure and main technical proposals of the supplied report in the repository. This digest summarizes the source; it is not a verbatim reproduction of the uploaded document. See [the independent reconciliation](GEMINI_RESEARCH_RECONCILIATION.md) for accept/reject decisions.

## 1. Executive summary of the source

The report argues that transcript-plus-OCR systems are inadequate for short-form video because many clips are music-led, speech-free, visually driven or paced around rapid cuts and movement. It rejects training a competitive multimodal foundation model from scratch and proposes pretrained specialist encoders plus temporal fusion, optional VLM reasoning and separate engagement prediction.

It proposes three architecture families:
- **A — Modular specialists + temporal fusion:** deterministic/specialist extraction, synchronized timeline and trainable fusion.
- **B — Cascaded specialist-to-VLM hybrid:** specialists run on every clip; a larger VLM is invoked selectively for difficult/complex cases.
- **C — Native omni-modal MLLM + hidden-state regression:** one multimodal model supplies hidden representations, with regression heads for downstream outcomes.

The report suggests a cascade may be the best future trade-off, but this is a hypothesis to test, not a measured ShortsLM result.

## 2. Problem formulation and system boundaries

The report models a video observation as visual frames with presentation timestamps, an audio waveform, platform metadata and an observation age. It emphasizes:
- sub-second pacing and opening attention signals;
- non-redundant or contradictory modalities;
- intra-utterance language switching and noisy speech;
- duration, creator and lifecycle confounding;
- different platform data availability.

It defines two coupled objectives: a confidence-weighted synchronized multimodal representation and a separate prediction/explanation layer. It also proposes three governance rules: media rights and retention compliance, privacy-preserving video-local anonymous IDs, and uncertainty/missingness transparency.

## 3. Research landscape

The source surveys 24 research subfields and reports contributions from global universities and 30+ AI research organizations. It includes computer vision, speech, audio/music information retrieval, NLP, multimodal learning, video editing, action recognition, recommender systems, causal inference and calibration.

The report's institution and ranking tables are background context, not a project dependency. The bibliography and institution affiliations should be checked against original papers before being reused in external publications.

## 4. Multimodal video understanding

The report highlights failure modes in video-language models:
- static-frame bias and weak temporal reasoning;
- visual dominance that can mis-ground audio events;
- sampling/token-budget trade-offs;
- lack of explicit evidence synchronization.

Proposed design patterns:
- dual semantic and motion visual encoders;
- interleaved video/audio/text representations;
- slow/fast frame streams;
- joint audio-visual embeddings;
- confidence-gated temporal fusion.

The project-level invariant is a common timeline anchored to media PTS, not nominal frame indices.

## 5. Speech, language identification and code-switching

The report reviews:
- Whisper/faster-whisper for broad multilingual ASR;
- Canary/Parakeet as a fast European-language route;
- IndicConformer and SraVaani for Indic speech;
- Sarvam Saaras and ElevenLabs as commercial service candidates;
- code-switch corpora and Hindi-English, Arabic-English and Spanish-English research;
- segment-level multi-label language identification and token-level script/language tags;
- language-aware normalization and code-switch-aware evaluation.

It recommends segment-level language identification rather than one language label per video. It also warns that WER can hide switch-region errors and that non-speech audio can cause ASR hallucinations.

**Project implication:** select one default ASR implementation, benchmark it on the project's languages and short-form conditions, and keep a second service/model optional only if a measured gap remains.

## 6. Speaker intelligence and diarization

The report discusses pyannote.audio diarization, overlapping speech, voice activity, active speaker detection and linking anonymous speech turns to visible person tracks. It proposes video-local speaker IDs and avoiding cross-video identity matching.

**Project implication:** diarization and audio-to-visible-person association are later-stage features. They should not introduce mandatory gated model downloads or tokens into the baseline pipeline.

## 7. Music and sound intelligence

The report covers:
- speech/music/singing/ambient classification;
- source separation (HTDemucs);
- MERT music embeddings;
- CLAP open-vocabulary audio-text matching;
- Beat This! beat/downbeat tracking;
- BEATs/PANNs/YAMNet sound-event classification;
- AudioSet, FSD50K and ESC-50 datasets;
- audio-visual synchronization and speech-free analysis.

It proposes beat-to-cut alignment, dance-motion-to-beat phase locking and sound-to-visual event correspondence. Music-only and speech-free clips should have a complete analysis path.

**Project implication:** start with inexpensive audio signal features and one VAD/ASR pass. Add learned music/event models and source separation only when an experiment justifies their installation and runtime.

## 8. OCR and on-screen text semantics

The report distinguishes spoken words, auto subtitles, manually styled/kinetic subtitles, hook/title text, meme captions, scene/product labels, watermarks, usernames and platform interface text. It proposes OCR tracklets with script, box, time and function; alignment to ASR; and text-speech relations such as reinforcement, complementarity and contradiction.

It warns that platform UI counters can become target leakage if the goal is pre-publication performance prediction.

**Project implication:** OCR should preserve raw text, script, bbox, time and confidence; function labels are hypotheses until reviewed.

## 9. Human actions, pose and dance

The report moves beyond person detection to atomic action intervals, compound activities, pose trajectories and person-object interaction. It discusses Kinetics, AVA, FineGym, FineDiving, FineParser, FineDance, AIST++, RTMPose/RTMW, ViTPose, RAFT and ActionFormer.

It proposes decoupling:
1. biomechanical primitives;
2. atomic moves;
3. full choreography sequences;
4. calibrated multi-label dance styles.

It notes that fine-grained dance labels are culturally uneven and should abstain when training coverage is inadequate.

**Project implication:** begin with general actions and objective motion/pose features. Do not claim reliable fine-grained dance-style classification without class-wise human-reviewed evaluation.

## 10. Appearance, clothing, objects and scenes

The report proposes observable clothing attributes, dominant color and wardrobe changes; object detection/tracking; person-object interaction triplets; and scene/environment classification. It mentions DeepFashion2, YOLO, RT-DETR, Grounding DINO, SAM 2 and Places365.

It explicitly prohibits inferring sensitive personal characteristics or socioeconomic status from clothing/appearance.

**Project implication:** appearance/object modules are conditional. Start only where they support a concrete analysis task, and verify checkpoint/data licenses independently.

## 11. Editing, camera and narrative intelligence

The report reviews VEU-Bench and CameraBench and proposes explicit measurements for:
- shot boundaries, transitions and jump cuts;
- shot duration, cut density and montage bursts;
- camera pan/tilt/zoom/shake and framing;
- speed changes and visual effects;
- opening hooks in the first 0–3 seconds;
- pattern interrupts, reveals, loops and CTAs;
- narrative arcs and non-narrative performance.

It suggests PELT change-point detection, temporal localization, audio/visual event synchronization and evidence-grounded narrative spans.

**Project implication:** deterministic cut, duration, motion, OCR, ASR and beat measurements should precede subjective VLM labels.

## 12. Engagement prediction and platform signals

The report discusses SnapUGC, LMM-EVQA, KuaiRand and D2Q. It warns that raw views are confounded by duration, creator size, exposure, upload age and platform distribution. It distinguishes public aggregate counts from creator-authorized retention/watch-time data.

It proposes creator-relative outcomes, cohort percentiles, time-to-breakout and ranking targets. It cautions that observational correlation cannot establish causality.

**Project implication:** preserve immutable platform-native snapshots. Build a separate performance model with creator/time splits and valid denominators. Do not conflate Instagram plays and YouTube views.

## 13. Dataset landscape

The report surveys video, action, dance, audio, music, speech and engagement datasets, including:
- Kinetics, Something-Something v2, AVA, FineGym, FineDiving, ActivityNet, Charades, UCF101 and HMDB51;
- AIST++, FineDance and DanceTrack;
- AudioSet, FSD50K, ESC-50, Clotho, WavCaps, FMA and MTG-Jamendo;
- Common Voice, FLEURS, VoxPopuli, IndicVoices, Kathbath and BhasaAnuvaad;
- HowTo100M, WebVid, MSR-VTT, VATEX, Ego4D, Video-MME, SnapUGC, KuaiRand and related engagement datasets.

The source repeatedly warns that linked media may remain copyrighted, research-only or gated. Dataset availability is not permission for commercial training.

## 14. Mathematical and algorithmic methods

The report discusses:
- symmetric multimodal InfoNCE and triplet losses;
- temporal self-attention/rotary time embeddings and temporal convolutions;
- PELT change-point detection and dynamic time warping;
- confidence-gated multimodal units and cross-modal attention;
- PCA/whitening and feature selection;
- CatBoost/XGBoost/LightGBM and LambdaMART;
- survival analysis for time-to-breakout;
- temperature scaling, calibration and conformalized quantile regression;
- graph representations for entities, actions and relations.

It proposes graph neural networks as an ablation rather than a default. The project should add each method only when its inputs, labels and evaluation design exist.

## 15. Feature schema

The source proposes a 24-group schema stored in Parquet for structured records and Safetensors/Lance for embeddings. It uses semantic missingness categories such as PRESENT, ABSENT_IN_VIDEO, UNAVAILABLE_BY_PLATFORM, EXTRACTION_FAILED and BELOW_CONFIDENCE_THRESHOLD.

Its feature groups span:
- video and creator metadata;
- engagement snapshots;
- speech/transcript and language/code-switch;
- speaker/diarization;
- music and sound events;
- audio emotion/delivery;
- OCR/on-screen text;
- person detection, action, pose and motion;
- object/HOI and clothing;
- scene/environment;
- editing/camera;
- hooks, narrative and cross-modal alignment;
- quality, provenance, embedding and uncertainty features.

**Project implication:** retain the 24-group conceptual taxonomy but implement P0/P1/P2 incrementally. JSON/JSONL is sufficient during the pilot; Parquet/embedding stores are scale-driven.

## 16. Training strategies

The report compares:
- frozen pretrained extractors;
- linear probing;
- task-specific temporal fusion;
- LoRA/QLoRA SFT;
- multimodal contrastive learning;
- multi-task learning;
- distillation from a teacher;
- larger native omni-modal models and MoE.

It recommends a staged combination: frozen specialists, compact temporal fusion, tabular performance model, optional LoRA VLM and evidence-grounded reasoning. It discourages a custom MoE before substantial labeled data exists.

## 17. Annotation and supervision

The source separates self-supervised signals, weak/platform labels and human-annotated gold labels. It recommends human-reviewed taxonomy, timestamped labels, annotation agreement, pseudo-label isolation and creator/time/audio/template-aware splits.

The project must keep machine-generated drafts distinct from human-confirmed labels and must not allow pseudo-labels into a locked gold set.

## 18. Hardware and cost model

The source estimates staged specialist extraction on the RTX 3050 and cloud processing costs for 1M videos. These numbers are **not reproduced measurements**. They depend on model variants, precision, sampling, memory, I/O, GPU SKU, provider pricing, retry rates and review overhead.

The project must benchmark 10–300 authorized clips before publishing throughput or unit-cost claims. Use the laptop for development and sequential extraction; rent a GPU for fine-tuning when required.

## 19. Proposed roadmap in the source

The Gemini report's staged roadmap is summarized as:
1. literature/repository/license/ethics review;
2. dataset and metadata design;
3. feature schema design;
4. baseline experiments;
5. feature-extraction prototype;
6. annotation and quality validation;
7. training experiments across architectures A/B/C;
8. ablations;
9. cross-platform/language/time generalization;
10. final architecture selection and scale plan.

The repository roadmap maps this into smaller practical phases and removes premature commitments to all three large architectures.

## 20. Report limitations identified during reconciliation

- Gemini reports that it could not inspect the repository; current repository docs and source were therefore audited separately.
- Some throughput and cost estimates are not independently reproduced on the project's hardware/workload.
- Some model performance/license/access claims are vendor- or model-card-dependent and must be rechecked at exact checkpoint/version.
- Public engagement APIs do not provide all desired retention signals.
- A proposed architecture winner is not a ShortsLM experimental result.
- The original report is a research synthesis; this digest is not a substitute for primary paper review.

## 21. Repository decisions

See [GEMINI_RESEARCH_RECONCILIATION.md](GEMINI_RESEARCH_RECONCILIATION.md) for the detailed decision matrix. The selected project plan is [GLOBAL_MASTER_PLAN.md](GLOBAL_MASTER_PLAN.md), with the feature contract in [FEATURE_EXTRACTION_SPEC.md](FEATURE_EXTRACTION_SPEC.md).

**Bottom line:** preserve Gemini's broad research coverage and core multimodal/temporal principles; implement a small, measurable, rights-aware local-first system rather than its entire specialist inventory in one step.
