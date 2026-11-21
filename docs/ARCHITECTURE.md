# ShortsLM Architecture — Open-Source Discovery Edition

**Status:** selected implementation architecture  
**Date:** 21 November 2026

## System flow

```text
Query planner (topic/language/region/date)
        |
        +----> ytscrape SearchFilter.SHORTS provider (YouTube)
        |
        +----> DDGS public-web search (Instagram Reel URLs)
                      |
                      v
                Instaloader shortcode metadata
                      |
                      v
        Normalization + 1M metric / short-format gate
                      |
                      v
              Local SQLite candidate inventory
             unique (platform, source_id)
                      |
                      v
             Private item-rights manifest gate
                      |
                      v
    yt-dlp (YouTube) / Instaloader → yt-dlp → gallery-dl (Instagram)
                      |
                      v
           MP4 + metadata/rights sidecar
                      |
                      v
              SHA-256 cross-platform dedup
                      |
                      v
          Existing Phase 1 local telemetry analyzer
                      |
                      v
           Review / dataset QA / train-test splits
                      |
                      v
          Frozen VLM baseline -> cloud fine-tuning
                      |
                      v
              Quantized local inference
```

## Components

### Discovery adapters

- YouTube: ytscrape's dedicated Shorts search filter, parse typed search metadata.
- Instagram: DDGS query public Reel URLs and Instaloader resolves shortcodes.
- Instaloader's hashtag discovery is optional and requires a user session.
- Combined discovery schedules both selected platform stages under the shared runtime deadline and reports independent execution states.
- No official platform API is used by the discovery CLI.

### Candidate normalizer

Maps tool-specific metadata into DiscoveredCandidate. Missing fields remain null/unknown. View count and play count are separate. Short-format status uses explicit URL and duration/dimensions/date evidence.

### Inventory

SQLite tracks discovery runs, candidate identity, metadata, status and download attempts. Unique (platform, source_id) prevents link repeats. SHA-256 prevents byte-identical media being processed twice across sources.

### Rights gate and downloader

A local JSONL record has to match both platform and source ID and declare each required permission scope. The code checks expiry/revocation and flags. It does not verify legal documents cryptographically or establish rights independently. Missing/invalid records block download.

Open-source extractor order:
- YouTube: yt-dlp plus FFmpeg.
- Instagram: Instaloader, then yt-dlp, then optional gallery-dl.

No access-control bypass is built.

### Existing telemetry and model path

The current Phase 1 local analyzer stays the downstream video feature extractor. It continues to produce ASR, OCR, frames, shot/cut, motion, audio and structured reports. Model training is batch-based after QA, not incremental per video.

## Non-goals

- Official platform API-key flow for discovery.
- Promise that every public Reel/Short is searchable/downloadable.
- Uniform sampling claim from search-engine rankings.
- Treat a public view counter as permission to download/train.
- Browser cookie extraction, CAPTCHA bypass, DRM circumvention or proxy evasion.
- Train-from-scratch foundation model.
