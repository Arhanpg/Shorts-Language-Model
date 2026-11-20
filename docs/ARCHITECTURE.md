# Architecture Decision Record

**Status:** Accepted for research MVP; implementation candidates remain benchmark-gated.  
**Date:** 2026-11-20

## Decision

Use a hybrid neuro-symbolic design: deterministic video/audio telemetry provides temporal facts; a compact multimodal VLM explains and combines evidence; a separate tabular model estimates normalized performance patterns. Acquisition is rights-aware and provider-pluggable.

## Why not a single video LLM?

Sparse frame sampling can miss short events between selected frames. A general VLM can describe visible content, but should not be trusted to infer exact cut timestamps, BPM, OCR strings or speed-ramp intervals without measurements. A deterministic front-end reduces the burden on the language model and enables consistency checks.

## Component contracts

### Acquisition adapter

Input: provider query, creator upload or licensed dataset manifest.  
Output: SourceRecord plus permission capabilities.  
Must report provenance, quota, observation time and rights. It must not bypass access controls or assume API access grants media/training rights.

### Media processor

Input: authorized temporary media artifact.  
Output: normalized stream metadata, audio, frames and scene candidates.  
Must be idempotent, resource-capped, resumable where possible, and record exact tool/configuration versions.

### Telemetry extractors

Each extractor emits events, evidence references, confidence, tool name/version and config hash. Extractors may abstain. The schema distinguishes a measured signal from an inferred artistic technique.

### Annotation and review

Teacher outputs are drafts, not gold labels. Each annotation tracks source, model, prompt version, human reviewer and corrections. High-impact temporal labels require review and/or a validated detector.

### Reasoning VLM

Input: selected timestamped frames, telemetry JSON, transcript/OCR and permitted metadata. Output: schema-validated analysis with evidence references, confidence and missing evidence. It cannot silently override deterministic measurements.

### Performance predictor

Separate model, LightGBM first. It receives creator-normalized features and platform/measurement context. View count is an outcome/label field, not an input feature for blind prediction.

### Inference service

CLI first, local API/UI later. Support CPU fallback, configurable frame/token budgets, explicit resource limits and graceful partial results.

## Data flow

```mermaid
flowchart LR
 A[Permitted source] --> B[Rights gate]
 B --> C[Manifest + metadata]
 C --> D[Dedup + eligibility]
 D --> E[Temporary media processing]
 E --> F[Telemetry lanes]
 F --> G[Evidence package]
 G --> H[Review + dataset builder]
 H --> I[Base model / SFT]
 I --> J[Evaluation]
 J --> K[Local quantized release]
 G --> L[Performance features]
 L --> M[Separate ranker]
 M --> N[Grounded report]
 K --> N
```

## Video sampling policy

Do not hard-code only 1 FPS. Begin with:
- hook window (first 0–3 seconds): dense sampling within a frame budget;
- scene/shot boundaries: sample immediately before/after candidate cuts;
- representative shot midpoints;
- motion peaks and low-motion intervals;
- climax/end frames and possible loop seam.

A 12–16 frame budget is a first VLM experiment, not a coverage guarantee. High-cut clips may require telemetry-only summaries or a second pass. Keep all temporal measurements in JSON even when only a few images enter the VLM.

## Failure handling

- ASR unavailable or language confidence low: mark transcript missing/uncertain; do not fabricate speech.
- OCR low confidence: preserve candidate text and confidence; show image evidence.
- Effect detector uncertain: label as candidate, not fact.
- Source right revoked: block future processing, mark derived artifacts for policy-based deletion and invalidate dataset membership.
- Model output contradicts telemetry: fail validation or downgrade claim to uncertain.

## Explicit non-goals for MVP

- arbitrary Instagram/YouTube downloading;
- foundation model training from scratch;
- 100–200 million video corpus;
- causal virality claims from observational data;
- GRPO/RL before reliable SFT and verifiable reward metrics;
- guaranteed support for every local GPU.
