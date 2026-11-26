# ================================================================
# SHORTSLM REPOSITORY-NATIVE ANONYMOUS DOWNLOADER
# ================================================================

from pathlib import Path
from shorts_intelligence.discovery import downloader as _shorts_downloader
from shorts_intelligence.discovery.downloader import download_candidate, DownloadError
from shorts_intelligence.discovery.models import DiscoveredCandidate

# Plain anonymous Instaloader "login required" may try the other
# standard adapters; explicit blocks and rate limits stop fallbacks.
def _anonymous_hard_block(error):
    message = str(error).casefold()
    markers = (
        "401", "403", "429", "rate limit", "too many requests",
        "checkpoint", "challenge_required", "challenge required",
        "challenge page", "sign in to confirm", "not a bot",
        "temporarily blocked", "timed out", "timeout",
        "connection reset", "connection refused",
    )
    return any(marker in message for marker in markers)

_shorts_downloader._is_access_or_transport_failure = _anonymous_hard_block

def download_video(item, output_dir):
    """Use the repository downloader anonymously without login/session/cookies."""
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
    print(f"ShortsLM downloader | {candidate.platform} | {candidate.source_id}")
    # No instagram_session_username, instagram_session_file or cookiefile.
    media_path = download_candidate(candidate, output_dir)
    media_path = Path(media_path).resolve(strict=True)
    if not media_path.is_file() or media_path.stat().st_size <= 0:
        raise DownloadError("Repository downloader returned an empty or missing file.")
    print("Download successful:", media_path.name,
          "|", round(media_path.stat().st_size / (1024 * 1024), 2), "MB")
    return media_path

print("Anonymous repository-native downloader ready.")
print("No Instagram session or YouTube cookie required.")

# ================================================================
# SHORTSLM PERSONAL FEATURE EXTRACTION — RESUMABLE RUNNER
# ================================================================

successes = 0
failures = 0
completed_set = set(read_lines(COMPLETED_FILE))
queue = [url for url in source_urls if url not in completed_set]
write_lines_atomic(REMAINING_FILE, queue)

print("=" * 70)
print("SHORTSLM PERSONAL FEATURE EXTRACTION")
print("=" * 70)
print("Source URLs:", f"{len(source_urls):,}")
print("Already completed:", f"{len(completed_set):,}")
print("To process:", f"{len(queue):,}")
print("Downloader: ShortsLM repository-native")
print("Authentication: anonymous; no sessions or cookies")
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
            print("URL remains in remaining.txt. Stopping to avoid repeated requests.")
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
