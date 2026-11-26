# ================================================================
# SHORTSLM — COLAB PADDLE OCR REPAIR + RESUME
#
# Paste this after the notebook has defined:
#   PROJECT_DIR, source_urls, ITEM_BY_URL, read_lines,
#   write_lines_atomic, append_jsonl, atomic_json,
#   COMPLETED_FILE, REMAINING_FILE, FAILED_LOG, PUSH_LOG,
#   FEATURES_DIR, GITHUB_REPO, GITHUB_BRANCH,
#   GITHUB_FEATURES_PREFIX, GH_API, GH_HEADERS,
#   github_commit_json, and Drive workspace paths.
#
# This cell repairs the runtime, preflights OCR, requeues previously
# pushed records whose OCR stage failed, and resumes the queue.
# ================================================================

import os
import sys
import time
import json
import shutil
import subprocess
import importlib
import tempfile
import re
from pathlib import Path
from datetime import datetime, timezone

REPO_BRANCH = "fix/colab-paddleocr-3-2-2-retry"

if not Path(PROJECT_DIR).exists():
    raise RuntimeError(
        f"ShortsLM checkout is missing: {PROJECT_DIR}. "
        "Run the notebook repository setup cell first."
    )

# ------------------------------------------------
# 1. Fetch patched ShortsLM source and reinstall dependencies
# ------------------------------------------------

subprocess.run(
    ["git", "fetch", "origin", REPO_BRANCH, "--depth", "1"],
    cwd=PROJECT_DIR,
    check=True,
)
subprocess.run(
    ["git", "checkout", "-B", REPO_BRANCH, "FETCH_HEAD"],
    cwd=PROJECT_DIR,
    check=True,
)

subprocess.run(
    [
        sys.executable, "-m", "pip", "install", "-q", "-e",
        ".[audio,ocr,discovery,legacy-discovery,instagram-fallback]",
    ],
    cwd=PROJECT_DIR,
    check=True,
)

# faster-whisper currently uses the av.open(metadata_errors=...) API.
subprocess.run(
    [
        sys.executable, "-m", "pip", "install", "-q",
        "--force-reinstall", "--no-deps", "av>=11,<19",
    ],
    check=True,
)

# PaddlePaddle 3.2.2 has CPython 3.13 Linux wheels and avoids the
# PaddlePaddle 3.3.0 CPU inference failure seen in the uploaded traceback.
subprocess.run(
    [
        sys.executable, "-m", "pip", "install", "-q",
        "--upgrade", "paddlepaddle==3.2.2",
    ],
    check=True,
)

import av
AV_VERSION = av.__version__
if int(AV_VERSION.split(".")[0]) >= 19:
    raise RuntimeError(f"PyAV {AV_VERSION} is incompatible; expected av<19.")
print("PyAV:", AV_VERSION)

import paddle
paddle.utils.run_check()
PADDLE_VERSION = paddle.__version__
if PADDLE_VERSION != "3.2.2":
    raise RuntimeError(
        f"Expected PaddlePaddle 3.2.2; found {PADDLE_VERSION}."
    )
print("PaddlePaddle:", PADDLE_VERSION)
print("Paddle CUDA build:", paddle.is_compiled_with_cuda())

os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

# ------------------------------------------------
# 2. Reload repository modules from patched source
# ------------------------------------------------

SRC_DIR = Path(PROJECT_DIR) / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import shorts_intelligence.telemetry.asr as asr_module
importlib.reload(asr_module)

import shorts_intelligence.telemetry.ocr as ocr_module
importlib.reload(ocr_module)

import shorts_intelligence.discovery.downloader as downloader_module
importlib.reload(downloader_module)

import shorts_intelligence.analyzer as analyzer_module
importlib.reload(analyzer_module)

from shorts_intelligence.config import AnalyzerConfig
from shorts_intelligence.discovery.models import DiscoveredCandidate
from shorts_intelligence.discovery.downloader import download_candidate, DownloadError
from shorts_intelligence.schemas import FrameEvidence

analyze_video = analyzer_module.analyze_video
run_ocr = ocr_module.run_ocr

# ------------------------------------------------
# 3. Configure analyzer and perform real OCR preflight
# ------------------------------------------------

import cv2
import numpy as np

ASR_MODEL = globals().get("ASR_MODEL", "small")
try:
    import torch
    ASR_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
except Exception:
    ASR_DEVICE = "cpu"

MAX_DURATION_SECONDS = globals().get("MAX_DURATION_SECONDS", 180.0)
MAX_FILE_SIZE_MB = globals().get("MAX_FILE_SIZE_MB", 1000)
MAX_KEYFRAMES = globals().get("MAX_KEYFRAMES", 24)
MAX_OCR_FRAMES = globals().get("MAX_OCR_FRAMES", 12)

