# Data Acquisition, Rights and Governance

## Core principle

A public URL, view count, API response, Creative Commons label or successful downloader request does not by itself grant every right needed for media retrieval, temporary processing, derived-artifact retention, model training or redistribution.

This is engineering policy, not legal advice. Obtain legal review before large-scale collection, commercial use or model release.

## Separate capability scopes

Every item/source needs independent capabilities for:
- metadata read;
- source-identifier/permalink retention;
- media retrieval/download;
- media analysis;
- temporary processing;
- raw media retention;
- derived-artifact retention;
- model training;
- public redistribution.

Store evidence reference, permission version, granting party, applicable rights-holder coverage, expiry, revocation and provider delivery terms. Include music, performers, stock footage, overlays, embedded broadcasts and other third-party rights.

## YouTube

### Data API

Use the documented YouTube Data API for search and metadata within its quotas and policies. Current default quota docs describe 100 calls/day for `search.list` and 10,000 units/day for other standard methods; check the project's Google Cloud Console and current quota guide.

The developer policy says API clients must not download, import, back up, cache or store copies of YouTube audiovisual content without YouTube's prior written approval. It also restricts scraping YouTube applications. A Data API result or video URL is not a media download licence.

For non-authorized API data, policy generally permits temporary storage for no longer than 30 calendar days. There is an amended policy for audited developers who have explicitly applied for and accepted permission for additional analytics/derived metrics: specified statistical data and accepted derived metrics may be stored up to 36 months. Other fields, including titles, creator names and descriptions, still follow 30-day refresh/deletion policy. Derived metrics are disabled in this project until the required use-case approval is documented.

The standard policy restricts API-data aggregation/derived metrics. The June 2026 additional-metrics policy allows specific analytics cases (some scores, categorization and leaderboards) subject to amendment and its rules. Do not assume it allows every cross-channel dataset, multimodal model-training use or cross-platform score. Keep YouTube metrics separate from Instagram metrics and review the exact analytics use before enabling creator-normalized scoring.

### Third-party AI training opt-in

YouTube offers a creator/rightsholder option to let selected third-party companies train AI models using eligible public content. The setting is off by default. All applicable rights holders must consent; creators can select companies from a list. YouTube says video training eligibility is exposed by video ID through the Data API and that it may share eligible content with the selected company.

Companies wanting to be listed can apply. This is a potential authorized acquisition route, but the project must be accepted, creators/rightsholders must opt in, and actual delivery terms must be confirmed. It is not a general public video-download endpoint.

## Instagram / Meta

### Instagram Graph API

Instagram Media endpoint documentation says media endpoints return media owned by professional accounts and do not return media owned by personal accounts. Business Discovery works with eligible public Business/Creator accounts whose usernames are known. Reel `view_count` is available via Business Discovery, but may include paid/cross-posted activity as described by Meta. `media_url` may be omitted for copyrighted/flagged content.

The standard Graph API is not a universal search/download index for arbitrary public Reels. Hashtag search is narrower and must not be assumed to return the Business Discovery view-count field. Follow app review, token, permissions, rate limits and API-data-use policies.

### Meta Content Library

Meta Content Library/API is a controlled research environment for eligible researchers affiliated with qualified academic or not-for-profit research institutions. It supports analysis/search of public Instagram content, including Reels, under applicable research terms.

Meta says downloading data from the Content Library API is not permitted, including from its Secure Research Environment. The web UI has a separate downloadable subset for approved researchers under additional conditions; this is not a general API media-download or raw-video training feed. Do not automate exports beyond the approved interface/agreement.

## Other acquisition sources

Preferred sources for trainable media:
1. project-owned videos where music and third-party rights are controlled;
2. creator-uploaded original files with clear consent;
3. creator-authorized cloud-drive delivery or signed upload;
4. licensed dataset/vendor feeds with explicit media-analysis and ML-training rights;
5. platform-provided sharing under an accepted program/contract.

For open datasets, verify item-level license, attribution, NC/ND restrictions, original platform terms, privacy and removal obligations. A public dataset repository does not itself imply commercial training or redistribution permission.

## Browser automation and downloaders

Playwright/browser automation may be used for approved UI tasks, such as navigating a permitted research interface or a creator-authorized workflow. It must not scrape platform pages, bypass login/rate limits/CAPTCHAs/robots/DRM/technical protections, use cookies to evade restrictions, or bulk-copy arbitrary media.

yt-dlp and similar tools are media transport software. Their ability to parse a URL does not grant download or training permission. Keep them out of default public-platform ingestion. A downloader may be considered only where written source terms explicitly permit that method/item.

Deleting a downloaded file after feature extraction does not make an unauthorized download/training use compliant.

## Retention and deletion

Every provider field has a source-specific retention class and expiry/refresh time. SQLite must run retention jobs automatically. Store metric definition and timestamp. Support refresh before expiry, deletion when expiry/revocation/provider policy requires it, invalidation of derived artifacts and training-set membership, and documented limitations on machine unlearning.

A one-way hash of a source identifier is not presumed exempt from retention rules. Durable deduplication is allowed only where the source agreement permits retaining the identifier/fingerprint.

## Privacy and safety

- Avoid identity recognition of ordinary people in footage.
- Do not infer sensitive traits from appearance or voice.
- Minimize usernames, faces, voices, location and other personal data.
- Add special handling for minors and sensitive content; exclude when rights/safeguards are inadequate.
- Do not publish private analytics, raw transcripts or identifiable derived artifacts.
- Use local secrets/env files, encryption and access controls for private source material.
- Keep API credentials, browser cookies, consent evidence and media out of Git.

## Public repository rules

Never commit raw media/audio, private SQLite DBs, private analytics, consent documents, creator identifiers, access tokens/cookies, transcripts or derived content whose license forbids redistribution. Publish code, synthetic fixtures, schemas, documentation and permissible aggregate reports only.

## References

- YouTube API Developer Policies: https://developers.google.com/youtube/terms/developer-policies
- YouTube quota and compliance audits: https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits
- YouTube additional derived metrics and storage: https://developers.google.com/youtube/terms/derived-metrics-policy
- YouTube third-party AI training controls: https://support.google.com/youtube/answer/15509945
- YouTube three-minute Shorts eligibility: https://support.google.com/youtube/answer/15424877
- Instagram Media endpoint: https://developers.facebook.com/docs/instagram-platform/reference/instagram-media/
- Instagram Business Discovery / IG User: https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/
- Instagram Graph API rate limits: https://developers.facebook.com/docs/graph-api/overview/rate-limiting/
- Meta Content Library API overview: https://developers.facebook.com/docs/content-library-and-api/content-library-api/overview
- Meta Content Library access: https://developers.facebook.com/docs/content-library-and-api/get-access

Re-check terms, access programs, API versions and retention rules before each acquisition release.
