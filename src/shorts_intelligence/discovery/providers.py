"""Quiet, flat search providers for public short-form video discovery.

YouTube search results are parsed from the search page itself. The provider does
not resolve every result as a full video page, which avoids dropping search
results or flooding the terminal when individual videos are unavailable.
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


class _QuietYtDlpLogger:
    """Collect yt-dlp messages instead of writing per-item errors to the console."""

    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def debug(self, message: str) -> None:
        # yt-dlp sends ordinary progress/debug details here.
        return None

    def info(self, message: str) -> None:
        return None

    def warning(self, message: str) -> None:
        self.warnings.append(str(message))

    def error(self, message: str) -> None:
        self.errors.append(str(message))


class YouTubeSearchProvider:
    """Search YouTube using yt-dlp's native ytsearch extractor without opening every video."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def search(self, query: str, *, limit: int = 50) -> Iterator[DiscoveredCandidate]:
        try:
            from yt_dlp import YoutubeDL
        except ImportError as exc:
            raise ProviderUnavailable(
                'YouTube discovery requires yt-dlp: pip install -e ".[discovery]"'
            ) from exc

        logger = _QuietYtDlpLogger()
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ignoreerrors": True,
            # Keep entries returned by the YouTube search page flat. Without this,
            # YoutubeDL resolves every search result as a full video page, causing
            # unavailable/private/deleted results to be dropped and logged noisily.
            "extract_flat": "in_playlist",
            "playlistend": max(1, limit),
            "socket_timeout": 20,
            "retries": 1,
            "logger": logger,
            "extractor_args": {
                "youtube": {
                    # Request approximate publication date where yt-dlp can infer it.
                    "approximate_date": ["true"],
                }
            },
        }

        try:
            with YoutubeDL(options) as ydl:
                result = ydl.extract_info(
                    f"ytsearch{max(1, limit)}:{query}",
                    download=False,
                )
        except Exception as exc:
            self.errors.append(f"ytsearch query failed: {str(exc)[:300]}")
            return

        self.warnings.extend(logger.warnings[:30])
        self.errors.extend(logger.errors[:30])
        entries = result.get("entries", []) if isinstance(result, dict) else []
        seen: set[str] = set()
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            candidate = candidate_from_ytdlp(entry)
            if candidate is None or candidate.source_id in seen:
                continue
            seen.add(candidate.source_id)
            yield candidate


class InstagramSearchProvider:
    """Find indexed public Reel URLs with DDGS, then resolve them using Instaloader.

    Search uses DDGS' documented region/backend/page options. Metadata lookup is
    per Reel, but failures are collected and do not flood the terminal or abort a
    complete search run.
    """

    def __init__(
        self,
        *,
        session_username: str | None = None,
        session_file: str | None = None,
        request_pause_seconds: float = 1.5,
        region: str = "in-en",
        backend: str = "auto",
        pages: int = 2,
    ) -> None:
        self.session_username = session_username
        self.session_file = session_file
        self.errors: list[str] = []
        self.request_pause_seconds = max(0.0, request_pause_seconds)
        self.region = region
        self.backend = backend
        self.pages = max(1, min(pages, 5))

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

    def _search_urls(self, query: str, *, limit: int) -> list[str]:
        try:
            from ddgs import DDGS
        except ImportError as exc:
            raise ProviderUnavailable(
                'Instagram URL search requires DDGS: pip install -e ".[discovery]"'
            ) from exc

        found: list[str] = []
        seen: set[str] = set()
        search_query = f"site:instagram.com/reel/ {query}"
        with DDGS() as search:
            for page in range(1, self.pages + 1):
                try:
                    results = search.text(
                        search_query,
                        region=self.region,
                        safesearch="moderate",
                        max_results=max(1, limit),
                        page=page,
                        backend=self.backend,
                    ) or []
                except Exception as exc:
                    self.errors.append(
                        f"DDGS page {page} for '{query}': {str(exc)[:250]}"
                    )
                    continue
                for result in results:
                    if not isinstance(result, dict):
                        continue
                    url = str(result.get("href") or result.get("url") or "")
                    shortcode = instagram_shortcode_from_url(url)
                    if shortcode and shortcode not in seen:
                        seen.add(shortcode)
                        found.append(url)
        return found

    def search(self, query: str, *, limit: int = 30) -> Iterator[DiscoveredCandidate]:
        try:
            import instaloader  # noqa: F401
        except ImportError as exc:
            raise ProviderUnavailable(
                'Instagram metadata discovery requires Instaloader: '
                'pip install -e ".[discovery]"'
            ) from exc

        urls = self._search_urls(query, limit=limit)
        if not urls:
            return
        loader = self._loader()
        for url in urls:
            shortcode = instagram_shortcode_from_url(url)
            if not shortcode:
                continue
            try:
                post = instaloader.Post.from_shortcode(loader.context, shortcode)
                candidate = candidate_from_instagram_post(post, from_reel_search=True)
                if candidate is not None:
                    yield candidate
            except Exception as exc:
                # Deleted, private, temporarily unavailable and login-gated results
                # are individual source failures, not fatal provider failures.
                self.errors.append(f"Instagram Reel {shortcode}: {str(exc)[:250]}")
            if self.request_pause_seconds:
                time.sleep(self.request_pause_seconds)

    def search_hashtag(self, hashtag: str, *, limit: int = 50) -> Iterator[DiscoveredCandidate]:
        """Optional authenticated hashtag search; requires an existing local session."""
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
                candidate = candidate_from_instagram_post(post, from_reel_search=False)
            except Exception as exc:
                self.errors.append(f"hashtag #{hashtag}: {str(exc)[:200]}")
                continue
            if candidate is None or candidate.source_id in seen:
                continue
            seen.add(candidate.source_id)
            yield candidate
            count += 1
            if count >= limit:
                break
            if self.request_pause_seconds:
                time.sleep(self.request_pause_seconds)
