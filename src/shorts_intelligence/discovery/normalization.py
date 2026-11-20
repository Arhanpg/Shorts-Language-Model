"""Canonical URL, metadata and hashtag normalization helpers."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

from shorts_intelligence.discovery.models import DiscoveredCandidate

_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_INSTAGRAM_PATH_RE = re.compile(r"/(?:reel|reels|p)/([A-Za-z0-9_-]+)/?")
_HASHTAG_RE = re.compile(r"(?<!\\w)#([\\w]+)", re.UNICODE)


def youtube_id_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    candidate: str | None = None
    if host in {"youtu.be", "www.youtu.be"}:
        candidate = parsed.path.strip("/").split("/")[0]
    elif host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [None])[0]
        else:
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) >= 2 and parts[0] in {"shorts", "live", "embed"}:
                candidate = parts[1]
    return candidate if candidate and _YOUTUBE_ID_RE.fullmatch(candidate) else None


def canonical_youtube_url(url: str, video_id: str | None = None) -> str:
    resolved_id = video_id or youtube_id_from_url(url)
    if not resolved_id or not _YOUTUBE_ID_RE.fullmatch(resolved_id):
        raise ValueError(f"Not a recognized YouTube video URL or ID: {url}")
    parsed = urlparse(url)
    if "/shorts/" in parsed.path:
        return f"https://www.youtube.com/shorts/{resolved_id}"
    return f"https://www.youtube.com/watch?v={resolved_id}"


def instagram_shortcode_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc.lower().removeprefix("www.") not in {"instagram.com", "m.instagram.com"}:
        return None
    match = _INSTAGRAM_PATH_RE.search(parsed.path)
    return match.group(1) if match else None


def canonical_instagram_url(url: str) -> str:
    shortcode = instagram_shortcode_from_url(url)
    if not shortcode:
        raise ValueError(f"Not a recognized Instagram Reel/post URL: {url}")
    parsed = urlparse(url)
    kind = "reel" if "/reel/" in parsed.path or "/reels/" in parsed.path else "p"
    return f"https://www.instagram.com/{kind}/{shortcode}/"


def extract_hashtags(*texts: str | None) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for text in texts:
        if not text:
            continue
        for match in _HASHTAG_RE.findall(text):
            tag = match.casefold()
            if tag not in seen:
                seen.add(tag)
                found.append(tag)
    return found


def candidate_from_ytdlp(info: dict[str, object]) -> DiscoveredCandidate | None:
    video_id = str(info.get("id") or "")
    webpage_url = str(info.get("webpage_url") or info.get("original_url") or "")
    if not video_id and webpage_url:
        video_id = youtube_id_from_url(webpage_url) or ""
    if not video_id or not _YOUTUBE_ID_RE.fullmatch(video_id):
        return None
    duration_raw = info.get("duration")
    duration = float(duration_raw) if isinstance(duration_raw, (int, float)) and duration_raw > 0 else None
    upload_date = str(info.get("upload_date") or "") or None
    if "/shorts/" in webpage_url:
        format_status = "confirmed"
        canonical = canonical_youtube_url(webpage_url, video_id)
    elif duration is not None and duration <= 180 and (not upload_date or upload_date >= "20241015"):
        format_status = "candidate"
        canonical = canonical_youtube_url(webpage_url or f"https://www.youtube.com/watch?v={video_id}", video_id)
    else:
        format_status = "not_short"
        canonical = canonical_youtube_url(webpage_url or f"https://www.youtube.com/watch?v={video_id}", video_id)
    view_count_raw = info.get("view_count")
    view_count = int(view_count_raw) if isinstance(view_count_raw, (int, float)) and view_count_raw >= 0 else None
    title = str(info.get("title") or "") or None
    description = str(info.get("description") or "") or None
    tags_raw = info.get("tags")
    tags = [str(item).lstrip("#").casefold() for item in tags_raw] if isinstance(tags_raw, list) else []
    hashtags = list(dict.fromkeys(tags + extract_hashtags(title, description)))
    return DiscoveredCandidate(
        platform="youtube", source_id=video_id, canonical_url=canonical,
        title=title, description=description, creator=str(info.get("channel") or info.get("uploader") or "") or None,
        view_count=view_count, metric_source="yt_dlp_view_count" if view_count is not None else None,
        duration_seconds=duration, upload_date=upload_date, hashtags=hashtags,
        short_format_status=format_status, discovered_at=datetime.now(UTC),
        metadata={key: info.get(key) for key in ("channel_id", "categories", "age_limit", "availability") if info.get(key) is not None},
    )


def candidate_from_instagram_url(url: str) -> DiscoveredCandidate:
    canonical = canonical_instagram_url(url)
    shortcode = instagram_shortcode_from_url(canonical)
    assert shortcode is not None
    return DiscoveredCandidate(
        platform="instagram", source_id=shortcode, canonical_url=canonical,
        short_format_status="confirmed", status="metric_unknown",
    )
