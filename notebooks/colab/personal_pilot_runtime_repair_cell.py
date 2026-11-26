# ================================================================
# SHORTSLM — COLAB RUNTIME REPAIR + RESUME CELL
# Fixes:
#   1) PyAV metadata_errors incompatibility in faster-whisper
#   2) Missing PaddlePaddle runtime behind PaddleOCR
#   3) Unexpected OCR errors aborting the complete video report
#
# Paste this after the existing setup cells and process_one() definition.
# It requires: PROJECT_DIR, process_one, source_urls, ITEM_BY_URL,
#              read_lines, write_lines_atomic, append_jsonl,
#              atomic_json, COMPLETED_FILE, REMAINING_FILE, FAILED_LOG,
#              PUSH_LOG, FEATURES_DIR, and GitHub helper definitions.
# ================================================================

import os
import sys
import time
import json
import shutil
import subprocess
import importlib
from pathlib import Path
from datetime import datetime, timezone

REPO_BRANCH = "fix/colab-asr-paddle-runtime"

if not Path(PROJECT_DIR).exists():
    raise RuntimeError(
        f"ShortsLM checkout is missing: {PROJECT_DIR}. "
        "Run the notebook repository setup cell first."
    )

# ------------------------------------------------
# 1. Switch existing Colab checkout to the repaired branch
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

# Reinstall repository extras from the checked-out, patched source.
subprocess.run(
    [
        sys.executable, "-m", "pip", "install", "-q", "-e",
        ".[audio,ocr,discovery,legacy-discovery,instagram-fallback]",
    ],
    cwd=PROJECT_DIR,
    check=True,
)

# PyAV 19 removed av.open(metadata_errors=...), which the installed
# faster-whisper path still calls. Force a compatible PyAV release.
subprocess.run(
    [
        sys.executable, "-m", "pip", "install", "-q",
        "--force-reinstall", "--no-deps", "av>=11,<19",
    ],
    check=True,
)

import av
AV_VERSION = av.__version__
if int(AV_VERSION.split(".")[0]) >= 19:
    raise RuntimeError(
        f"PyAV {AV_VERSION} is incompatible. Expected av>=11,<19."
    )
print("PyAV compatibility verified:", AV_VERSION)

# ------------------------------------------------
# 2. Install and verify PaddlePaddle for PaddleOCR
# ------------------------------------------------

os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

paddle_install = subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q", "--upgrade", "paddlepaddle==3.2.0", "-i", "https://www.paddlepaddle.org.cn/packages/stable/cpu/"],
    capture_output=True,
    text=True,
    check=False,
)

if paddle_install.returncode != 0:
    print("PaddlePaddle install output:")
    print((paddle_install.stderr or paddle_install.stdout)[-1800:])

PADDLE_READY = False
PADDLE_VERSION = None
PADDLE_DEVICE = "unavailable"

try:
    import paddle
    paddle.utils.run_check()
    PADDLE_VERSION = paddle.__version__
    PADDLE_READY = True
    PADDLE_DEVICE = "GPU" if paddle.is_compiled_with_cuda() else "CPU"
except Exception as exc:
    print(
        "PaddlePaddle verification failed:",
        type(exc).__name__,
        str(exc)[:900],
    )

ENABLE_OCR = PADDLE_READY
print("PaddlePaddle:", PADDLE_VERSION or "unavailable")
print("Paddle device:", PADDLE_DEVICE)
print("OCR enabled:", ENABLE_OCR)

# ------------------------------------------------
# 3. Reload patched analyzer modules after checkout/install
# ------------------------------------------------

SRC_DIR = Path(PROJECT_DIR) / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import shorts_intelligence.config as config_module
importlib.reload(config_module)

import shorts_intelligence.telemetry.asr as asr_module
importlib.reload(asr_module)

import shorts_intelligence.telemetry.ocr as ocr_module
importlib.reload(ocr_module)

import shorts_intelligence.discovery.downloader as downloader_module
importlib.reload(downloader_module)

import shorts_intelligence.analyzer as analyzer_module
importlib.reload(analyzer_module)

from shorts_intelligence.discovery.models import DiscoveredCandidate
from shorts_intelligence.discovery.downloader import download_candidate, DownloadError
from shorts_intelligence.config import AnalyzerConfig

# process_one() resolves these globals when it executes; rebinding them
# updates the existing notebook function without redefining process_one().
analyze_video = analyzer_module.analyze_video

ASR_MODEL = globals().get("ASR_MODEL", "small")
ASR_DEVICE = "cuda" if (
    "torch" in sys.modules and sys.modules["torch"].cuda.is_available()
) else "cpu"

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
    enable_ocr=ENABLE_OCR,
    enable_audio_analysis=True,
    keep_artifacts=False,
)

# ------------------------------------------------
# 4. Replace notebook-only downloader with repository adapter
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

    # No Instagram session username/file and no YouTube cookie file.
    media_path = download_candidate(candidate, output_dir)
    media_path = Path(media_path).resolve(strict=True)

    if not media_path.is_file() or media_path.stat().st_size <= 0:
        raise DownloadError("Downloader returned an empty or missing media file.")

    return media_path


# ------------------------------------------------
# 5. Resume sequential processing from persistent ledger
# ------------------------------------------------

SESSION_STARTED = time.monotonic()
SESSION_BUDGET_SECONDS = globals().get(
    "SESSION_BUDGET_SECONDS", 4 * 60 * 60 + 30 * 60
)

successes = 0
failures = 0
completed_set = set(read_lines(COMPLETED_FILE))
queue = [
    url for url in source_urls
    if url not in completed_set
]
write_lines_atomic(REMAINING_FILE, queue)

print("=" * 70)
print("SHORTSLM RUNTIME REPAIR VERIFIED")
print("=" * 70)
print("Repository branch:", REPO_BRANCH)
print("PyAV:", AV_VERSION)
print("PaddlePaddle:", PADDLE_VERSION or "unavailable")
print("ASR:", ASR_MODEL, "| device:", ASR_DEVICE)
print("OCR:", "enabled" if ENABLE_OCR else "disabled; runtime unavailable")
print("URLs to process:", f"{len(queue):,}")
print("=" * 70)

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

            # Feature report is saved locally before GitHub commit.
            feature_file = Path(result["local_json"])
            payload = json.loads(feature_file.read_text(encoding="utf-8"))
            stages = payload.get("analysis", {}).get("stages", {})
            failed_stages = [
                name for name, stage in stages.items()
                if isinstance(stage, dict) and stage.get("status") == "failed"
            ]
            if failed_stages:
                print("Partial feature record; failed stages:", failed_stages)

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
            print("URL remains in remaining.txt.")
            print("Stopping to avoid repeated requests.")
            write_lines_atomic(REMAINING_FILE, queue)
            break

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
