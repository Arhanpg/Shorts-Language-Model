# Proposal 3 — Creator-Normalized Dataset and 20K Learning Ladder

## Original direction

Prioritize a small number of well-chosen training examples over a huge raw-video scrape. Use creator-matched positives and controls; first prove that the pipeline and baseline can identify meaningful differences, then scale toward 20,000 examples.

## Dataset ladder proposed

- 300 videos: initial pilot.
- 5,000 videos: first structured training/evaluation tier.
- 20,000 videos: expanded SFT and model-comparison tier.
- 100,000 or more: only when the measured gain justifies additional rights, processing and annotation cost.

The numbers are proposed milestones, not claims that 20K is statistically optimal.

## Sampling and bias

A dataset that contains only million-view videos cannot learn which properties distinguish a successful video from an ordinary upload. Suggested controls:

- same-creator uploads;
- comparable topic, language, duration and publication window;
- channel audience-size/baseline strata;
- high-, medium- and low-performance buckets;
- both speech-heavy and dialogue-free edits.

The proposal highlights creator-relative performance instead of raw views:

`creator_outlier = log(1 + video_outcome) - robust_creator_baseline`

This can reduce one source of creator-size confounding, but it does not remove distribution, promotion, audience, geography or topic confounders. The formula and baseline window must be validated.

## Model route

- SmolVLM2-500M as a small, low-resource smoke-test candidate.
- Qwen3-VL-2B as the main compact VLM candidate.
- Qwen3-VL-4B or a newer family as a stretch candidate.
- A separate gradient-boosted predictor on metadata and extracted features.
- The VLM explains measured evidence; it should not be the only numerical popularity estimator.

The model input is a compact package: 8–16 hook-aware frames, transcript, OCR, audio tags/features, measured edit statistics and permitted metadata.

## Evaluation proposed

- Pairwise comparison within same-creator matched pairs.
- Faithfulness checks against measured cut/OCR/beat telemetry.
- Ablations removing audio, text or hook frames.
- Evaluation on future videos and unseen creators.
- Per-language and no-speech reporting.

## What the combined plan accepts

1. 300-video pilot before large training runs.
2. Small VLM baseline for smoke testing.
3. Creator-relative outcome as an experimental target.
4. Separate performance predictor before fine-tuning the VLM.
5. Matched controls and creator/time-disjoint evaluation.
6. Ablation studies to identify which modalities add signal.

## What changes

- 20K is not guaranteed to be enough or optimal.
- The predictor does not prove what causes virality; observational models identify associations and predictive signals, not causal effects.
- Raw view counts must be interpreted with platform-specific metric definitions and observation ages.
- MicroLens, SMPD-Video or any suggested research dataset must be checked for item-level rights, privacy terms and commercial-use constraints before training.

## Final disposition

**Accepted as the experimental scaling strategy.** Run a diagnostic 300-video pilot, then grow by evidence-led gates. Prioritize quality, diversity, creator-held-out evaluation and cost per approved training example.
