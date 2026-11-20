# Compute, Storage and Cost Engineering

## Hardware division

### Local laptop: RTX 3050 4 GB

Use for development, FFmpeg, CPU/OpenCV processing, small smoke tests, quantized inference experiments and UI/API work. Run extractors sequentially. Do not treat the 4 GB GPU as a training platform for 2B/4B multimodal BF16 LoRA. CPU fallback is mandatory for preprocessing and useful for smaller inference models.

### Notebook services

Colab and Kaggle are suitable for demonstrations and short experiments. Session limits, hardware variability, persistence and connection constraints make them poor production orchestrators. Export checkpoints/logs to durable storage; never rely on notebook disk as the only copy.

### Rented GPU

Use SSH-capable instances with persistent volume, tmux, Docker/venv, checkpoint sync and idle shutdown. Start with a 24 GB-class GPU for compact-model SFT if the chosen recipe fits. Use larger-memory hardware for teachers or multi-frame/long-context experiments. Provider pricing and stock are dynamic.

## Pilot measurements

On 300 representative authorized videos, record per-stage:
- decode/validation CPU seconds;
- frame extraction and scene detection seconds;
- optical-flow/learned vision CPU/GPU seconds;
- OCR/ASR/audio seconds and GPU memory;
- model annotation input/output tokens and cost;
- review minutes/video;
- storage by artifact class;
- failure/retry rate;
- accepted examples per processed video.

Calculate cost per accepted example as total compute + storage + paid annotation + human review + data-access cost, divided by accepted training examples. Define whether values are per clip, accepted sample or instruction example.

## Storage scenarios

Raw bytes = video count × measured average media bytes.  
Feature bytes = video count × measured average feature-bundle bytes.

Measure keyframe count, dimensions, image encoding/quality, transcript/audio retention, JSON, embeddings and backup/redundancy. Do not assume 0.83 MB/video until measured.

## Supplied cost chart is not a quote

The image estimates $112.25 for 50K and $449,004 for 200M. It assumes specific throughput, frame/feature size, token count, GPU rental, teacher pricing and storage. None has been benchmarked in this repository. It may omit data licensing, human review, failure/retry, distributed orchestration, backups and rights audits. Retain it only as a scenario.

## Operations

- Job IDs and idempotency keys.
- Durable manifests before processing.
- Bounded queues and backpressure.
- Limited retries; dead-letter persistent failures.
- Checkpoints synced off-instance.
- Automatic idle GPU shutdown.
- Record instance SKU, region, runtime, storage and taxes.
