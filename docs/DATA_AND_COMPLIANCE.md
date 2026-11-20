# Data Acquisition, Rights and Governance

## Core principle

A public URL, view count, API metadata record, Creative Commons label or temporary download does not by itself grant every right needed for analysis, storage, derived-artifact retention, model training or redistribution. Each operation needs a permission basis appropriate to its source and jurisdiction.

This is engineering policy, not legal advice. Obtain legal review before large-scale collection, commercial use or model-weight release.

## Source tiers

| Source | Metadata | Media processing | Training | Redistribution |
|---|---|---|---|---|
| Project-owned media | Yes | Yes, subject to music/third-party rights | Yes, under recorded rights | Only if every component permits |
| Creator upload with permission | As consented | As consented | Only if separately explicit | Only if explicit |
| Licensed dataset | Per item/dataset terms | Per item/dataset terms | Per item/dataset terms | Per item and terms |
| Official YouTube API | In API policy scope | Not a media-download grant | Not a training grant | Not assumed |
| Meta Content Library API | Controlled research scope | API terms govern; API data download prohibited | Do not assume external model-training permission | Not permitted from API |
| User-supplied public link | Link can be stored only as permitted | Only through authorized access/rights | Only if rights allow | Not assumed |

### YouTube

YouTube API Services Developer Policies restrict downloading, importing, backing up, caching or storing copies of YouTube audiovisual content without prior written approval. They also restrict aggregation of API Data, with a narrow channel-content-owner exception. API metadata access is not a general-purpose audiovisual training license. Follow current API terms, quota and retention rules; do not build production around scraping or unofficial downloader workarounds.

YouTube's third-party AI-training opt-in is a potential route for eligible creator/rights-holder authorization, but remains subject to YouTube's process and applicable agreements. It is not a general bulk-download API.

### Instagram / Meta

Meta Content Library is controlled research access. Meta's API overview says downloading data through the API is not permitted. A separate downloadable subset in the UI has eligibility and approval conditions. Do not build a crawler for arbitrary public Reels. Use creator-submitted or separately licensed video files for media training unless approved access explicitly grants the required rights.

## Rights capability record

An illustrative source record should include a source ID/type, platform, source ID, rights record ID, creator group key, consent version/time, expiration, music-rights status and an explicit capability map for:
- metadata read;
- media analysis;
- temporary processing;
- raw retention;
- derived-artifact retention;
- model training;
- public redistribution.

Store consent proof outside the public repository. Capabilities must be enforced by code, not just documented.

## Media lifecycle

1. Register source and rights record.
2. Verify every required capability before fetching or processing.
3. Use isolated temporary storage with size, duration and codec limits.
4. Extract only artifacts permitted by the rights record.
5. Record tool versions, input checksums and output lineage.
6. Delete raw media according to applicable rights and retention contract.
7. On rights revocation, block new processing and run documented deletion/invalidation for affected files, feature records and training dataset membership. Model unlearning may not be technically guaranteed; disclose this limitation to contributors.

Deleting raw media after extraction does not make an otherwise unauthorized download or training use compliant.

## Privacy and safety

- Avoid identity recognition of ordinary people in footage.
- Do not infer sensitive traits from appearance or voice.
- Minimize and protect usernames, faces, voices, location and other personal data.
- Add special handling for minors and sensitive content; exclude when rights or safeguards are inadequate.
- Do not publish private analytics, raw transcripts or identifiable derived artifacts.
- Use encryption, access control, audit logs and defined deletion paths for private source material.
- Treat platform metrics as snapshots with timestamp and definition.

## Public repository rules

Never commit raw media/audio, private analytics, consent documents, identity data, access tokens, cookies, credentials or derived content whose license forbids redistribution. Publish schemas, code, synthetic fixtures, documented evaluation procedures and source references instead.

## References

- YouTube API Developer Policies: https://developers.google.com/youtube/terms/developer-policies
- YouTube quota and compliance audits: https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits
- YouTube third-party AI training controls: https://support.google.com/youtube/answer/15509945
- Meta Content Library: https://developers.facebook.com/docs/content-library-and-api/content-library
- Meta Content Library API overview: https://developers.facebook.com/docs/content-library-and-api/content-library-api/overview

Re-check source policy before each new acquisition program; platform terms and access programs can change.
