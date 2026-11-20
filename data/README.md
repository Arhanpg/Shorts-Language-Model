# Data Directory

Keep local datasets and media out of Git. The intended local layout is:

```text
data/
  manifests/       # source IDs, rights references, processing status
  raw-temp/        # temporary authorized media; retention enforced by policy
  frames/          # permitted selected frames
  audio-temp/      # temporary extracted audio when allowed
  telemetry/       # scene, OCR, ASR, motion, audio JSON
  annotations/     # private drafts and reviewed labels
  splits/          # versioned train/validation/test manifests
  shards/          # generated WebDataset/Parquet artifacts
```

Never put raw media, private creator analytics, personal data, consent documents, API keys or restricted derived artifacts in the public repository. See `docs/DATA_AND_COMPLIANCE.md`.
