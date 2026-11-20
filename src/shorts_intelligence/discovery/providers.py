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
from shorts_intelligence.discovery.normalization import (
    candidate_from_instagram_post,
    candidate_from_ytdlp,
    instagram_shortcode_from_url,
)


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
        self.errors: list[str] = []
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

    def search(self, query: str, *, limit: int = 30) -> Iterator[DiscoveredCandidate]:
        try:
            import instaloader
            from ddgs import DDGS
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
                candidate = candidate_from_instagram_post(post, from_reel_search=True)
                if candidate is not None:
                    yield candidate
            except Exception as exc:
                # One unavailable/deleted/restricted post should not abort the run.
                self.errors.append(f"{shortcode}: {str(exc)[:250]}")
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
        scanned = 0
        for post in iterator:
            scanned += 1
            if scanned > max(limit * 12, limit + 25):
                break
            try:
                shortcode = str(getattr(post, "shortcode", "") or "")
            except Exception as exc:
                self.errors.append(f"hashtag #{hashtag}: shortcode read failed: {str(exc)[:150]}")
                continue
            if not shortcode or shortcode in seen:
                continue
            seen.add(shortcode)
            try:
                candidate = candidate_from_instagram_post(post, from_reel_search=False)
            except Exception as exc:
                self.errors.append(f"hashtag #{hashtag} {shortcode}: {str(exc)[:200]}")
                continue
            if candidate is not None:
                yield candidate
                count += 1
            if count >= limit:
                break
            if self.request_pause_seconds:
                time.sleep(self.request_pause_seconds)
