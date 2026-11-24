# ShortsLM Feature Extraction Specification

**Version:** 1.0-draft  
**Date:** 24 November 2026  
**Status:** P0 schema contract; freeze only after pilot validation.

## 1. Design goals

- Preserve time, evidence, uncertainty and provenance.
- Represent both speech-bearing and speech-free clips.
- Support Hindi-English and other code-switching without forcing one video-level language.
- Separate measured signals from model-generated interpretations.
- Keep raw source metrics immutable and platform-native.
- Keep the default runtime small and dependency count low.

## 2. Data model

A video is not one flat JSON blob. Store a stable internal video key and versioned components:

1. `video_manifest.json` — media facts, source metadata reference, rights state and processing versions.
2. `timeline.jsonl` — timestamped events from all modalities.
3. `transcript.json` — ASR segments and optional words.
4. `ocr.json` — OCR tracklets and text spans.
5. `features.json` — aggregated scalar/vector features and missingness.
6. `engagement_snapshots.jsonl` — platform-native metric observations.
7. `annotations.json` — machine drafts, human corrections and adjudication kept separately.
8. `provenance.json` — extractor/model/version/config hashes, evidence references and permission lineage.

During the pilot, JSON/JSONL is sufficient. Move structured high-volume arrays to Parquet after schema and workload stabilize. Dense embeddings are external binary artifacts referenced by URI, dimension, dtype and model version.

## 3. Canonical time representation

- Use media presentation timestamps (PTS) from the container where possible; retain stream time-base and map to seconds.
- Use `start_s` and `end_s` as normalized seconds for interoperability.
- Intervals are half-open: `[start_s, end_s)`.
- Point events use equal start/end or an explicit `event_time_s` (choose one consistently in implementation).
- Preserve original timestamp precision; round only for display.
- Validate every event against media duration.
- For VFR, do not derive timestamps from frame index × nominal FPS.
- Store frame index as supporting metadata, never as the sole time source.

## 4. Semantic missingness/status enum

Every modality and optional field should expose one of:

| Status | Meaning |
|---|---|
| `PRESENT` | Valid evidence was extracted. |
| `ABSENT_IN_MEDIA` | Modality/event is genuinely absent (e.g. no speech detected). |
| `NOT_APPLICABLE` | Field does not apply to this media/task. |
| `UNAVAILABLE_FROM_SOURCE` | Platform/source did not expose the field. |
| `PERMISSION_DENIED` | Required permission was not granted. |
| `EXTRACTION_FAILED` | Attempted extraction failed. |
| `BELOW_CONFIDENCE_THRESHOLD` | Candidate evidence exists but is too uncertain. |
| `NOT_YET_PROCESSED` | Work has not run yet. |

Do not replace missingness with numeric zero. For example, zero detected speech is a measured result; ASR failure is not.

## 5. Core feature groups

### P0 — required

| Group | Fields / examples | Granularity | Default extractor |
|---|---|---|---|
| 1. Media manifest | duration, width, height, codec, nominal/average FPS, VFR, audio streams, time-base, decode status | video/stream | FFprobe + FFmpeg |
| 2. Platform metadata | platform, native metric name/value, creator/source ref, published_at, observed_at, age_hours, metric provenance | snapshot | existing discovery metadata |
| 3. Speech presence | speech intervals, speech_ratio, VAD confidence, silence intervals | 10–30 ms internal, aggregated to 1 s | existing VAD adapter |
| 4. Transcript | text_raw, text_normalized, language spans, segment start/end, confidence, speaker-local ID if reliable, hallucination flags | segment; word optional | one faster-whisper checkpoint |
| 5. Language/code-switch | language probability per segment, detected language set, script, switch boundary candidates, CMI optional | 2–5 s segment and token tags where supported | ASR language output + lightweight text LID |
| 6. OCR | text, script/language, normalized bbox, start/end, tracklet ID, confidence, text role candidate | frame/tracklet | existing PaddleOCR |
| 7. Audio signal | RMS/loudness, spectral flux, onset strength, tempo/beat candidates, clipping, music/speech/silence ratio | 0.1–1 s | librosa/NumPy signal processing |
| 8. Visual sampling | frame PTS, frame index, sample reason, image dimensions, sharpness/quality | frame | FFmpeg/OpenCV |
| 9. Shot/edit baseline | shot start/end, shot duration, cut candidate/confidence, cuts per minute, opening cut density | shot/event | existing shot logic + OpenCV |
| 10. Motion baseline | frame-to-frame motion magnitude/direction, camera/subject ambiguity, motion bursts | 0.1–1 s | OpenCV |
| 11. Hook evidence | first salient speech/text/audio/motion event, start time, evidence refs; verbal/visual/acoustic hook candidates | event in 0–3 s | derived from P0 lanes |
| 12. Provenance/quality | extractor/model/version, config hash, run ID, source refs, confidence, missingness, error details | every artifact | pipeline |

### P1 — conditional modules

