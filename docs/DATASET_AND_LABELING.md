# Dataset and Annotation Specification

## 1. Data unit

The unit is a video observation, not merely a video ID. One video can have multiple engagement snapshots and processing/annotation versions. Store stable source identity separately from observation time and artifact version.

## 2. Initial composition

The first diagnostic set is 300 videos, then 1,000–2,000 accepted examples. Include multiple platforms only where underlying permissions support processing and training. Do not force a platform ratio before access rights and availability are known.

Sample across language/script, category, duration, creator baseline, view bands, video age, speech/no-speech, visual edit style and publication time. Oversample rare languages and edit patterns for task evaluation, retaining sampling weights for population-level estimates.

## 3. Canonical schema

Link versioned component files rather than embedding every artifact in one large JSON record. The canonical record includes:
- schema version and stable internal video key;
- source/platform/type, private source ID, pseudonymous creator group and rights record ID;
- duration, dimensions, FPS, audio presence and SHA-256;
- metadata snapshots;
- frame, scene, transcript, OCR, audio and editing-event artifact references;
- media-integrity, ASR/OCR status and quality flags.

## 4. Annotation tasks

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
11. Improvement suggestions tied to a timestamp and trade-off.

## 5. Editing taxonomy v0

- Shot: hard cut, fade, dissolve, wipe, flash, match cut, jump cut.
- Motion: static, pan, tilt, zoom, whip pan, shake, tracking, handheld.
- Time: slow motion, speed-up, speed ramp, freeze frame, reverse, timelapse.
- Overlay/compositing: subtitles, kinetic typography, sticker/meme, split screen, picture-in-picture, green screen, mask/composite.
- Image treatment: color grade, contrast/saturation shift, blur, sharpen, vignette, grain, flash/strobe.
- Audio: voiceover, dialogue, music, beat/onset, bass drop, whoosh, riser, crowd, laughter, silence break.

For every class, define positive examples, hard negatives, timestamp tolerance, annotator instructions and whether labels are visually inferable or require editor metadata. A detector should abstain when evidence is ambiguous.

## 6. Creator-relative outcomes

Keep raw metrics immutable with metric name/definition, observed-at timestamp, video age, source and permission scope. Compute normalized features in a separate derived table. Avoid comparing YouTube views to Instagram views without cohort/metric calibration.

A candidate outlier score can compare log-transformed outcomes against a robust creator baseline, but baseline eligibility and minimum sample count must be defined before analysis. Keep same-creator ordinary-performing uploads as controls where permitted. Do not treat one fixed ratio as a law.

## 7. Annotation process

1. Deterministic tools create draft measurements.
2. A VLM may draft descriptions and hypotheses.
3. Rule-based checks verify timestamp ranges and contradictions against measured telemetry.
4. Human reviewers correct high-value fields and adjudicate disagreements.
5. Store draft, corrected label, reviewer, prompt/model/tool versions and quality state separately.
6. Only approved labels enter the gold training set.

Choose review proportions from measured error and disagreement. Reviewing 10–20% is a starting budget hypothesis, not a guarantee; high-risk or low-confidence labels may require full review.

## 8. Data splits

- Creator/account group split, never random rows alone.
- Time-forward holdout.
- Group duplicate/repost/cross-post media before splitting.
- Keep platform-specific and cross-platform transfer tests distinct.
- Lock the golden set and document every use.

## 9. Quality gates

- 100% of accepted records have a rights reference and provenance.
- At least 95% of accepted records have valid core metadata, media integrity, frame manifest and explicit ASR/OCR status (including not-present/failed).
- Timestamp references fall inside video duration.
- Duplicate rate and cross-split leakage are reported.
- Language/category/duration/creator coverage and missingness are reported.
- Human agreement is measured per label, not only globally.
