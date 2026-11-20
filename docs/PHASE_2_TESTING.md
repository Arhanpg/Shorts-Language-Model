# Phase 2 — Download and Acquisition Validation

## Environment

Use the Windows PowerShell environment on the local laptop. Install Python 3.11 and FFmpeg (ffmpeg.exe and ffprobe.exe on PATH). RTX 3050 is not needed for discovery, SQLite or file downloads.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,discovery,audio]"
pip install -e ".[instagram-fallback]"
shorts-lm doctor
```

The last optional gallery-dl install may be skipped if it is not needed.

## Phase 2 validation checklist

1. Create a private item-specific rights manifest for one YouTube test video and one creator-authorized Instagram Reel.
2. Verify that missing rights row blocks the item.
3. Verify incomplete, expired or revoked permissions block the item.
4. Download the authorized YouTube video with yt-dlp; check MP4 exists and is non-empty.
5. Download the Instagram Reel with Instaloader; force/test fallback adapters separately only where needed.
6. Run FFprobe; compare duration/dimensions/audio with expected metadata.
7. Confirm metadata/rights sidecar created beside the MP4.
8. Verify SHA-256 is stored in SQLite.
9. Replay download; already downloaded record is not queued again.
10. Register same bytes under another platform in a test DB; duplicate_media state must be set and redundant file removed.
11. Simulate provider/network failure; state is download_failed and is eligible for retry.
12. Confirm .shortslm DB, session files, rights manifest, MP4 and sidecar are gitignored.

## Commands

Discover 100 candidates:

```powershell
shorts-lm discover run --platform all --target-new 100 --min-views 1000000 --max-candidates 1500
```

Download permitted candidates:

```powershell
shorts-lm discover download --rights-manifest data/private/rights.jsonl --limit 25 --output-dir data/private/acquired
```

Process one authorized asset with existing analyzer:

```powershell
shorts-lm analyze --input data/private/acquired/VIDEO.mp4 --output outputs/analysis.json --rights-basis creator_permission --rights-reference PRIVATE_CONSENT_REFERENCE --training-permitted
```

## Acceptance criteria

- All download decisions are per-item and auditable.
- No metadata-only candidate silently downloads.
- Unknown view metric does not qualify as 1M+.
- A partial provider result is reported instead of forced through infinite retries.
- Failed extraction leaves a retryable state.
- SHA-256 prevents exact duplicate bytes from entering the telemetry queue twice.
- Test failures and CI status are reported honestly.
