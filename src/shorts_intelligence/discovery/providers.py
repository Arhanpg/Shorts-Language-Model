"""Resilient, no-official-API discovery providers.

YouTube uses the open-source ytscrape project, which applies YouTube's Shorts
search filter and returns typed search metadata. It communicates with the
website's internal InnerTube web endpoints rather than the official Data API.

Instagram public-link discovery uses DDGS metasearch. Instaloader resolves
public Reel metadata with deliberately short request timeouts, one connection
attempt, and a circuit breaker. Neither provider bypasses login walls,
CAPTCHAs, platform access controls, or rate limits.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

from shorts_intelligence.discovery.models import DiscoveredCandidate
from shorts_intelligence.discovery.normalization import (
    candidate_from_instagram_post,
    candidate_from_ytscrape_video,
    extract_hashtags,
    instagram_shortcode_from_url,
)


class ProviderUnavailable(RuntimeError):
    """An optional discovery dependency is unavailable."""


class YouTubeSearchProvider:
    """Shorts-filtered YouTube search with locale rotation and selective enrichment."""

    def __init__(
        self,
        *,
        request_timeout: float = 12.0,
        request_interval: float = 1.25,
        max_retries: int = 1,
        detail_enrichment_limit: int = 40,
    ) -> None:
        self.request_timeout = max(3.0, request_timeout)
        self.request_interval = max(0.5, request_interval)
        self.max_retries = max(0, max_retries)
        self.detail_enrichment_limit = max(0, detail_enrichment_limit)
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.search_results_seen = 0
        self.enrichment_attempts = 0
        self.enrichment_successes = 0
        self.circuit_open = False
        self.circuit_reason: str | None = None
        self.consecutive_failures = 0
        self.failure_threshold = 3
        self._clients: dict[tuple[str, str], Any] = {}

    def _client_for(self, language: str, region: str) -> Any:
        key = (language.casefold(), region.upper())
        if key in self._clients:
            return self._clients[key]
        try:
            from ytscrape import RetryPolicy, YouTube
        except ImportError as exc:
            raise ProviderUnavailable(
                'YouTube Shorts discovery requires ytscrape: '
                'pip install -e ".[discovery]" --upgrade'
            ) from exc

        retry = RetryPolicy(
            max_retries=self.max_retries,
            backoff_factor=0.5,
            max_backoff=2.0,
            jitter=True,
        )
        client = YouTube(
            language=language,
            region=region,
            timeout=self.request_timeout,
            retry=retry,
            min_interval=self.request_interval,
        )
        self._clients[key] = client
        return client

    @staticmethod
    def _is_stop_error(exc: Exception) -> bool:
        text = f"{type(exc).__name__}: {exc}".casefold()
        return any(
            token in text
            for token in (
                "ratelimited",
                "http 429",
                "too many requests",
                "botdetected",
                "captcha",
                "confirm you're not a bot",
                "consentrequired",
                "request blocked",
                "timed out",
                "connectionerror",
                "requesterror",
            )
        )

    def _record_error(self, platform: str, exc: Exception) -> None:
        if len(self.errors) < 100:
            self.errors.append(f"{platform}: {type(exc).__name__}: {str(exc)[:250]}")
        self.consecutive_failures += 1
        if self._is_stop_error(exc) or self.consecutive_failures >= self.failure_threshold:
            self.circuit_open = True
            self.circuit_reason = f"{type(exc).__name__}: {str(exc)[:180]}"

    def search(
        self,
        query: str,
        *,
        limit: int = 50,
        language: str = "en",
        region: str = "IN",
    ) -> Iterator[DiscoveredCandidate]:
        """Use YouTube's Shorts-only filter and preserve typed metrics.

        The ytscrape SearchFilter.SHORTS option applies the website's dedicated
        Shorts search filter. Results are paginated up to the requested cap.
        """
        if self.circuit_open:
            return
        try:
            from ytscrape import BotDetected, RateLimited, SearchFilter
        except ImportError as exc:
            raise ProviderUnavailable(
                'YouTube Shorts discovery requires ytscrape 2.2+: '
                'pip install -e ".[discovery]" --upgrade'
            ) from exc

        try:
            client = self._client_for(language, region)
            results = client.search(
                query,
                filter=SearchFilter.SHORTS,
                max_results=max(1, min(limit, 50)),
            )
            seen: set[str] = set()
            for video in results:
                self.search_results_seen += 1
                candidate = candidate_from_ytscrape_video(
                    video,
                    query=query,
                    language=language,
                    region=region,
                )
                if candidate is None or candidate.source_id in seen:
                    continue
                seen.add(candidate.source_id)
                yield candidate
            self.consecutive_failures = 0
        except (RateLimited, BotDetected) as exc:
            self._record_error("youtube", exc)
        except ProviderUnavailable:
            raise
        except Exception as exc:
            self._record_error("youtube", exc)

    def enrich(
        self,
        candidate: DiscoveredCandidate,
        *,
        language: str = "en",
        region: str = "IN",
    ) -> DiscoveredCandidate:
        """Fetch detailed player metadata only when search metadata is incomplete.

        Enrichment is capped per provider instance. It never runs for a candidate
        with both a view count and a duration already present.
        """
        if candidate.platform != "youtube":
            return candidate
        if candidate.view_count is not None and candidate.duration_seconds is not None:
            return candidate
        if self.circuit_open or self.enrichment_attempts >= self.detail_enrichment_limit:
            return candidate

        try:
            from ytscrape import BotDetected, RateLimited
        except ImportError as exc:
            raise ProviderUnavailable("Install the discovery extra first.") from exc

        self.enrichment_attempts += 1
        try:
            details = self._client_for(language, region).video(candidate.source_id)
        except (RateLimited, BotDetected) as exc:
            self._record_error("youtube metadata enrichment", exc)
            return candidate
        except Exception as exc:
            self._record_error("youtube metadata enrichment", exc)
            return candidate

        views = candidate.view_count
        if views is None and isinstance(details.views, int) and details.views >= 0:
            views = details.views
        duration = candidate.duration_seconds
        if duration is None and isinstance(details.length_seconds, int) and details.length_seconds > 0:
            duration = float(details.length_seconds)
        title = details.title or candidate.title
        description = details.description or candidate.description
        creator = candidate.creator or details.channel
        upload_date = candidate.upload_date or details.upload_date
        hashtags = list(dict.fromkeys(candidate.hashtags + extract_hashtags(title, description)))
        metadata = {
            **candidate.metadata,
            "detail_enriched": True,
            "detail_views": details.views,
            "detail_length_seconds": details.length_seconds,
            "detail_published_at": details.published_at.isoformat() if details.published_at else None,
            "detail_channel_id": details.channel_id,
            "detail_category": details.category,
        }
        self.enrichment_successes += 1
        self.consecutive_failures = 0
        return candidate.model_copy(
            update={
                "view_count": views,
                "metric_source": (
                    candidate.metric_source
                    or ("ytscrape_player_view_count" if views is not None else None)
                ),
                "duration_seconds": duration,
                "title": title,
                "description": description,
                "creator": creator,
                "upload_date": upload_date,
                "hashtags": hashtags,
                "metadata": metadata,
            }
        )

    def close(self) -> None:
        """Close the HTTP sessions used for each locale."""
        for client in self._clients.values():
            try:
                client.close()
            except Exception:
                pass
        self._clients.clear()

    def __enter__(self) -> YouTubeSearchProvider:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


class InstagramSearchProvider:
    """Search indexed public Reels and resolve metadata with bounded retries.

    DDGS uses a short network timeout and an explicit backend list that avoids
    the slow Yahoo default encountered in the user's latest run. Instaloader
    defaults are overridden from 300 seconds / three attempts to 12 seconds /
    one attempt. Consecutive failures or access/rate-limit errors open a circuit
    for the remainder of the run.
    """

    def __init__(
        self,
        *,
        session_username: str | None = None,
        session_file: str | None = None,
        request_pause_seconds: float = 2.5,
        region: str = "in-en",
        backend: str = "bing,brave,duckduckgo",
        fallback_backend: str = "google",
        pages: int = 1,
        search_timeout: int = 8,
        request_timeout: float = 12.0,
        max_connection_attempts: int = 1,
        max_lookups: int = 40,
        failure_threshold: int = 3,
    ) -> None:
        self.session_username = session_username
        self.session_file = session_file
        self.errors: list[str] = []
        self.search_results_seen = 0
        self.metadata_lookups = 0
        self.lookup_backlog = 0
        self.metadata_failures = 0
        self.metadata_successes = 0
        self.ddgs_failures = 0
        self.consecutive_search_failures = 0
        self.request_pause_seconds = max(1.0, request_pause_seconds)
        self.region = region
        self.backend = backend
        self.fallback_backend = fallback_backend
        self.pages = max(1, min(pages, 3))
        self.search_timeout = max(3, min(search_timeout, 15))
        self.request_timeout = max(5.0, min(request_timeout, 30.0))
        self.max_connection_attempts = max(1, min(max_connection_attempts, 2))
        self.max_lookups = max(1, min(max_lookups, 100))
        self.failure_threshold = max(1, min(failure_threshold, 5))
        self.consecutive_failures = 0
        self.circuit_open = False
        self.circuit_reason: str | None = None
        self._loader_instance: Any | None = None

    def _record_error(self, message: str) -> None:
        if len(self.errors) < 100:
            self.errors.append(message[:350])

    def _open_circuit(self, reason: str) -> None:
        self.circuit_open = True
        self.circuit_reason = reason[:250]

    def _loader(self) -> Any:
        if self._loader_instance is not None:
            return self._loader_instance
        try:
            import instaloader
        except ImportError as exc:
            raise ProviderUnavailable(
                'Instagram metadata discovery requires Instaloader: '
                'pip install -e ".[discovery]" --upgrade'
            ) from exc

        loader = instaloader.Instaloader(
            quiet=True,
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_comments=False,
            save_metadata=False,
            max_connection_attempts=self.max_connection_attempts,
            request_timeout=self.request_timeout,
            # Do not retry a blocked account/session indefinitely.
            fatal_status_codes=[401, 403, 429],
        )
        if self.session_username:
            loader.load_session_from_file(
                self.session_username,
                filename=self.session_file,
            )
        self._loader_instance = loader
        return loader

    def _search_page(
        self,
        query: str,
        *,
        limit: int,
        page: int,
        backend: str,
    ) -> list[dict[str, Any]]:
        try:
            from ddgs import DDGS
        except ImportError as exc:
            raise ProviderUnavailable(
                'Instagram URL search requires DDGS: pip install -e ".[discovery]"'
            ) from exc
        with DDGS(timeout=self.search_timeout) as search:
            return list(
                search.text(
                    query,
                    region=self.region,
                    safesearch="moderate",
                    max_results=max(1, min(limit, 30)),
                    page=page,
                    backend=backend,
                )
                or []
            )

    def _search_urls(self, query: str, *, limit: int) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()
        search_query = query if query.startswith("site:instagram.com/") else (
            f"site:instagram.com/reel/ {query}"
        )
        for page in range(1, self.pages + 1):
            try:
                results = self._search_page(
                    search_query, limit=limit, page=page, backend=self.backend
                )
            except ProviderUnavailable:
                raise
            except Exception as exc:
                self.ddgs_failures += 1
                self._record_error(
                    f"DDGS {self.backend} page {page} for '{query}': "
                    f"{type(exc).__name__}: {str(exc)[:200]}"
                )
                results = []
                if self.fallback_backend and self.fallback_backend != self.backend:
                    try:
                        results = self._search_page(
                            search_query,
                            limit=limit,
                            page=page,
                            backend=self.fallback_backend,
                        )
                    except ProviderUnavailable:
                        raise
                    except Exception as fallback_exc:
                        self.ddgs_failures += 1
                        self._record_error(
                            f"DDGS fallback {self.fallback_backend}: "
                            f"{type(fallback_exc).__name__}: {str(fallback_exc)[:180]}"
                        )
            if results:
                self.consecutive_search_failures = 0
            else:
                self.consecutive_search_failures += 1
                if self.consecutive_search_failures >= self.failure_threshold:
                    self._open_circuit(
                        f"DDGS returned no results after {self.consecutive_search_failures} "
                        "consecutive failed searches"
                    )
            for result in results:
                if not isinstance(result, dict):
                    continue
                url = str(result.get("href") or result.get("url") or "")
                shortcode = instagram_shortcode_from_url(url)
                if shortcode and shortcode not in seen:
                    seen.add(shortcode)
                    found.append(url)
        self.search_results_seen += len(found)
        return found

    @staticmethod
    def _should_open_circuit(exc: Exception) -> bool:
        text = f"{type(exc).__name__}: {exc}".casefold()
        return any(
            marker in text
            for marker in (
                "429",
                "too many requests",
                "401",
                "403",
                "login_required",
                "challenge_required",
                "checkpoint_required",
                "read timed out",
                "timed out",
                "remote disconnected",
                "remote end closed connection",
                "connection aborted",
                "connection reset",
                "connectionexception",
            )
        )

    def _resolve_shortcode(self, shortcode: str, loader: Any) -> DiscoveredCandidate | None:
        import instaloader

        self.metadata_lookups += 1
        try:
            post = instaloader.Post.from_shortcode(loader.context, shortcode)
            candidate = candidate_from_instagram_post(post, from_reel_search=True)
        except Exception as exc:
            self.metadata_failures += 1
            self.consecutive_failures += 1
            self._record_error(
                f"Instagram Reel {shortcode}: {type(exc).__name__}: {str(exc)[:220]}"
            )
            if (
                self._should_open_circuit(exc)
                or self.consecutive_failures >= self.failure_threshold
            ):
                self._open_circuit(
                    f"Stopped after {self.metadata_failures} metadata failures; "
                    f"last error: {type(exc).__name__}: {str(exc)[:160]}"
                )
            return None

        self.consecutive_failures = 0
        if candidate is not None:
            self.metadata_successes += 1
        return candidate

    def search(self, query: str, *, limit: int = 30) -> Iterator[DiscoveredCandidate]:
        """Search indexed Reel URLs and resolve at most the remaining lookup budget."""
        if self.circuit_open or self.metadata_lookups >= self.max_lookups:
            return
        urls = self._search_urls(query, limit=limit)
        if not urls:
            return
        try:
            loader = self._loader()
        except ProviderUnavailable:
            raise
        except Exception as exc:
            self._open_circuit(f"Could not initialize Instaloader: {type(exc).__name__}: {exc}")
            self._record_error(self.circuit_reason or str(exc))
            return

        remaining = self.max_lookups - self.metadata_lookups
        self.lookup_backlog += max(0, len(urls) - remaining)
        for url in urls[:remaining]:
            if self.circuit_open:
                break
            shortcode = instagram_shortcode_from_url(url)
            if not shortcode:
                continue
            candidate = self._resolve_shortcode(shortcode, loader)
            if candidate is not None:
                yield candidate
            if self.request_pause_seconds:
                time.sleep(self.request_pause_seconds)

    def search_hashtag(self, hashtag: str, *, limit: int = 50) -> Iterator[DiscoveredCandidate]:
        """Optional authenticated hashtag search; obeys the same lookup cap."""
        if not self.session_username:
            raise ValueError(
                "Instagram hashtag search requires --instagram-session-user and a valid local session."
            )
        if self.circuit_open or self.metadata_lookups >= self.max_lookups:
            return
        try:
            import instaloader
            loader = self._loader()
            tag = instaloader.Hashtag.from_name(loader.context, hashtag.lstrip("#"))
            iterator = tag.get_posts_resumable()
        except ProviderUnavailable:
            raise
        except Exception as exc:
            self._open_circuit(f"Hashtag search could not start: {type(exc).__name__}: {exc}")
            self._record_error(self.circuit_reason or str(exc))
            return

        remaining = min(limit, self.max_lookups - self.metadata_lookups)
        self.lookup_backlog += max(0, min(limit, self.max_lookups) - remaining)
        seen: set[str] = set()
        for post in iterator:
            if self.circuit_open or len(seen) >= remaining:
                break
            try:
                shortcode = str(getattr(post, "shortcode", "") or "")
            except Exception as exc:
                self.metadata_failures += 1
                self._record_error(f"Hashtag #{hashtag}: {type(exc).__name__}: {str(exc)[:180]}")
                if self._should_open_circuit(exc):
                    self._open_circuit(str(exc))
                continue
            if not shortcode or shortcode in seen:
                continue
            seen.add(shortcode)
            self.search_results_seen += 1
            candidate = self._resolve_shortcode(shortcode, loader)
            if candidate is not None:
                # Hashtag provenance is a candidate, not proof of Reel URL format.
                candidate = candidate.model_copy(update={"short_format_status": "candidate"})
                yield candidate
            if self.request_pause_seconds:
                time.sleep(self.request_pause_seconds)

    def close(self) -> None:
        if self._loader_instance is not None:
            try:
                self._loader_instance.close()
            except Exception:
                pass
            self._loader_instance = None

    def __enter__(self) -> InstagramSearchProvider:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
