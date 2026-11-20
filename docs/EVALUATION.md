# Evaluation Protocol

## Principles

- Every comparison uses identical splits and input budgets.
- Separate external benchmark scores from our own task-specific tests.
- Report by language, topic, creator size, duration, platform, speech/no-speech and edit class.
- Use confidence intervals where possible; avoid one headline accuracy score.
- Do not tune thresholds on the locked test set.

## Benchmark matrix

| Task | Metric | Ground truth |
|---|---|---|
| Shot boundary detection | Precision/recall/F1; boundary tolerance | Human-reviewed cut timestamps |
| Editing event detection | Per-class precision/recall/F1 | Annotated events and hard negatives |
| Temporal localization | temporal IoU / start-end error | Annotated intervals |
| OCR | CER/WER and span localization | Human-checked timed text |
| ASR | WER by language; language-ID accuracy | Human transcripts |
| Audio/beat sync | beat/onset error and cut-to-beat distance | Human/algorithm-verified audio timeline |
| Video grounding | Evidence-reference precision and factuality | Human-reviewed evidence labels |
| Structured output | JSON parse rate and schema validity | Validator |
| Explanation usefulness | Rubric ratings and inter-rater agreement | Blind human reviewers |
| Performance ranking | Spearman/Kendall, pairwise accuracy, calibration | Authorized longitudinal outcomes |
| Recommendations | Usefulness, feasibility and trade-off quality | Creator/reviewer feedback |

## Temporal hallucination audit

For every predicted event:
1. timestamp must be within media duration;
2. cited frame/telemetry ID must exist;
3. measured counts/text/audio values must match referenced extractor output within tolerance;
4. uncertain technique labels must remain candidates;
5. output must not claim measured beat sync if beat-detector confidence is inadequate.

A deterministic verifier catches structural contradiction, not all semantic hallucination. Human review remains necessary.

## Ablations

Run the full package, then remove one input lane at a time: video frames; ASR; OCR; audio features; motion/edit telemetry; metadata; retrieval examples. This reveals which modalities contribute to which task.

## Leakage checks

- Creator/account group split.
- Time-forward holdout.
- Perceptual video/image duplicate checks and audio fingerprints where permitted.
- Cross-platform repost grouping.
- Same creator must not appear across train/test if claiming creator generalization.

## External benchmarks

VEBench is a useful external video-editing understanding benchmark (arXiv:2605.03276). It does not replace a project-specific short-form editing set. Video-MME/MVBench/OCRBench are general multimodal regression checks only when candidate model/input conventions support comparable evaluation.

## Acceptance gates

Set thresholds after measuring annotator agreement and base-model performance. A fine-tuned model is accepted only if it improves a predeclared task by a meaningful margin, avoids material multilingual/general regressions, meets grounding/calibration requirements and fits documented runtime constraints.
