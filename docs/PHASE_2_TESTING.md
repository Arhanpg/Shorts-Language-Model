# Revised Phase 2 — Media Delivery Setup and Validation

## Before enabling a downloader

Do not install/run yt-dlp against arbitrary public YouTube or Instagram links as the first test. First record which authorized provider will deliver the media and which agreement permits that exact method.

## Local environment

Media-delivery workers and telemetry can run on the local Windows/WSL laptop initially. Use a private SSD staging area. The RTX 3050 is not required for source delivery, hashing, FFprobe or SQLite.

Cloud object storage may be introduced if creators/providers deliver large batches or local disk is insufficient. Use private buckets, signed URLs, expiry and deletion lifecycle rules.

## Provider onboarding checklist

For each provider, document:
- provider name and official documentation/contract URL;
- application/app-review status;
- credentials/scopes required;
- rate limits and quota;
- candidate discovery capability;
- whether media retrieval is explicitly permitted;
- whether model training is explicitly permitted;
- raw/derived-data retention;
- music and third-party rights requirements;
- attribution, withdrawal, takedown and deletion procedure.

If any required field is unknown, provider remains disabled or metadata-only.

## Validation tests for an authorized provider

1. Register one test candidate.
2. Verify its rights capability map and permission expiry.
3. Execute the provider's documented media handoff.
4. Confirm the asset arrives in the private media root.
5. Run FFprobe and verify duration, dimensions, codec and audio presence.
6. Compute SHA-256 and compare with provider metadata if supplied.
7. Repeat the same delivery and verify duplicate detection.
8. Change permission to revoked/expired and verify new delivery/processing is blocked.
9. Test network interruption/resume without duplicate files.
10. Verify raw and derived artifacts follow retention policy after deletion/withdrawal.
11. Confirm SQLite DB, credentials, media and logs remain ignored by Git.
12. Confirm a metadata-only candidate cannot enter media processing.

## No-provider behavior

When a source has no approved media provider:
- discovery may continue if metadata access is permitted;
- candidate remains metadata_only or delivery_unavailable;
- run report explains the blocker;
- no downloader fallback is attempted;
- processing continues for other sources with authorized media.

## Batch test

Once one provider passes the single-item test, run a 10-item authorized batch, then 50, then 100. Measure actual delivery success, latency, volume, duplicate rate, failed jobs and storage. Do not infer capacity from a mock run.

## CLI design target (not implemented yet)

    shorts-lm acquisition status
    shorts-lm acquisition validate --candidate-id LOCAL_ID
    shorts-lm acquisition run --provider creator_media_inbox --limit 10
    shorts-lm acquisition report --run-id RUN_ID

The actual provider/options will be fixed only after a source with a real authorized handoff has been selected.
