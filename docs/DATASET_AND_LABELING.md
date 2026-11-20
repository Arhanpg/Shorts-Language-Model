# Dataset and Annotation Specification

## 1. Data unit

The unit is a video observation, not merely a video ID. One video can have multiple engagement snapshots and processing/annotation versions. Store stable source identity separately from observation time and artifact version. Keep a provider retention deadline for every source-derived identifier and metadata field.

## 2. Acquisition provenance

A record begins as a discovered candidate; it is not a training asset until the media itself has been delivered through an authorized route.

Record at minimum:
- schema version and stable internal candidate key;
- platform, provider, source item ID/permalink and discovery run ID;
- discovery method/query cell, discovered-at and last-seen times;
- metric value, definition and observed-at time;
- title/caption, description, tags/hashtags and metadata source;
- metadata retention class, refresh/delete deadline and provider policy version;
- media-delivery provider, rights evidence and explicit media/training scopes;
- media asset checksum, duration, resolution, FPS and audio presence after delivery;
- transcript/OCR/scene/audio/editing evidence references and extractor versions.

Do not retain API-derived source IDs or metadata beyond the applicable provider policy. A hashed identifier is not assumed exempt. Keep the SQLite discovery ledger and its retention jobs out of the public repository.

## 3. Initial composition

The first diagnostic set is up to 300 rights-cleared media assets, not 300 discovered URLs. Later targets are 1,000–2,000 accepted examples. Include multiple platforms only where media rights and platform terms support processing and training. Do not force a platform ratio before access and availability are known.

Sample across language/script, category, duration, creator baseline, view bands, video age, speech/no-speech, edit style and publication time. Oversample rare languages/edit patterns for task evaluation, retaining sampling weights only where source policy permits derived statistics.

## 4. Canonical schema

Link versioned component files rather than embedding every artifact in one large record. The canonical record includes:
- schema version and stable internal candidate/video key;
- source/platform/provider, private source ID, pseudonymous creator group and rights record ID;
- discovery run, query stratum and provider-retention deadline;
- metadata snapshots and metric observation timestamps;
- media asset reference, SHA-256, duration, dimensions, FPS and audio presence;
- frame, scene, transcript, OCR, audio and editing-event artifact references;
- media-integrity, ASR/OCR status and quality flags.

## 5. Annotation tasks

Create independent tasks so one clip yields several useful examples:
1. Grounded video summary and event sequence.
2. Hook-window detection and hook type.
3. Shot boundaries and pacing description.
4. Editing effect candidates with start/end timestamps.
5. On-screen text, position, style and communicative function.
6. Speech language, transcript alignment and speaker-turn segmentation when appropriate.
7. Music/sound design, silence, energy and beat alignment.
8. Narrative arc: setup, escalation, payoff and loop structure.
9. Platform/title/description/hashtag interpretation where permitted.
10. Performance hypothesis with missing evidence stated.
11. Improvement suggestions tied to timestamp and trade-off.

## 6. Editing taxonomy v0

- Shot: hard cut, fade, dissolve, wipe, flash, match cut, jump cut.
- Motion: static, pan, tilt, zoom, whip pan, shake, tracking, handheld.
- Time: slow motion, speed-up, speed ramp, freeze frame, reverse, timelapse.
- Overlay/compositing: subtitles, kinetic typography, sticker/meme, split screen, picture-in-picture, green screen, mask/composite.
- Image treatment: color grade, contrast/saturation shift, blur, sharpen, vignette, grain, flash/strobe.
- Audio: voiceover, dialogue, music, beat/onset, bass drop, whoosh, riser, crowd, laughter, silence break.

For every class, define positive examples, hard negatives, timestamp tolerance, annotator instructions and whether labels are visually inferable or require editor metadata. A detector should abstain when evidence is ambiguous.

## 7. Creator-relative outcomes

Keep raw metrics immutable with metric name/definition, observed-at timestamp, video age, source and permission scope. Compute normalized features only where provider policy, rights and approval allow the intended use. Do not assume a public YouTube Data API view count can be retained or used for custom metrics indefinitely without the applicable YouTube analytics amendment. Do not combine YouTube API metrics with Instagram metrics into one undifferentiated score.

A candidate outlier score can compare log-transformed outcomes against a robust creator baseline, but baseline eligibility and minimum count must be defined before analysis. Keep same-creator ordinary-performing uploads as controls where permitted. Do not treat one fixed ratio as a law.

## 8. Annotation process

1. Deterministic tools create draft measurements.
2. A VLM may draft descriptions/hypotheses.
3. Rule-based checks verify timestamps and contradictions against telemetry.
4. Human reviewers correct high-value fields and adjudicate disagreements.
5. Store draft, corrected label, reviewer, prompt/model/tool versions and quality state separately.
6. Only approved labels with training permission enter the gold training set.

Choose review proportions from measured error and disagreement. Reviewing 10–20% is a starting budget hypothesis, not a guarantee; high-risk or low-confidence labels may require full review.

## 9. Data splits

- Creator/account group split, never random rows alone.
- Time-forward holdout.
- Group duplicate/repost/cross-post media before splitting.
- Keep platform-specific and cross-platform transfer tests distinct.
- Lock the golden set and document every use.

## 10. Quality gates

- 100% of accepted training media have a rights reference and provenance.
- At least 95% of accepted records have valid core metadata, media integrity, frame manifest and explicit ASR/OCR status (including not-present/failed).
- Timestamp references fall inside video duration.
- Duplicate rate and cross-split leakage are reported.
- Language/category/duration/creator coverage and missingness are reported.
- Human agreement is measured per label, not only globally.


## 11. Non-API acquisition integration

The source identity is produced by the selected open-source extractors (yt-dlp or Instaloader) and stored in SQLite. Preserve which extractor returned the metric and the observation/discovery timestamp. Store Instagram view count and play count in separate fields; do not blend them in one training target. A result without a known metric cannot be labelled as 1M+.

Before a downloaded media asset enters this specification, the local acquisition workflow must have a rights manifest granting retrieval, media analysis, temporary processing, derived artifact retention and model-training use. This manifest is an evidence pointer and local assertion, not an independent legal verification. The dataset builder should reject unresolved/revoked/expired entries.

Use SHA-256 for exact file-level duplicate checks after download. This does not detect transcodes or alternate encodings; a later perceptual near-duplicate step remains required before the golden split. Candidate URL deduplication and media-byte deduplication are separate checks.
