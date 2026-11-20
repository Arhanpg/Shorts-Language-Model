# Revised Phase 2 — Rights-Gated Automatic Media Delivery

**Status:** design only; no universal public-platform downloader is implemented.

## Objective

Take newly discovered, deduplicated candidates from revised Phase 1 and automatically acquire the video only when the source provides a documented authorized delivery route for media analysis and model training.

The project owner should not manually download MP4s. The acquisition worker should use platform-approved sharing, creator-authorized uploads/cloud-drive handoff, or licensed dataset/provider feeds. If a candidate has metadata permission but no media delivery right, it remains metadata-only and the worker must not try another route to force a download.

## Inputs

- normalized candidate from source_items;
- current 1M+ metric snapshot and observation timestamp;
- confirmed/candidate short-format status;
- rights record and source delivery contract;
- provider adapter and credential reference;
- source-specific retention/storage policy.

## State machine

    DISCOVERED
        |
        v
    METADATA_ELIGIBLE
        |
        v
    RIGHTS_CHECK
      /       \
    deny      allow
     |          |
     v          v
    METADATA   DELIVERY_QUEUED
    _ONLY          |
                   v
           PROVIDER_DELIVERY
             /          \
           fail         success
            |              |
            v              v
         RETRY/       CHECKSUM + FILE
         DEFERRED       VALIDATION
                            |
                            v
                      TRAINING_SCOPE
                        /       \
                     deny       allow
                      |            |
                      v            v
                  ANALYSIS_ONLY  TRAINING_READY

## Provider adapters

### YouTube platform training share

- Disabled until the project/company is accepted into YouTube's third-party AI-training program and provider delivery is documented.
- Verify the video ID's third-party training state and applicable rightsholder conditions.
- Consume content through the approved handoff only.
- Do not call yt-dlp or browser download as a fallback.
- Record contract, permission version, item ID, delivery timestamp, checksum and retention rules.

### Creator-authorized media inbox

- Provide signed upload endpoint or approved cloud-drive connector.
- Creators connect their account or deliver original assets; the project owner does not have to manually source/download each video.
- Require explicit media-analysis, temporary-processing and training scopes, including music/rightsholder status.
- Use resumable upload and checksum verification.
- Support withdrawal, expiry, deletion and dataset invalidation.

### Licensed dataset/vendor

- Load provider item manifest and rights terms.
- Fetch only items explicitly covered by the license.
- Record attribution, license version, NC/ND restrictions, takedown and retention rules.
- Do not infer that a public dataset page grants rights beyond the item-level license.

### Instagram and Meta

- Instagram Business Discovery can discover/describe eligible public professional-account media, but it does not make every public Reel downloadable for training.
- Meta Content Library/API is a controlled research environment and does not provide API media downloads.
- Enable an Instagram media-delivery provider only after Meta or creator/license provider documents the permitted file-delivery method and ML-training scope.

## Asset validation

After authorized delivery, verify:
- local/object storage path belongs to private asset root;
- expected media type/container and non-zero file size;
- duration/resolution limits;
- successful FFprobe;
- SHA-256 checksum;
- source ID/content fingerprint consistency;
- rights scope remains valid and unexpired;
- duplicate byte content and perceptual near-duplicates;
- malware/file-integrity checks where required.

## Retention

- Raw media duration follows the specific rights contract.
- Temporary processing may delete source media after telemetry is committed only if agreement and retention policy permit it.
- Derived frame/audio/transcript retention and model-training use are separate rights.
- Revocation/expiry blocks future processing and starts deletion/invalidation workflow.

## Phase 2 exit criteria

1. At least one authorized media provider is operational end-to-end.
2. All acquired assets have complete provenance and permission evidence.
3. Missing media permission causes a hard block; there is no downloader fallback.
4. Retry/resume and partial-failure handling work.
5. Duplicate files and repeated source IDs are handled according to retention rules.
6. No raw media, credentials or local database are published to GitHub.
7. System reports separate counts for discovered candidates, metadata-qualified candidates, acquisition-authorized assets and training-authorized assets.

A completed discovery job does not mean media acquisition is complete. If there is no approved delivery mechanism, this phase remains blocked for that provider.
