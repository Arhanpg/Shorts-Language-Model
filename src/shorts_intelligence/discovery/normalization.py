"""Canonical URL, metadata and hashtag normalization helpers."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

from shorts_intelligence.discovery.models import DiscoveredCandidate

_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_INSTAGRAM_PATH_RE = re.compile(r"/(?:reel|reels|p)/([A-Za-z0-9_-]+)/?")
_HASHTAG_RE = re.compile(r"(?<!\w)#([\w]+)", re.UNICODE)


def youtube_id_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    candidate: str | None = None
    if host == "youtu.be":
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
    host = parsed.netloc.lower().removeprefix("www.")
    if host not in {"instagram.com", "m.instagram.com"}:
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


def _youtube_format_status(
    info: dict[str, object],
    *,
    duration: float | None,
    upload_date: str | None,
    webpage_url: str,
) -> str:
    if "/shorts/" in webpage_url:
        return "confirmed"
    if duration is None:
        return "unknown"

    # YouTube's standard-channel Shorts duration window changed on 15 Oct 2024.
    # When upload_date is missing, do not assume which duration rule applies.
    if not upload_date:
        if duration > 60.0:
            return "unknown"
        max_duration = 60.0
    elif upload_date >= "20241015":
        max_duration = 180.0
    else:
        max_duration = 60.0

    if duration > max_duration:
        return "not_short"

    width_raw, height_raw = info.get("width"), info.get("height")
    width = int(width_raw) if isinstance(width_raw, (int, float)) and width_raw > 0 else None
    height = int(height_raw) if isinstance(height_raw, (int, float)) and height_raw > 0 else None

    if width is not None and height is not None:
        if height < width:
            return "not_short"
        if upload_date and (upload_date >= "20241015" or duration <= 60.0):
            return "confirmed"
        return "candidate"

    # Missing dimensions mean short-form format cannot be confirmed from duration alone.
    return "candidate"


def candidate_from_ytdlp(info: dict[str, object]) -> DiscoveredCandidate | None:
    video_id = str(info.get("id") or "")
    webpage_url = str(info.get("webpage_url") or info.get("original_url") or "")
    if not video_id and webpage_url:
        video_id = youtube_id_from_url(webpage_url) or ""
    if not video_id or not _YOUTUBE_ID_RE.fullmatch(video_id):
        return None

    duration_raw = info.get("duration")
    duration = (
        float(duration_raw)
        if isinstance(duration_raw, (int, float)) and duration_raw > 0
        else None
    )
    upload_date = str(info.get("upload_date") or "") or None
    title = str(info.get("title") or "") or None
    description = str(info.get("description") or "") or None
    canonical_source = webpage_url or f"https://www.youtube.com/watch?v={video_id}"
    format_status = _youtube_format_status(
        info,
        duration=duration,
        upload_date=upload_date,
        webpage_url=canonical_source,
    )
    canonical = canonical_youtube_url(canonical_source, video_id)
    view_count_raw = info.get("view_count")
    view_count = (
        int(view_count_raw)
        if isinstance(view_count_raw, (int, float)) and view_count_raw >= 0
        else None
    )
    tags_raw = info.get("tags")
    tags = (
        [str(item).lstrip("#").casefold() for item in tags_raw]
        if isinstance(tags_raw, list)
        else []
    )
    hashtags = list(dict.fromkeys(tags + extract_hashtags(title, description)))
    return DiscoveredCandidate(
        platform="youtube",
        source_id=video_id,
        canonical_url=canonical,
        title=title,
        description=description,
        creator=str(info.get("channel") or info.get("uploader") or "") or None,
        view_count=view_count,
        metric_source="yt_dlp_view_count" if view_count is not None else None,
        duration_seconds=duration,
        upload_date=upload_date,
        hashtags=hashtags,
        short_format_status=format_status,
        discovered_at=datetime.now(UTC),
        metadata={
            key: info.get(key)
            for key in ("channel_id", "categories", "age_limit", "availability", "width", "height")
            if info.get(key) is not None
        },
    )


def _safe_post_value(post: object, name: str) -> object | None:
    try:
        return getattr(post, name, None)
    except Exception:
        # Instaloader's lazy GraphQL properties can be absent or unavailable for
        # a particular post. Missing metrics are recorded as unknown, not zero.
        return None


def candidate_from_instagram_post(
    post: object,
    *,
    from_reel_search: bool = True,
) -> DiscoveredCandidate | None:
    """Normalize an Instaloader Post without guessing absent metrics."""
    if not bool(_safe_post_value(post, "is_video")):
        return None
    shortcode = str(_safe_post_value(post, "shortcode") or "")
    if not shortcode:
        return None

    caption = _safe_post_value(post, "caption")
    view_count = _safe_post_value(post, "video_view_count")
    play_count = _safe_post_value(post, "video_play_count")
    duration = _safe_post_value(post, "video_duration")
    date = _safe_post_value(post, "date_utc")
    hashtags = list(_safe_post_value(post, "caption_hashtags") or [])
    likes = _safe_post_value(post, "likes")
    comments = _safe_post_value(post, "comments")
    return DiscoveredCandidate(
        platform="instagram",
        source_id=shortcode,
        canonical_url=f"https://www.instagram.com/reel/{shortcode}/",
        title=_safe_post_value(post, "title"),
        description=str(caption) if caption is not None else None,
        creator=_safe_post_value(post, "owner_username"),
        view_count=int(view_count) if isinstance(view_count, (int, float)) else None,
        play_count=int(play_count) if isinstance(play_count, (int, float)) else None,
        metric_source=(
            "instaloader_video_view_count" if isinstance(view_count, (int, float))
            else "instaloader_video_play_count" if isinstance(play_count, (int, float))
            else None
        ),
        duration_seconds=float(duration) if isinstance(duration, (int, float)) and duration > 0 else None,
        upload_date=date.date().isoformat() if isinstance(date, datetime) else None,
        hashtags=[str(tag).casefold() for tag in hashtags],
        short_format_status="confirmed" if from_reel_search else "candidate",
        discovered_at=datetime.now(UTC),
        metadata={
            "likes": int(likes or 0) if isinstance(likes, (int, float)) else None,
            "comments": int(comments or 0) if isinstance(comments, (int, float)) else None,
            "typename": str(_safe_post_value(post, "typename") or ""),
        },
    )
