"""Local MP4 acquisition adapters for discovered candidates."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shorts_intelligence.discovery.models import DiscoveredCandidate


class DownloadError(RuntimeError):
    """A source-specific downloader could not produce a local MP4."""


def _is_access_or_transport_failure(error: BaseException) -> bool:
    """Avoid cascading extractor requests after an access denial or network outage."""
    message = str(error).casefold()
    markers = (
        "401 unauthorized", "403 forbidden", "429", "rate limit",
        "checkpoint", "login required", "challenge", "timed out", "timeout",
        "connection reset", "connection refused", "temporarily blocked",
    )
    return any(marker in message for marker in markers)


def _write_metadata(candidate: DiscoveredCandidate, path: Path) -> None:
    """Write a small source/download sidecar beside the MP4."""
    metadata_path = path.with_suffix(".metadata.json")
    payload = {
        "candidate": candidate.model_dump(mode="json"),
        "downloaded_at": datetime.now(UTC).isoformat(),
    }
    temporary = metadata_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    temporary.replace(metadata_path)


def _download_with_ytdlp(candidate: DiscoveredCandidate, output_dir: Path) -> Path:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise DownloadError('Install yt-dlp with: pip install -e ".[discovery]"') from exc

    options: dict[str, Any] = {
        "quiet": False,
        "noplaylist": True,
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "retries": 2,
        "fragment_retries": 2,
        "socket_timeout": 30,
        "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
    }
    # Prefer Node when available. Deno remains yt-dlp's default on machines
    # without Node, while this avoids the observed Deno challenge-runtime error.
    node_runtime = shutil.which("node")
    if node_runtime:
        options["js_runtimes"] = {"node": {"path": node_runtime}}

    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(str(candidate.canonical_url), download=True)
            if not isinstance(info, dict):
                raise DownloadError("yt-dlp returned no video information.")
            requested = info.get("requested_downloads") or []
            candidate_paths = [
                Path(item["filepath"]) for item in requested
                if isinstance(item, dict) and item.get("filepath")
            ]
            candidate_paths += [
                Path(ydl.prepare_filename(info)),
                output_dir / f"{candidate.source_id}.mp4",
            ]
    except DownloadError:
        raise
    except Exception as exc:
        raise DownloadError(f"yt-dlp failed for {candidate.canonical_url}: {exc}") from exc

    for path in candidate_paths:
        if path.exists() and path.suffix.lower() == ".mp4" and path.stat().st_size > 0:
            return path
        remuxed = path.with_suffix(".mp4")
        if remuxed.exists() and remuxed.stat().st_size > 0:
            return remuxed
    matches = sorted(output_dir.glob(f"{candidate.source_id}*.mp4"))
    if matches:
        return matches[0]
    raise DownloadError("yt-dlp finished but no MP4 file was found; check FFmpeg installation.")


def _download_instagram(
    candidate: DiscoveredCandidate,
    output_dir: Path,
    *,
    session_username: str | None,
    session_file: str | None,
) -> Path:
    try:
        import instaloader
    except ImportError as exc:
        raise DownloadError('Install Instaloader with: pip install -e ".[discovery]"') from exc

    # Isolate each post's download directory so the resulting video is unambiguous.
    with tempfile.TemporaryDirectory(prefix="shortslm_instagram_") as temp_dir:
        temp_root = Path(temp_dir)
        loader = instaloader.Instaloader(
            quiet=False,
            dirname_pattern=str(temp_root / "{target}"),
            filename_pattern="{shortcode}",
            download_pictures=False,
            download_videos=True,
            download_video_thumbnails=False,
            download_comments=False,
            save_metadata=False,
            post_metadata_txt_pattern="",
        )
        if session_username:
            loader.load_session_from_file(session_username, filename=session_file)
        try:
            post = instaloader.Post.from_shortcode(loader.context, candidate.source_id)
            if not post.is_video:
                raise DownloadError("Instagram item is not a video Reel.")
            loader.download_post(post, target=candidate.source_id)
        except DownloadError:
            raise
        except Exception as exc:
            raise DownloadError(f"Instaloader failed for {candidate.canonical_url}: {exc}") from exc

        videos = [p for p in temp_root.rglob("*") if p.is_file() and p.suffix.lower() == ".mp4"]
        if not videos:
            raise DownloadError(
                "Instaloader completed but did not produce an MP4. "
                "The item may be unavailable, restricted or unsupported."
            )
        source = max(videos, key=lambda p: p.stat().st_size)
        target = output_dir / f"instagram_{candidate.source_id}.mp4"
        shutil.copy2(source, target)
        return target


def _download_gallery_dl(candidate: DiscoveredCandidate, output_dir: Path) -> Path:
    """Secondary Instagram extractor using gallery-dl when Instaloader cannot resolve a Reel."""
    executable = shutil.which("gallery-dl")
    if executable is None:
        raise DownloadError("gallery-dl is not installed; install the instagram-fallback extra.")
    with tempfile.TemporaryDirectory(prefix="shortslm_gallerydl_") as temp_dir:
        result = subprocess.run(
            [executable, "-D", temp_dir, str(candidate.canonical_url)],
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "gallery-dl failed").strip()[-500:]
            raise DownloadError(detail)
        videos = [p for p in Path(temp_dir).rglob("*") if p.is_file() and p.suffix.lower() == ".mp4"]
        if not videos:
            raise DownloadError("gallery-dl completed but returned no MP4 file.")
        source = max(videos, key=lambda p: p.stat().st_size)
        target = output_dir / f"instagram_{candidate.source_id}.mp4"
        shutil.copy2(source, target)
        return target


def download_candidate(
    candidate: DiscoveredCandidate,
    output_dir: Path,
    *,
    instagram_session_username: str | None = None,
    instagram_session_file: str | None = None,
) -> Path:
    """Download a discovered video with the configured public-media extractor."""
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if candidate.platform == "youtube":
        media_path = _download_with_ytdlp(candidate, output_dir)
    else:
        try:
            media_path = _download_instagram(
                candidate,
                output_dir,
                session_username=instagram_session_username,
                session_file=instagram_session_file,
            )
        except DownloadError as instaloader_error:
            # Do not cascade more extractors after access denials or network outages.
            if _is_access_or_transport_failure(instaloader_error):
                raise DownloadError(
                    f"Instagram access/transport failure; stopped fallback attempts: {instaloader_error}"
                ) from instaloader_error
            try:
                media_path = _download_with_ytdlp(candidate, output_dir)
            except DownloadError as ytdlp_error:
                if _is_access_or_transport_failure(ytdlp_error):
                    raise DownloadError(
                        f"Instagram access/transport failure; stopped fallback attempts: {ytdlp_error}"
                    ) from ytdlp_error
                try:
                    media_path = _download_gallery_dl(candidate, output_dir)
                except (DownloadError, subprocess.TimeoutExpired) as gallery_error:
                    raise DownloadError(
                        "Instagram download attempts failed: "
                        f"Instaloader ({instaloader_error}); yt-dlp ({ytdlp_error}); "
                        f"gallery-dl ({gallery_error})."
                    ) from gallery_error
    if not media_path.exists() or media_path.stat().st_size == 0:
        raise DownloadError("Downloaded media file is empty or missing.")
    _write_metadata(candidate, media_path)
    return media_path
