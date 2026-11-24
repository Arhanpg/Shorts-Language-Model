# ShortsLM Architecture — Minimal Multimodal Evidence Pipeline

**Updated:** 24 November 2026  
**Status:** selected target architecture; reuse current working code and validate before replacing components.

## System flow

```text
Existing discovery providers + SQLite
          |
          v
Metadata snapshot + item-specific rights gate
          |
          v
Authorized acquisition + FFprobe validation
          |
          v
FFmpeg decode-once / PTS timeline
          |
     +----+--------------------+
     |                         |
     v                         v
Audio lane                 Visual lane
VAD + one ASR              adaptive frames
audio signal features      OCR + shot/motion
music/beat candidates      optional pose/action
     |                         |
     +-----------+-------------+
                 v
       Timestamped evidence timeline
      confidence + missingness + provenance
                 |
       +---------+----------+
       |                    |
       v                    v
Deterministic aggregation   Optional VLM
and quality checks          fallback (one API)
       |                    |
       +---------+----------+
                 v
        Versioned feature bundle
                 |
        human review / annotation
                 |
        leakage-safe dataset splits
                 |
       +---------+----------+
       |                    |
       v                    v
Content understanding   Performance model
temporal fusion         CatBoost baseline
       |                    |
       +---------+----------+
                 v
     evidence-grounded report / API
                 |
        quantized local deployment
```

## Components and boundaries

### Discovery and inventory
Keep existing discovery adapters and SQLite inventory. Discovery is not permission to download or train. Preserve platform-native metric definitions and source observation time.

### Rights and media acquisition
Keep the existing rights gate and downloader. Retrieval, analysis, temporary processing, derived-artifact retention and model training are separate scopes. Do not add access-control bypasses. Use FFprobe to validate media and FFmpeg to produce normalized audio/frame streams with PTS.

### Audio lane
Reuse the existing VAD and faster-whisper adapter. Choose one ASR checkpoint by benchmark; default candidate is large-v3-turbo INT8 only if it beats the currently configured model on the held-out short-form sample. Extract low-cost audio signals in one pass. Do not require gated diarization, multi-ASR ensembles or source separation in the default path.

### Visual lane
Reuse the existing OCR adapter. Begin with OpenCV and current scene/shot logic; add one shot detector or one pose model only when benchmark evidence warrants it. Sample frames adaptively rather than uniformly at a fixed low rate. Fine-grained dance/action labels require a reviewed taxonomy and class-wise evaluation.

### Evidence timeline
All outputs share PTS-derived time. Events include modality, event type, start/end, payload, confidence/quality, evidence reference, extractor/version and missingness status. A failed ASR stage cannot be interpreted as a silent clip.

### Optional reasoning
One optional Gemini API key can be used for selected, rights-approved clips. It is not part of local default processing. Apply cost caps, log provider/model/prompt and verify every claim against evidence. Do not automatically upload private media.

### Storage
Keep SQLite for job state and JSON/JSONL for pilot artifacts. Adopt Parquet only after schema stabilization. Store large embeddings separately and only when an experiment needs them. Keep private media, transcripts, credentials and rights evidence outside Git.

### Training and prediction
Train the temporal understanding head only after human-reviewed labels and a locked holdout exist. Keep engagement prediction as a separate model. Start with CatBoost for structured engagement features.

## Operational principles
- Load large models sequentially and release resources between stages.
- CPU fallback for decode/preprocessing and supported inference stages.
- Every stage has timeout, retry limit, idempotency key and persisted status.
- Cache successful artifacts so failures do not repeat expensive upstream stages.
- Record actual device, runtime, peak memory, model version and failure reason.
- Measure throughput and cost on the actual laptop/cloud SKU; do not copy research estimates as benchmarks.

## Non-goals
- Training a foundation model from scratch.
- Installing every model named in the Gemini report.
- Mandatory Hugging Face token or ten different vendor accounts.
- Treating view count as causal virality or retention.
- Inferring identity or sensitive attributes from people in videos.