ANALYZER_CONFIG = AnalyzerConfig(
    max_file_size_mb=MAX_FILE_SIZE_MB,
    max_duration_seconds=MAX_DURATION_SECONDS,
    max_keyframes=MAX_KEYFRAMES,
    max_ocr_frames=MAX_OCR_FRAMES,
    asr_model=ASR_MODEL,
    asr_device=ASR_DEVICE,
    asr_timeout_seconds=300,
    enable_asr=True,
    enable_ocr=True,
    enable_audio_analysis=True,
    keep_artifacts=False,
)

_preflight_image = np.full((180, 640, 3), 255, dtype=np.uint8)
cv2.putText(
    _preflight_image, "ShortsLM OCR preflight 123", (18, 100),
    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2, cv2.LINE_AA,
)
_preflight_evidence = FrameEvidence(
    timestamp_seconds=0.0,
    frame_index=0,
    reason=["ocr_preflight"],
    motion_score=0.0,
)

try:
    _preflight_spans, OCR_PREFLIGHT_ENGINE = run_ocr(
        [(_preflight_evidence, _preflight_image)],
        max_frames=1,
        prefer_gpu=False,
    )
except Exception as exc:
    raise RuntimeError(
        "PaddleOCR preflight failed. The URL queue was not started. "
        f"{type(exc).__name__}: {exc}"
    ) from exc

print(
    "OCR preflight PASSED:",
    OCR_PREFLIGHT_ENGINE,
    "| detected spans:",
    len(_preflight_spans),
)
print("ASR:", ASR_MODEL, "| device:", ASR_DEVICE)

# ------------------------------------------------
# 4. Use the repository anonymous downloader
# ------------------------------------------------

def download_video(item, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    candidate = DiscoveredCandidate(
        platform=item["platform"],
        source_id=item["source_id"],
        canonical_url=item["url"],
        short_format_status="unknown",
        status="metric_unknown",
        metadata={
            "source": "personal_url_txt",
            "download_mode": "anonymous",
            "authentication_session_supplied": False,
        },
    )

    print(
        f"ShortsLM downloader | {candidate.platform} | {candidate.source_id}"
    )
    media_path = download_candidate(candidate, output_dir)
    media_path = Path(media_path).resolve(strict=True)

    if not media_path.is_file() or media_path.stat().st_size <= 0:
        raise DownloadError("Downloader returned an empty or missing media file.")
    return media_path


# ------------------------------------------------
# 5. Rebuild process_one so failed OCR JSON is reprocessed
# ------------------------------------------------

def safe_id(value):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(value))[:120]


def process_one(item):
    platform = item["platform"]
    source_id = item["source_id"]
    url = item["url"]

    local_json = FEATURES_DIR / platform / f"{safe_id(source_id)}.json"
    github_path = (
        f"{GITHUB_FEATURES_PREFIX}/{platform}/{safe_id(source_id)}.json"
    )

    if local_json.exists():
        existing_payload = json.loads(
            local_json.read_text(encoding="utf-8")
        )
        ocr_status = (
            existing_payload.get("analysis", {})
            .get("stages", {})
            .get("ocr", {})
            .get("status")
        )
        if ocr_status == "failed":
            print("Existing record has failed OCR; reprocessing:", local_json)
            local_json.unlink()
        else:
            payload = existing_payload
            print("Reusing saved feature JSON:", local_json)

    if not local_json.exists():
        temp_dir = Path(tempfile.mkdtemp(
            prefix=f"shortslm_{platform}_{safe_id(source_id)}_"
        ))
        try:
            media_path = download_video(item, temp_dir)
            if media_path.stat().st_size > MAX_FILE_SIZE_MB * 1024 * 1024:
                raise RuntimeError(
                    f"Downloaded media exceeds {MAX_FILE_SIZE_MB} MB limit."
                )

            report = analyze_video(
                media_path,
                temp_dir / "analysis.json",
                config=ANALYZER_CONFIG,
            )

            payload = {
                "schema_version": "shortslm.personal-pilot.v2",
                "record_type": "short_video_feature_observation",
                "platform": platform,
                "source_id": source_id,
                "canonical_url": url,
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "pipeline": {
                    "repository": REPO_URL,
                    "repository_branch": REPO_BRANCH,
                    "asr_model": ASR_MODEL,
                    "asr_device": ASR_DEVICE,
                    "max_duration_seconds": MAX_DURATION_SECONDS,
                    "max_keyframes": MAX_KEYFRAMES,
                    "max_ocr_frames": MAX_OCR_FRAMES,
                    "analyzer_config": "repository AnalyzerConfig",
                },
                "analysis": report.model_dump(mode="json"),
            }
            atomic_json(local_json, payload)
            print("Feature JSON saved to Drive:", local_json)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            print("Temporary media directory removed.")

    commit_sha, html_url = github_commit_json(
        github_path,
        payload,
        f"Add ShortsLM personal features for {platform}:{source_id}",
    )

    return {
        "platform": platform,
        "source_id": source_id,
        "url": url,
        "local_json": str(local_json),
        "github_path": github_path,
        "commit_sha": commit_sha,
        "github_url": html_url,
    }


# ------------------------------------------------
# 6. Requeue completed records whose saved OCR failed
# ------------------------------------------------

