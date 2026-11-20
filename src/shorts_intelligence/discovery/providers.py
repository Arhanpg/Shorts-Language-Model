"""Public search discovery adapters built on yt-dlp, DDGS and Instaloader.

No first-party platform API keys are used. These adapters use the public web
search/provider interfaces implemented by the upstream open-source projects.
They do not bypass login walls, CAPTCHAs, rate limits or access restrictions.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

from shorts_intelligence.discovery.models import DiscoveredCandidate
from shorts_intelligence.discovery.normalization import candidate_from_ytdlp, instagram_shortcode_from_url


class ProviderUnavailable(RuntimeError):
    """An optional discovery dependency is unavailable."""


class YouTubeSearchProvider:
    """Search YouTube with yt-dlp's ytsearch extractor (no Data API key)."""

    def search(self, query: str, *, limit: int = 50) -> Iterator[DiscoveredCandidate]:
        try:
            from yt_dlp import YoutubeDL
        except ImportError as exc:
            raise ProviderUnavailable(
                'YouTube discovery requires the optional extra: pip install -e ".[discovery]"'
            ) from exc

        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ignoreerrors": True,
            "playlistend": max(1, limit),
            "socket_timeout": 20,
            "retries": 1,
        }
        with YoutubeDL(options) as ydl:
            result = ydl.extract_info(f"ytsearch{max(1, limit)}:{query}", download=False)
        entries = result.get("entries", []) if isinstance(result, dict) else []
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            candidate = candidate_from_ytdlp(entry)
            if candidate is not None:
                yield candidate


class InstagramSearchProvider:
    """Find public Reel URLs with a search engine, then read metadata via Instaloader.

    DDGS is a web-search client, not an Instagram API client. Instaloader resolves
    the public shortcode and exposes video_view_count/video_play_count when Instagram
    makes those fields available. An optional existing Instaloader session can be
    loaded from a local session file; passwords/cookies are never accepted as CLI args.
    """

    def __init__(
        self,
        *,
        session_username: str | None = None,
        session_file: str | None = None,
        request_pause_seconds: float = 1.5,
    ) -> None:
        self.session_username = session_username
        self.session_file = session_file
        self.request_pause_seconds = max(0.0, request_pause_seconds)

    def _loader(self) -> Any:
        try:
            import instaloader
        except ImportError as exc:
            raise ProviderUnavailable(
                'Instagram metadata discovery requires Instaloader: '
                'pip install -e ".[discovery]"'
            ) from exc
        loader = instaloader.Instaloader(
            quiet=True,
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_comments=False,
            save_metadata=False,
        )
        if self.session_username:
            loader.load_session_from_file(
                self.session_username,
                filename=self.session_file,
            )
        return loader

    @staticmethod
    def _candidate_from_post(post: Any, *, from_reel_search: bool) -> DiscoveredCandidate | None:
        if not bool(getattr(post, "is_video", False)):
            return None
        shortcode = str(getattr(post, "shortcode", "") or "")
        if not shortcode:
            return None

        caption = getattr(post, "caption", None)
        view_count = getattr(post, "video_view_count", None)
        play_count = getattr(post, "video_play_count", None)
        duration = getattr(post, "video_duration", None)
        date = getattr(post, "date_utc", None)
        is_reel = from_reel_search
        metric_source = (
            "instaloader_video_view_count" if view_count is not None
            else "instaloader_video_play_count" if play_count is not None
            else None
        )
        hashtags = list(getattr(post, "caption_hashtags", []) or [])
        return DiscoveredCandidate(
            platform="instagram",
            source_id=shortcode,
            canonical_url=f"https://www.instagram.com/reel/{shortcode}/",
            title=getattr(post, "title", None),
            description=caption,
            creator=getattr(post, "owner_username", None),
            view_count=int(view_count) if view_count is not None else None,
            play_count=int(play_count) if play_count is not None else None,
            metric_source=metric_source,
            duration_seconds=float(duration) if duration is not None else None,
            upload_date=date.date().isoformat() if date is not None else None,
            hashtags=hashtags,
            short_format_status="confirmed" if is_reel else "candidate",
            metadata={
                "likes": int(getattr(post, "likes", 0) or 0),
                "comments": int(getattr(post, "comments", 0) or 0),
                "typename": str(getattr(post, "typename", "")),
                "discovery_method": "search_engine_reel_url" if is_reel else "instagram_profile_or_hashtag",
            },
        )

    def search(self, query: str, *, limit: int = 30) -> Iterator[DiscoveredCandidate]:
        try:
            from ddgs import DDGS
            import instaloader
        except ImportError as exc:
            raise ProviderUnavailable(
                'Instagram discovery requires DDGS and Instaloader: '
                'pip install -e ".[discovery]"'
            ) from exc

        with DDGS() as search:
            results = list(search.text(
                f"site:instagram.com/reel/ {query}",
                max_results=max(1, limit),
            ) or [])
        loader = self._loader()
        seen: set[str] = set()
        for result in results:
            if not isinstance(result, dict):
                continue
            url = str(result.get("href") or result.get("url") or "")
            shortcode = instagram_shortcode_from_url(url)
            if not shortcode or shortcode in seen:
                continue
            seen.add(shortcode)
            try:
                post = instaloader.Post.from_shortcode(loader.context, shortcode)
                candidate = self._candidate_from_post(post, from_reel_search=True)
                if candidate is not None:
                    yield candidate
            except Exception:
                # One unavailable/deleted/restricted post should not abort the run.
                # The caller reports provider errors and continues with other results.
                continue
            if self.request_pause_seconds:
                time.sleep(self.request_pause_seconds)

    def search_hashtag(self, hashtag: str, *, limit: int = 50) -> Iterator[DiscoveredCandidate]:
        """Optional authenticated hashtag search; requires a valid user session."""
        if not self.session_username:
            raise ValueError(
                "Instagram hashtag search requires --instagram-session-user and a valid local session."
            )
        try:
            import instaloader
        except ImportError as exc:
            raise ProviderUnavailable("Install the discovery extra first.") from exc
        loader = self._loader()
        tag = instaloader.Hashtag.from_name(loader.context, hashtag.lstrip("#"))
        iterator = tag.get_posts_resumable()
        seen: set[str] = set()
        count = 0
        for post in iterator:
            shortcode = str(getattr(post, "shortcode", "") or "")
            if not shortcode or shortcode in seen:
                continue
            seen.add(shortcode)
            candidate = self._candidate_from_post(post, from_reel_search=False)
            if candidate is not None:
                yield candidate
                count += 1
            if count >= limit:
                break
            if self.request_pause_seconds:
                time.sleep(self.request_pause_seconds)
