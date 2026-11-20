# Architecture Decision Record

**Status:** accepted for revised automated-discovery architecture; provider implementation pending  
**Date:** 21 November 2026

## Decision

Build a provider-based system with automated discovery, a policy-aware local SQLite inventory, explicit rights gates and separate authorized media-delivery adapters. Keep the existing deterministic telemetry front-end. Use a compact multimodal VLM and a separate performance model only after dataset QA and evaluation.

The normal workflow should not require pasting one link or manually downloading one MP4 per video. It may still require initial API credentials, institutional approval, creator agreements or a platform partnership. Those are source-access prerequisites, not per-video manual work.

## Component contracts

### Discovery provider

Input: stratified query cell, provider credentials and quota budget. Output: normalized candidate records with provider ID, canonical URL, returned metadata fields, metric definition, observation timestamp, source retention deadline and provenance.

Must use documented API/approved UI only; respect quotas/pagination; expose unsupported fields as missing; support deterministic query plans and resumable cursors; never imply media/training permission.

### Local discovery inventory

Input: normalized provider response. Output: unique retained candidate row and run-level discovery statistics.

Must enforce unique keys/upserts; store retention/refresh deadlines; support deletion/expiry; distinguish metadata-only, rights-pending, authorized, acquired, processed and rejected states; not promise indefinite retention of public API identifiers.

### Rights and policy engine

Check independent capabilities: metadata access, media retrieval, media analysis, temporary processing, raw retention, derived-artifact retention, model training and redistribution. Rights scope is attached per item and source. Public availability, view count, API access, Creative Commons label or temporary downloader success do not imply every capability.

### Media-delivery adapter

Accept only an item with a documented asset-delivery path and necessary permission. Return private asset location, SHA-256, file size, codec/duration, delivery timestamp and rights reference. It may use a provider API, signed upload, creator cloud-drive handoff or approved platform delivery. A generic webpage downloader is not the fallback.

### Telemetry engine

Reuse existing media analyzer: validation, bounded frame/keyframe extraction, shot/cut candidates, motion, ASR, OCR and audio. Each event has timestamp, evidence reference, tool version, config hash, confidence/status and distinction between measured signal and inferred technique.

### Dataset factory

Build reviewed examples from media/metadata whose rights permit the exact training purpose. Track deduplication, creator/time splits, annotations, teacher provenance and quality. A discovery-URL database is not itself a media-training corpus.

### Model factory

Frozen VLM baseline, non-LLM feature baselines, separate performance ranker and task-specific SFT. Training is batch-based, reproducible and checkpointed. Use model-specific settings, not a universal QLoRA recipe.

### Local inference

CLI first, API/UI later. Include resource limits, CPU fallback, configurable frame/token budget, evidence validation and uncertainty/abstention.

## Data flow

    Scheduled run -> seeded query planner -> official APIs / approved research / licensed providers
        -> normalized candidates -> view threshold + short-format confidence
        -> SQLite dedup + retention manager -> rights/capability gate
        -> metadata-only/deferred OR approved media delivery
        -> private staging + checksum -> telemetry engine
        -> evidence store + review -> dataset QA/splits
        -> baselines/SFT/evaluation -> local quantized release

## Explicit non-goals

- Arbitrary public YouTube/Instagram bulk MP4 downloading.
- Scraping web pages, using browser cookies or bypassing restrictions.
- Claiming 100/200 candidate target is guaranteed every run.
- Treating a metadata-only candidate as a trainable media asset.
- Indefinite API-data retention without an applicable allowance.
- One-step online fine-tuning per downloaded video.
- Causal virality claims from observational data.
- Training from scratch or guaranteed 4 GB GPU compatibility.

## Revisit criteria

Add a source only when its API/provider contract or creator agreement documents discovery, retrieval, storage, training and deletion rights. Revisit model choice only after candidates can be compared using the same locked dataset and input budget.