SESSION_STARTED = time.monotonic()
SESSION_BUDGET_SECONDS = globals().get(
    "SESSION_BUDGET_SECONDS", 4 * 60 * 60 + 30 * 60
)

successes = 0
failures = 0
completed_set = set(read_lines(COMPLETED_FILE))
ocr_retry_urls = []

for candidate_url in source_urls:
    if candidate_url not in completed_set:
        continue
    candidate_item = ITEM_BY_URL.get(candidate_url)
    if not candidate_item:
        continue

    old_feature = (
        FEATURES_DIR
        / candidate_item["platform"]
        / f"{safe_id(candidate_item['source_id'])}.json"
    )
    if not old_feature.exists():
        continue

    try:
        old_payload = json.loads(old_feature.read_text(encoding="utf-8"))
        old_status = (
            old_payload.get("analysis", {})
            .get("stages", {})
            .get("ocr", {})
            .get("status")
        )
        if old_status == "failed":
            ocr_retry_urls.append(candidate_url)
    except (OSError, ValueError, TypeError):
        continue

completed_set.difference_update(ocr_retry_urls)
queue = [url for url in source_urls if url not in completed_set]
write_lines_atomic(COMPLETED_FILE, sorted(completed_set))
write_lines_atomic(REMAINING_FILE, queue)

print("=" * 70)
print("SHORTSLM PERSONAL FEATURE EXTRACTION")
print("=" * 70)
print("Source URLs:", f"{len(source_urls):,}")
print("Valid completed:", f"{len(completed_set):,}")
print("Previously completed with OCR failure; requeued:", f"{len(ocr_retry_urls):,}")
print("To process:", f"{len(queue):,}")
print("PyAV:", AV_VERSION, "| PaddlePaddle:", PADDLE_VERSION)
print("OCR preflight:", OCR_PREFLIGHT_ENGINE)
print("No artificial URL-count cap.")
print("=" * 70)

# ------------------------------------------------
# 7. Sequential, resumable runner
# ------------------------------------------------

try:
    while queue:
        if time.monotonic() - SESSION_STARTED >= SESSION_BUDGET_SECONDS:
            print("Colab safety time budget reached. Remaining URLs checkpointed.")
            break

        url = queue[0]
        item = ITEM_BY_URL.get(url)

        if item is None:
            failures += 1
            append_jsonl(FAILED_LOG, {
                "url": url,
                "error": "URL missing from ITEM_BY_URL",
                "at": datetime.now(timezone.utc).isoformat(),
            })
            queue.pop(0)
            write_lines_atomic(REMAINING_FILE, queue)
            continue

        print(
            f"\n[{len(completed_set) + 1}/{len(source_urls)}] "
            f"{item['platform']} | {item['source_id']} | remaining: {len(queue):,}"
        )

        try:
            result = process_one(item)

            feature_file = Path(result["local_json"])
            feature_payload = json.loads(
                feature_file.read_text(encoding="utf-8")
            )
            stages = feature_payload.get("analysis", {}).get("stages", {})
            failed_stages = [
                name for name, stage in stages.items()
                if isinstance(stage, dict) and stage.get("status") == "failed"
            ]
            if failed_stages:
                print("WARNING: partial feature record; failed stages:", failed_stages)

            completed_set.add(url)
            append_jsonl(PUSH_LOG, {
                **result,
                "pushed_at": datetime.now(timezone.utc).isoformat(),
            })

            queue.pop(0)
            write_lines_atomic(COMPLETED_FILE, sorted(completed_set))
            write_lines_atomic(REMAINING_FILE, queue)

            successes += 1
            print("PUSHED:", result["github_url"])
            print("COMMIT:", result["commit_sha"])

        except Exception as exc:
            failures += 1
            error_text = f"{type(exc).__name__}: {exc}"
            append_jsonl(FAILED_LOG, {
                "url": url,
                "platform": item["platform"],
                "source_id": item["source_id"],
                "error": error_text,
                "at": datetime.now(timezone.utc).isoformat(),
            })
            print("FAILED:", error_text[:1400])
            print("Current URL remains in remaining.txt.")
            write_lines_atomic(REMAINING_FILE, queue)
            break

except KeyboardInterrupt:
    print("\nManual interrupt received. Current URL remains checkpointed.")

finally:
    write_lines_atomic(COMPLETED_FILE, sorted(completed_set))
    write_lines_atomic(REMAINING_FILE, queue)

    print("\n" + "=" * 70)
    print("SESSION SUMMARY")
    print("=" * 70)
    print("Successful GitHub pushes:", successes)
    print("Failures:", failures)
    print("Completed total:", len(read_lines(COMPLETED_FILE)))
    print("Remaining total:", len(read_lines(REMAINING_FILE)))
    print("Completed file:", COMPLETED_FILE)
    print("Remaining file:", REMAINING_FILE)
    print("Failure log:", FAILED_LOG)
    print("GitHub push log:", PUSH_LOG)
    print("=" * 70)
