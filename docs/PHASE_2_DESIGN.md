# Phase 2 — Open-Source Media Acquisition

**Goal:** automatically download eligible discovered media to the local laptop without manually fetching MP4s, using the source-specific open-source extractors already selected.

## Inputs

- SQLite candidate row with platform, source ID, canonical URL, current metric snapshot and discovery state.
- Private rights JSONL entry that matches the platform/source ID and explicitly grants media retrieval, analysis, temporary processing, derived-artifact retention and model training.
- Local output directory and optional user-created Instaloader session.

## Provider order

### YouTube

Use yt-dlp on the canonical video URL. Select best available video/audio format and remux to MP4 using FFmpeg. Preserve the source candidate metadata in a JSON sidecar.

### Instagram

Try:
1. Instaloader Post.from_shortcode + download_post;
2. yt-dlp Instagram extractor;
3. optional gallery-dl command-line fallback.

A failure in one adapter proceeds to the next ordinary extractor; if all fail, store the error and leave the item retryable. Do not use browser-cookie extraction, proxy rotation, CAPTCHA/challenge bypass or other access-control evasion.

## Rights state

A candidate cannot enter download merely because its view count is above 1M. The rights manifest row is a local declaration and evidence pointer. The downloader validates:
- matching platform and source ID;
- known basis and evidence reference;
- current/unexpired permission;
- not revoked;
- separate retrieval, analysis, processing, retention and training permissions.

If no row is present, the item remains queued/blocked. The application cannot independently establish whether the consent or license is genuine.

## Asset validation and uniqueness

After each successful download:
1. require a non-empty MP4;
2. generate private metadata/rights sidecar;
3. run FFprobe in the processing/validation step;
4. calculate SHA-256;
5. compare with already acquired assets across both platforms;
6. if identical bytes exist, delete the redundant file and mark duplicate_media;
7. otherwise mark downloaded and retain local path/hash.

An identical SHA-256 indicates exact file equality. A future perceptual hash stage is needed for visually identical but re-encoded files.

## Local execution

Run discovery and download on the laptop. Neither operation requires the RTX 3050. The GPU will matter later for local model experiments; cloud GPU is for fine-tuning. Do not use Colab as the durable scheduler or state store.

## Exit criteria

- At least one authorized YouTube asset can be downloaded via yt-dlp.
- At least one authorized Instagram Reel can be downloaded by Instaloader or a documented fallback.
- Metadata sidecars contain candidate + rights provenance.
- Missing, expired or revoked rights block download.
- FFprobe and SHA-256 validation succeed.
- Same platform/source ID is not downloaded twice.
- Exact cross-platform duplicate media is removed/marked once.
- Failures are retryable and reported.
- No local media, DB, session or consent files are committed.