| Group | Fields / examples | Granularity | Activation gate |
|---|---|---|---|
| 13. Person tracking | anonymous video-local track ID, bbox, visible ratio, track confidence | frame/track | person/action research need |
| 14. Pose/motion | keypoints, visibility, posture, joint velocity, kinetic energy, gesture cadence | 2–5 Hz or validated rate | selected pose model passes license/runtime benchmark |
| 15. General actions | action label, start/end, track ID, confidence, evidence refs | action interval | gold labels + held-out evaluation |
| 16. Objects/HOI | object label, bbox/track, person-track, predicate candidate, interval, confidence | frame/interval | detector adds measured value |
| 17. Music/sound events | class, start/end, confidence, music embedding ref, beat/downbeat candidates | event/0.5–2 s | one lightweight model passes benchmark |
| 18. Text-speech relation | reinforcement/complement/contradiction, aligned text/audio refs, confidence | text tracklet/utterance | semantic review sample available |
| 19. Editing taxonomy | jump cut, transition, speed change, overlay, split screen, zoom, camera movement | event/shot | taxonomy and annotations stable |
| 20. Narrative spans | setup, conflict, reveal, payoff, CTA, loop, non-narrative performance | interval | human-reviewed benchmark |
| 21. Scene/context | indoor/outdoor, studio/kitchen/stage/sports etc., scene confidence | shot | visual model/license gate |
| 22. Appearance (observable only) | visible garment category/color/wardrobe change | shot/track | explicit task need; no sensitive inference |

### P2 — research-only until proven

- Fine-grained dance styles and choreography matching.
- Speaker diarization and active speaker association.
- Source separation (HTDemucs), dense audio encoders, high-capacity video encoders.
- Open-vocabulary HOI, segmentation masks, graph neural networks.
- Cross-modal contrastive embedding training and foundation-model hidden-state regression.

## 6. Transcript schema

Minimum segment:

```json
{
  "segment_id": "asr_00012",
  "start_s": 4.18,
  "end_s": 5.73,
  "text_raw": "Aaj ka result is actually surprising",
  "text_normalized": "Aaj ka result is actually surprising",
  "language_spans": [
    {"start_s": 4.18, "end_s": 4.83, "language": "hi", "script": "Latn"},
    {"start_s": 4.83, "end_s": 5.73, "language": "en", "script": "Latn"}
  ],
  "confidence": null,
  "status": "PRESENT",
  "speaker_local_id": null,
  "hallucination_risk": "UNASSESSED",
  "extractor": {"name": "faster-whisper", "model": "selected-checkpoint", "version": "pinned"}
}
```

Confidence may be null if the ASR backend does not expose a calibrated confidence. Do not fabricate a score. Preserve raw text; normalization must not erase code-switching or script distinctions. Add word-level timestamps only when their alignment quality is measured.

## 7. Timeline event schema

```json
{
  "event_id": "evt_0019",
  "video_key": "internal-video-key",
  "modality": "audio",
  "event_type": "music_onset",
  "start_s": 6.20,
  "end_s": 6.20,
  "payload": {"onset_strength": 0.82},
  "confidence": null,
  "status": "PRESENT",
  "evidence": [{"kind": "audio_window", "start_s": 5.9, "end_s": 6.5}],
  "extractor": {"name": "librosa", "version": "pinned"},
  "created_at": "2026-11-24T00:00:00Z"
}
```

This is an illustrative contract. Replace placeholder timestamps and IDs with actual measured values; never treat this example as data.

## 8. Engagement snapshot schema

```json
{
  "platform": "instagram",
  "metric_name": "video_play_count",
  "metric_value": 123456,
  "metric_kind": "plays",
  "observed_at": "2026-11-24T00:00:00Z",
  "published_at": "2026-11-20T00:00:00Z",
  "age_hours": 96,
  "source": "existing-discovery-adapter",
  "exactness": "exact",
  "availability_status": "PRESENT",
  "permission_scope": "as-recorded"
}
```

YouTube views, Instagram views and Instagram plays are distinct. Do not silently map one to another or merge into a universal outcome. If creator-authorized watch-time/retention is unavailable, mark it unavailable; do not infer it from public counts.

## 9. Quality flags and validation

- Transcript: language/script known where possible; segment bounds valid; music-only false positives measured.
- OCR: bbox normalized to [0,1]; timestamps inside duration; duplicate tracklets merged; script-wise error reported.
- Audio: sample rate/channel conversion recorded; no silent clipping; feature windows align with PTS.
- Video: decode errors and dropped frames reported; VFR preserved; sample reasons logged.
- Actions: interval and track evidence required; fine-grained labels may abstain.
- Metrics: native definition, observation time, source and exactness required.
- Provenance: all model outputs carry model and extractor versions; human edits retain reviewer and annotation version.
- Dataset: creator/duplicate/audio-template groups cannot leak across evaluation splits.

## 10. Output acceptance gate

A 10-video smoke test must produce schema-valid manifests, timelines and status fields. A 100–300 video pilot must report per-stage runtime, peak VRAM/RAM, failure/retry rate, quality metrics by language/script/content type, and accepted outputs per processed clip. No throughput number is accepted until measured on this workload.

## 11. Privacy and rights

Use anonymous video-local IDs only. Do not identify people across videos, infer sensitive traits from clothing/voice/appearance, or profile minors. Retrieval, analysis, temporary processing, derived-artifact retention and model training each require the appropriate rights. Keep raw media, transcripts, private identifiers, rights evidence and platform credentials outside Git.
