# ShortsLM full-catalogue collection: rights manifest

The `phase4 run-all` command may discover public metadata for catalogue candidates, but it will download and analyze a video only when its exact platform/source ID has a current grant in a local JSONL rights manifest.

Default local path: `data/private/rights-manifest.jsonl`. Keep this file and all underlying evidence private; do not commit them.

Each non-empty line must be one JSON object with:

- `platform`: `instagram` or `youtube`
- Exactly one of `source_id` or `creator_id`:
  - `source_id`: exact Instagram Reel shortcode or YouTube video ID
  - `creator_id`: exact Instagram username (without `@`) or stable YouTube channel ID; authorizes all discovered items attributed to that creator
- `media_retrieval`: `true`
- `media_analysis`: `true`
- `temporary_processing`: `true`
- `derived_artifact_retention`: `true`
- `model_training`: `true`
- `evidence_ref`: private evidence reference (for example, a consent record ID or licensed-dataset record)
- `expires_at`: timezone-aware ISO-8601 timestamp in the future
- `revoked`: `false`

Example schema only (replace every placeholder with a real grant; do not use this example as evidence):

```json
{
  "platform": "instagram",
  "source_id": "REAL_REEL_SHORTCODE",
  "media_retrieval": true,
  "media_analysis": true,
  "temporary_processing": true,
  "derived_artifact_retention": true,
  "model_training": true,
  "evidence_ref": "PRIVATE_CONSENT_OR_LICENSE_RECORD",
  "expires_at": "2027-12-31T23:59:59+00:00",
  "revoked": false
}
```

The command supports exact-item grants and creator-scope grants. Creator-scope grants must correspond to explicit permission covering the creator's videos and all listed scopes; do not infer creator permission from a public profile or follow relationship. A public profile, a public Reel URL, a creator-list entry, a dataset compilation licence, or a successful extractor response is not itself permission to retrieve, retain, analyze, or train on the underlying video. The evidence reference is an audit pointer; ShortsLM does not independently authenticate the consent or licence.

If you do not have item-specific permission, leave that item out. It can remain in the discovery metadata inventory, but its MP4 will not be acquired or processed. Do not fabricate grants or evidence references.

For example, create the private file locally in PowerShell:

```powershell
New-Item -ItemType Directory -Force data/private | Out-Null
notepad data/private/rights-manifest.jsonl
```

The feature manifest records the grant and expiry that authorized each processed item. The later Phase 4 release gate still requires human-reviewed annotations and validates the training permission fields.
