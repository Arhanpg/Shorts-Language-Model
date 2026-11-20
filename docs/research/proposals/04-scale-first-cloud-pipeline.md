# Proposal 4 — Scale-Ready Cloud Data and Model Factory

## Original direction

Design the pipeline with large-scale engineering disciplines from the beginning while retaining a small diagnostic smoke test. The proposal emphasizes provider adapters, partitions, manifests, resumable jobs, sharding, queues, checkpoints and observability.

## Proposed two-plane design

### Data / telemetry plane

1. Discovery and metadata capture.
2. Source provenance and rights checks.
3. Eligibility filtering and deduplication.
4. Temporary media processing where authorized.
5. Video/audio extraction and specialist telemetry.
6. Evidence manifest and feature store.
7. Label generation and human review.

### Model factory plane

1. Versioned dataset manifest and train/validation/test splits.
2. Base-model benchmark.
3. SFT with LoRA/QLoRA/DoRA as supported by the exact model.
4. Optional later preference optimization or RL.
5. Evaluation and regression tests.
6. Quantized local artifact and inference API.

## Distributed-data engineering ideas

- Idempotent stages and stable job IDs.
- Partitioned manifests and provider-specific quota managers.
- Bounded queues, backpressure and dead-letter handling.
- Checkpoint recovery and off-instance checkpoint sync.
- Sequential data shards (Parquet/WebDataset) once small-file I/O is a measured bottleneck.
- Cost counters at each pipeline stage.
- Rights-aware retention and deletion invalidation.
- Separate CPU preprocessing workers from GPU training workers.
- Automatic idle GPU shutdown and instance-cost tracking.

## What the combined plan accepts

The scale-ready contracts should be designed early: provenance manifests, idempotency, retries, bounded resource use, versioned features, dataset lineage and per-video cost measurements. This avoids rewriting components when moving beyond a laptop.

## What changes

- Scale-ready architecture does not mean running 50K/200M jobs before the diagnostic pilot.
- Rights gates and source capability checks must run before acquisition and every derived operation.
- Colab/Kaggle are experiments, not production queue orchestrators.
- GPU provider rate cards are volatile and need live quotes, storage costs and interruption overhead.
- A 0.83 MB artifact bundle or 2 GPU-seconds per clip is an assumption until measured.
- Distributed systems such as Ray/Airflow/Kafka should not be introduced before concurrency and operational needs require them.

## Final disposition

**Accepted as infrastructure principles, deferred as deployment complexity.** Start with local manifests and a simple queue/worker; preserve interfaces that support object storage and sharded data. Add distributed workers only when the 300-video profile and later batch requirements justify them.
