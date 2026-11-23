# Shorts-LM global discovery catalogue — reconciliation audit

**Audit date:** 23 November 2026  
**Primary source:** Gemini Deep Research document  
**Supplementary sources:** expanded AI CSV/JSON pack, earlier compact CSV pack, NotebookLM report, Executive Summary PDF, and the current repository documentation/code.

## Decision

**Partially ready as a discovery seed catalogue; not ready as a training dataset or gold model test set.** The AI outputs provide useful language, category, creator, hashtag and query leads. They do not provide rights-cleared media, complete row-level identity evidence, measured hashtag popularity, human-reviewed annotations or a locked media holdout.

## Reconciled inventory

The expanded AI pack contains 71 language rows, 30 category IDs with 362 subcategory rows, 143 creator records, 686 hashtag candidates, 4,658 generated query rows and 1,420 language/category diversity rows. Gemini supplies 63 language/variety records, 23 primary domains, 105 core creator rows, 70 hashtag rows, 60 query templates and six high-level diversity strata. NotebookLM and the earlier compact CSV/PDF outputs are older, narrower variants and are retained as supplementary inputs.

The reconciled v0.1 release contains 71 normalized language/community scopes, 362 proposed subcategory rows under 30 domains, 300 deduplicated creator/account leads, 371 separately held handle-only mentions from Gemini regional rosters, 59 regional roster rows, 802 hashtag candidates, 4,744 query candidates, 1,420 proposed diversity cells and 50 synthetic contract fixtures. Exact counts and SHA-256 checksums are in QA_SUMMARY.json in the release archive.

## Evidence corrections

### Creator accounts

Gemini labels all 105 core creator rows VERIFIED, but the source_url evidence cell is empty for all 105 rows. Supplied profile URLs are unchecked targets; a profile URL does not establish that a paired account is official, active on Shorts/Reels, original, correctly localized or rights-cleared. The expanded pack's 143 records include 99 imported repository seeds and a large majority of unverified or pending statuses. The canonical release preserves source-claimed statuses but uses conservative verification_state values. All creator rows remain NOT_ASSESSED_DISCOVERY_ONLY for rights.

### Hashtags

The expanded pack's 686 hashtags are explicitly unverified and have blank source_url values. Gemini's 70-row table marks its tags verified, but all 70 source URL cells are also blank. A constructed hashtag search URL is not evidence of frequency, popularity, script correctness or retrieval yield. Every tag remains a candidate pending native-speaker review and bounded empirical testing.

### Search queries

The expanded 4,658-row list is generated query expansion, not 4,658 manually executed searches. 3,938 rows lack related_hashtags. The merged list marks queries as unexecuted and records platform-routing guidance. Instagram text-query rows are not treated as directly executable by the current graph collector; they need conversion to supported creator/hashtag seed actions or manual review.

### Diversity quotas

Gemini's six broad strata and the expanded 1,420-cell matrix are proposals, not observed platform coverage or feasible acquisition quotas. Use them to identify gaps after the first rights-cleared pilot, then set quotas from observed yield and rights-cleared supply.

## Architecture decision conflict

Gemini recommends official YouTube Data API and Meta Content Library/API workflows. The current repository's ADR-003 explicitly excludes official platform APIs and specifies the non-API discovery approach. The existing ADR remains authoritative. This release does not add official API clients or change the Phase 3/creator-graph implementation. The official API route is an alternative requiring an explicit project-owner decision and separate legal/engineering review.

A second mismatch: Gemini recommends retiring the global one-million metric floor for discovery inclusion, while current graph code/docs still describe min_metric=1,000,000 as the default. Do not treat one million views as a language-neutral quality label. Discovery retention, processing eligibility and virality cohorts should be separate policies. This release documents the mismatch but does not change Phase 3 or rerun its commands.

## Rights and child-safety gate

Public visibility, a profile link, an AI report's VERIFIED label or a successful extractor call is not permission to download, store, analyze, retain derived artifacts or train. Each media asset requires separate item-level permission scopes. The release's rights-provenance schema defaults every permission to false. The optional YouTube video-trainability signal is not a substitute for download/storage authorization.

Catalogue official children's studios separately from family/UGC content that may contain minors. Do not collect minor PII or infer real viewer ages/identities. Do not bypass logins, challenges, CAPTCHAs, blocks, rate limits or DRM.

## Readiness blockers

1. No video assets were present in the uploaded research outputs.
2. No item-level rights records prove retrieval, storage, processing or model-training grants.
3. Creator ownership, account pairing, current short-form activity, language, region and original-publisher status require live verification.
4. Hashtag frequency and retrieval yield are not measured; native-script forms need community review.
5. Query precision/recall, duplicate yield and freshness have not been measured.
6. No human-reviewed annotation gold set or media-backed holdout exists.
7. No actual media/perceptual duplicate groups, creator-disjoint split or time-forward holdout exists.

## Synthetic fixture interpretation

The 50 release JSONL cases are synthetic metadata-only contract fixtures. They exercise language/script preservation, code-switching, ASR/OCR failures, editing timestamps, hook abstention, platform metric semantics, duplicate grouping, default-deny rights and child-content safeguards. They contain no video/audio, are not human annotated, and are not model-accuracy benchmarks.
