# Data Acquisition, Rights and Governance — Non-API Toolchain

## Scope

ShortsLM now uses open-source search and extractor tools for discovery rather than official YouTube/Instagram platform API clients:
- yt-dlp for YouTube search, metadata and downloading;
- DDGS for public search-indexed Instagram Reel URLs;
- Instaloader for Instagram shortcode metadata, hashtags and media download;
- yt-dlp and optional gallery-dl as Instagram fallback extractors;
- local SQLite for source identity and job state.

This change avoids platform API keys in the selected workflow. It does **not** remove website terms, copyright, privacy, consent or model-training obligations. It also does not make web search complete or unbiased.

## Separate permissions

A discovered URL, public view count, or successful extractor call is not by itself proof of:
- permission to retrieve/copy the media;
- permission to analyze the media;
- permission to temporarily process it;
- permission to retain transcripts, frames, OCR or other derived artifacts;
- permission to train a model;
- permission to redistribute the resulting media or model.

Keep those scopes separate in each item's rights record. Include source ID, rights basis, evidence reference, applicable rights-holder coverage, expiry, revocation and restrictions. Account for embedded music, performances, stock material, broadcast clips, overlays and other third-party rights.

The app's private JSONL rights manifest is a **local attestation and evidence pointer**. The program checks that a matching record exists, that its flags cover the intended use, and that it is not expired/revoked. The program does not authenticate the document, verify ownership or independently decide whether the grant is legally sufficient. A project owner must not fabricate or infer permission from public visibility.

## Open-source extractor boundaries

### yt-dlp

Use the normal public-site extractor, ytsearch search prefix and source URL download path. Do not use options/workarounds intended to defeat a login wall, DRM, CAPTCHA, rate limit or technical access restriction. A successful download does not establish that model training is permitted.

### Instaloader

Use normal public shortcode/profile/hashtag operations. Hashtag and some post metadata operations may require the user's own Instaloader session. Session files must stay local and must be created through Instaloader's documented login flow. Never put an account password in command-line arguments or commits. If Instagram requires a challenge, blocks access or rate-limits requests, stop/skip and try later within ordinary tool behaviour.

### DDGS and gallery-dl

DDGS returns public search-engine-indexed links, not a complete Instagram catalogue. gallery-dl is an optional alternate extractor. Neither changes the source site's terms or grants rights to media.

## No bypass behaviour

The system must not:
- extract cookies from a browser or another person's account;
- bypass login/challenge/CAPTCHA walls;
- rotate proxies or identities to evade platform rate limits;
- circumvent DRM or technical restrictions;
- scrape private/restricted content;
- claim that a downloader's supported-site list grants model-training rights.

A failed/restricted item is recorded as unavailable, not forcibly acquired.

## Data minimization and local security

- Store only metadata necessary for discovery, deduplication and research tasks.
- Keep SQLite, MP4 files, sidecar metadata, reports, sessions, rights manifests, access credentials and consent documents outside Git.
- Set restrictive file permissions for session files and rights manifests.
- Encrypt backups containing media or creator information.
- Use pseudonymous creator grouping in training/evaluation outputs where feasible.
- Do not identify people in media or infer sensitive attributes from appearance/voice.
- Apply additional safeguards for minors; exclude items without adequate permission and safeguards.
- Support deletion of media and derived artifacts when a grant expires or is revoked, and document limits on removing information from already trained weights.

## Local persistence and source deduplication

SQLite stores source IDs/URLs and metadata snapshots locally so repeat runs avoid selecting the same item. SHA-256 catches exact byte-identical downloaded files across platforms. A hash does not detect visual equivalence after re-encoding; a later perceptual dedup phase is needed. Do not publish the DB or media files.

## References

- yt-dlp: https://github.com/yt-dlp/yt-dlp
- Instaloader: https://github.com/instaloader/instaloader
- Instaloader troubleshooting/session and rate controller: https://instaloader.github.io/troubleshooting.html
- DDGS: https://github.com/deedy5/ddgs
- gallery-dl: https://github.com/mikf/gallery-dl and https://codeberg.org/mikf/gallery-dl
- YouTube policy for contextual review: https://developers.google.com/youtube/terms/developer-policies
- Instagram terms: https://help.instagram.com/581066165581870

This document is engineering guidance, not legal advice. Have appropriate counsel review bulk acquisition, commercial training and model distribution.
