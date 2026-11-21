"""Visible, user-session Instagram Reels discovery.

Uses a single persistent local Chrome context per run. The user signs in manually.
Only ordinary public profile, hashtag and Reel pages are visited; no private
requests are constructed or replayed and no access-control challenge is bypassed.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from shorts_intelligence.discovery.models import DiscoveredCandidate

_CODE = re.compile(r"^[A-Za-z0-9_-]{5,}$")
_REEL_PATH = re.compile(r"/reel/([A-Za-z0-9_-]{5,})/?", re.IGNORECASE)
_NUMERIC_COUNT = re.compile(r"^\s*[0-9][0-9,]*\s*$")
_PLAY_FIELDS = ("play_count", "video_play_count", "ig_play_count")
_VIEW_FIELDS = ("view_count", "video_view_count")


def _raw_count(value: object) -> int | None:
    """Parse only explicit integer counts; never guess from abbreviated display text."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and _NUMERIC_COUNT.fullmatch(value):
        try:
            return int(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def _first_count(value: dict[str, Any], fields: tuple[str, ...]) -> tuple[int | None, str | None]:
    for field in fields:
        count = _raw_count(value.get(field))
        if count is not None:
            return count, field
    return None, None


def _username(value: object) -> str | None:
    if isinstance(value, dict):
        raw = value.get("username") or value.get("user_name")
        if isinstance(raw, str) and raw.strip():
            return raw.strip().lstrip("@").casefold()
    return None


def extract_reel_records(
    payload: object,
    *,
    creator_handle: str,
    discovery_surface: str = "instagram_json",
    hashtag: str | None = None,
) -> list[DiscoveredCandidate]:
    """Extract explicit Reel/video records from observed Instagram response JSON."""
    found: dict[str, DiscoveredCandidate] = {}

    def walk(value: object) -> None:
        if isinstance(value, dict):
            code = value.get("code") or value.get("shortcode") or value.get("media_code")
            product_type = str(value.get("product_type") or "").casefold()
            media_type = value.get("media_type")
            if isinstance(media_type, str) and media_type.isdigit():
                media_type = int(media_type)
            is_reel = (
                product_type in {"clips", "reels", "reel"}
                or media_type == 2
                or value.get("is_reel") is True
                or value.get("is_video") is True
            )
            if isinstance(code, str) and _CODE.fullmatch(code) and is_reel:
                plays, play_field = _first_count(value, _PLAY_FIELDS)
                views, view_field = _first_count(value, _VIEW_FIELDS)
                owner = _username(value.get("user")) or _username(value.get("owner"))
                coauthors = value.get("coauthor_producers") or value.get("coauthors") or []
                coauthor_handles = sorted({
                    handle for item in coauthors
                    if (handle := _username(item)) is not None
                }) if isinstance(coauthors, list) else []
                caption_value = value.get("caption")
                if isinstance(caption_value, dict):
                    caption_value = caption_value.get("text")
                caption = caption_value if isinstance(caption_value, str) else None
                hashtags = sorted(set(re.findall(r"#([\w]+)", caption or "")))
                metric_source = (
                    f"instagram_response.{play_field}" if plays is not None
                    else f"instagram_response.{view_field}" if views is not None
                    else None
                )
                record = DiscoveredCandidate(
                    platform="instagram",
                    source_id=code,
                    canonical_url=f"https://www.instagram.com/reel/{code}/",
                    title=None,
                    description=caption,
                    creator=owner or creator_handle,
                    view_count=views,
                    play_count=plays,
                    metric_source=metric_source,
                    short_format_status="confirmed",
                    hashtags=hashtags,
                    metadata={
                        "provider": "playwright_response_observer",
                        "discovery_surface": discovery_surface,
                        "hashtag": hashtag,
                        "metric_kind": (
                            "plays" if plays is not None
                            else "views" if views is not None else "unknown"
                        ),
                        "metric_field": play_field or view_field,
                        "coauthor_handles": coauthor_handles,
                        "product_type": product_type or None,
                        "media_type": media_type,
                        "instagram_owner": owner,
                    },
                )
                previous = found.get(code)
                if previous is None or (
                    previous.qualifying_metric() is None
                    and record.qualifying_metric() is not None
                ):
                    found[code] = record
                elif previous and record.description and not previous.description:
                    previous.description = record.description
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return list(found.values())


def _jsonld_video_metric(payload: object) -> tuple[str, int, str] | None:
    """Extract exact WatchAction/ViewAction counts from public Reel JSON-LD."""
    found: list[tuple[str, int, str]] = []

    def walk(value: object) -> None:
        if isinstance(value, dict):
            stats = value.get("interactionStatistic")
            if isinstance(stats, dict):
                stats = [stats]
            if isinstance(stats, list):
                for item in stats:
                    if not isinstance(item, dict):
                        continue
                    raw_type = item.get("interactionType")
                    action = (
                        str(raw_type.get("@type") or "")
                        if isinstance(raw_type, dict) else str(raw_type or "")
                    ).rsplit("/", 1)[-1]
                    metric = _raw_count(item.get("userInteractionCount"))
                    if metric is not None and action in {"WatchAction", "ViewAction"}:
                        kind = "plays" if action == "WatchAction" else "views"
                        found.append((kind, metric, f"instagram_jsonld.{action}"))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return next((item for item in found if item[0] == "plays"), found[0] if found else None)


class InstagramPlaywrightProvider:
    """One visible persistent Chrome profile reused across all discovery surfaces."""

    def __init__(
        self,
        *,
        profile_dir: Path,
        timeout_seconds: float = 15.0,
        detail_timeout_seconds: float = 8.0,
    ) -> None:
        self.profile_dir = profile_dir.expanduser().resolve()
        self.timeout_seconds = max(5.0, min(timeout_seconds, 30.0))
        self.detail_timeout_seconds = max(4.0, min(detail_timeout_seconds, 15.0))
        self.requests_observed = 0
        self.responses_parsed = 0
        self.responses_unparsed = 0
        self.errors: list[str] = []
        self.blocked = False
        self.creator_diagnostics: list[dict[str, Any]] = []
        self.hashtag_diagnostics: list[dict[str, Any]] = []
        self._playwright: Any = None
        self._context: Any = None

    async def _ensure_context(self) -> Any:
        if self._context is not None:
            # Chrome can be closed by the user while a run is active. Check
            # the owning browser connection instead of trusting a cached
            # BrowserContext handle after its target has gone away.
            try:
                browser = self._context.browser
                connected = browser is None or browser.is_connected()
                if connected:
                    _ = self._context.pages
                    return self._context
            except Exception:
                pass
            await self.close()
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                'Install browser support: pip install -e ".[instagram-browser]" '
                "then run playwright install chromium"
            ) from exc
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        try:
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=False,
                channel="chrome",
                viewport={"width": 1365, "height": 900},
            )
            # Persistent contexts may create an initial blank tab; surfaces
            # below own their pages explicitly and close them after each visit.
            for initial_page in list(self._context.pages):
                await initial_page.close()
        except Exception as exc:
            playwright = self._playwright
            self._context = None
            self._playwright = None
            if playwright is not None:
                try:
                    await playwright.stop()
                except Exception:
                    pass
            message = str(exc)
            if any(token in message.casefold() for token in (
                "target.createtarget", "target page", "browser has been closed",
                "user data directory is already in use", "process singleton"
            )):
                raise RuntimeError(
                    "Could not open the Instagram Chrome profile. Close every Chrome "
                    "window using this profile, check Task Manager for leftover chrome.exe "
                    "processes, then retry. Do not delete the profile or its session files."
                ) from exc
            raise
        return self._context

    async def close(self) -> None:
        # Cleanup must be idempotent and must not mask the real collection error
        # when the user closes Chrome or Windows tears down its pipe transport.
        context, playwright = self._context, self._playwright
        self._context = None
        self._playwright = None
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                await playwright.stop()
            except Exception:
                pass

    async def _collect_surface(
        self,
        *,
        url: str,
        creator_handle: str,
        surface: str,
        hashtag: str | None,
        max_scrolls: int,
        max_reel_details: int,
    ) -> tuple[list[DiscoveredCandidate], set[str], dict[str, Any]]:
        context = await self._ensure_context()
        try:
            page = await context.new_page()
        except Exception as exc:
            # Recover once from an externally closed target/context. The
            # persistent profile is reused; no second profile is created.
            self._context = None
            message = str(exc).casefold()
            if any(token in message for token in (
                "targetclosederror", "target page, context or browser has been closed",
                "target.createtarget", "browser has been closed"
            )):
                await self.close()
                context = await self._ensure_context()
                page = await context.new_page()
            else:
                raise
        candidates: dict[str, DiscoveredCandidate] = {}
        coauthors: set[str] = set()
        tasks: set[asyncio.Task[Any]] = set()
        diagnostic: dict[str, Any] = {
            "surface": surface,
            "handle": creator_handle,
            "hashtag": hashtag,
            "requested_url": url,
            "final_url": None,
            "page_title": None,
            "http_json_responses": 0,
            "responses_with_reels": 0,
            "responses_without_reels": 0,
            "parse_errors": 0,
            "dom_reel_links": 0,
            "detail_pages_attempted": 0,
            "detail_pages_with_metrics": 0,
            "detail_pages_without_metrics": 0,
            "candidate_count": 0,
            "metric_count": 0,
            "login_or_checkpoint": False,
            "reason": None,
        }

        def add_records(records: list[DiscoveredCandidate]) -> None:
            for candidate in records:
                previous = candidates.get(candidate.source_id)
                if previous is None:
                    candidates[candidate.source_id] = candidate
                else:
                    if candidate.play_count is not None:
                        previous.play_count = candidate.play_count
                    if candidate.view_count is not None:
                        previous.view_count = candidate.view_count
                    if candidate.metric_source:
                        previous.metric_source = candidate.metric_source
                    if candidate.description and not previous.description:
                        previous.description = candidate.description
                    previous.metadata.update(candidate.metadata)
                coauthors.update(candidate.metadata.get("coauthor_handles", []))

        async def parse_response(response: Any) -> None:
            try:
                parsed_url = urlparse(response.url)
                if parsed_url.hostname not in {"instagram.com", "www.instagram.com"}:
                    return
                if response.request.resource_type not in {"xhr", "fetch"}:
                    return
                content_type = response.headers.get("content-type", "").casefold()
                if "json" not in content_type:
                    return
                self.requests_observed += 1
                diagnostic["http_json_responses"] += 1
                if response.status in {401, 403, 429}:
                    self.blocked = True
                    diagnostic["reason"] = f"HTTP {response.status} from Instagram"
                    return
                payload = await asyncio.wait_for(
                    response.json(), timeout=self.timeout_seconds
                )
                records = extract_reel_records(
                    payload,
                    creator_handle=creator_handle,
                    discovery_surface=surface,
                    hashtag=hashtag,
                )
                if records:
                    self.responses_parsed += 1
                    diagnostic["responses_with_reels"] += 1
                    add_records(records)
                else:
                    self.responses_unparsed += 1
                    diagnostic["responses_without_reels"] += 1
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.responses_unparsed += 1
                diagnostic["parse_errors"] += 1
                if len(self.errors) < 50:
                    self.errors.append(
                        f"{surface} {creator_handle}: {type(exc).__name__}: {str(exc)[:140]}"
                    )

        def on_response(response: Any) -> None:
            task = asyncio.create_task(parse_response(response))
            tasks.add(task)
            task.add_done_callback(tasks.discard)

        def collect_rendered_links(raw_links: list[str]) -> None:
            for href in raw_links:
                match = _REEL_PATH.search(href or "")
                if not match:
                    continue
                code = match.group(1)
                if code not in candidates:
                    candidates[code] = DiscoveredCandidate(
                        platform="instagram",
                        source_id=code,
                        canonical_url=f"https://www.instagram.com/reel/{code}/",
                        creator=creator_handle,
                        short_format_status="confirmed",
                        metadata={
                            "provider": "playwright_rendered_reel_link",
                            "discovery_surface": surface,
                            "hashtag": hashtag,
                            "metric_kind": "unknown",
                        },
                    )

        page.on("response", on_response)
        try:
            response = await asyncio.wait_for(
                page.goto(url, wait_until="domcontentloaded"),
                timeout=self.timeout_seconds * 2,
            )
            await page.wait_for_timeout(1800)
            diagnostic["final_url"] = page.url
            diagnostic["page_title"] = (await page.title())[:160]
            final_url = page.url.casefold()
            if any(token in final_url for token in (
                "checkpoint", "challenge", "/accounts/login", "consent"
            )):
                self.blocked = True
                diagnostic["login_or_checkpoint"] = True
                diagnostic["reason"] = "Instagram redirected to login/checkpoint/challenge"
            elif response is not None and response.status in {401, 403, 429}:
                self.blocked = True
                diagnostic["reason"] = f"Surface page returned HTTP {response.status}"

            if not self.blocked:
                previous_count = -1
                stable_rounds = 0
                for _ in range(max(0, min(max_scrolls, 20))):
                    await page.mouse.wheel(0, 1750)
                    await page.wait_for_timeout(850)
                    links = await page.locator('a[href*="/reel/"]').evaluate_all(
                        "(els) => els.map((el) => el.getAttribute('href')).filter(Boolean)"
                    )
                    collect_rendered_links(links)
                    diagnostic["dom_reel_links"] = len(candidates)
                    current_count = len(candidates)
                    stable_rounds = stable_rounds + 1 if current_count == previous_count else 0
                    previous_count = current_count
                    if stable_rounds >= 2:
                        break

                # Reel grid cards often expose only a permalink. Resolve a small,
                # configurable sample through the normal visible Reel detail page.
                detail_codes = [
                    code for code, item in candidates.items()
                    if item.qualifying_metric() is None
                ][:max(0, min(max_reel_details, 30))]
                for code in detail_codes:
                    if self.blocked:
                        break
                    diagnostic["detail_pages_attempted"] += 1
                    before = candidates[code].qualifying_metric()
                    try:
                        await asyncio.wait_for(
                            page.goto(
                                f"https://www.instagram.com/reel/{code}/",
                                wait_until="domcontentloaded",
                            ),
                            timeout=self.detail_timeout_seconds * 2,
                        )
                        await page.wait_for_timeout(850)
                        scripts = await page.locator(
                            'script[type="application/ld+json"]'
                        ).all_text_contents()
                        for script in scripts:
                            try:
                                payload = json.loads(script)
                            except (ValueError, TypeError):
                                continue
                            add_records(extract_reel_records(
                                payload,
                                creator_handle=creator_handle,
                                discovery_surface="reel_detail_jsonld",
                                hashtag=hashtag,
                            ))
                            detail_metric = _jsonld_video_metric(payload)
                            if detail_metric:
                                kind, count, source = detail_metric
                                target = candidates[code]
                                if kind == "plays":
                                    target.play_count = count
                                else:
                                    target.view_count = count
                                target.metric_source = source
                                target.metadata["metric_kind"] = kind
                                target.metadata["metric_source"] = source
                                target.metadata["metric_detail_enriched"] = True
                    except Exception as exc:
                        if len(self.errors) < 50:
                            self.errors.append(
                                f"reel {code}: {type(exc).__name__}: {str(exc)[:100]}"
                            )
                    if tasks:
                        await asyncio.gather(*tuple(tasks), return_exceptions=True)
                    after = candidates[code].qualifying_metric()
                    if before is None and after is not None:
                        diagnostic["detail_pages_with_metrics"] += 1
                    else:
                        diagnostic["detail_pages_without_metrics"] += 1

            if tasks:
                await asyncio.gather(*tuple(tasks), return_exceptions=True)

            diagnostic["candidate_count"] = len(candidates)
            diagnostic["metric_count"] = sum(
                item.qualifying_metric() is not None for item in candidates.values()
            )
            if self.blocked:
                diagnostic["reason"] = diagnostic["reason"] or (
                    "Instagram login/checkpoint or rate-limit restriction"
                )
            elif not candidates:
                if diagnostic["http_json_responses"] == 0:
                    diagnostic["reason"] = (
                        "No Instagram JSON responses or rendered Reel links; "
                        "check profile/hashtag availability and manual login"
                    )
                elif diagnostic["responses_with_reels"] == 0:
                    diagnostic["reason"] = (
                        "Responses arrived but no recognized Reel records; "
                        "inspect the saved response-shape diagnostics"
                    )
                else:
                    diagnostic["reason"] = "No Reel links rendered during bounded scrolling"
            elif diagnostic["metric_count"] == 0:
                diagnostic["reason"] = (
                    "Reel links were collected, but the sampled detail pages exposed no "
                    "explicit numeric plays/views metric"
                )
        except Exception as exc:
            diagnostic["reason"] = f"{type(exc).__name__}: {str(exc)[:180]}"
            if any(token in diagnostic["reason"].casefold() for token in (
                "checkpoint", "challenge", "login", "429", "403", "captcha"
            )):
                self.blocked = True
                diagnostic["login_or_checkpoint"] = True
            if len(self.errors) < 50:
                self.errors.append(f"{surface} {creator_handle}: {diagnostic['reason']}")
            if not self.blocked:
                raise
        finally:
            if tasks:
                await asyncio.gather(*tuple(tasks), return_exceptions=True)
            diagnostic["candidate_count"] = len(candidates)
            diagnostic["metric_count"] = sum(
                item.qualifying_metric() is not None for item in candidates.values()
            )
            try:
                if not page.is_closed():
                    await page.close()
            except Exception as exc:
                # The browser may have exited between the is_closed check and
                # close(). Keep harvested candidates and retain a diagnostic.
                if len(self.errors) < 50:
                    self.errors.append(
                        f"{surface} {creator_handle}: page cleanup: "
                        f"{type(exc).__name__}: {str(exc)[:100]}"
                    )

        return list(candidates.values()), coauthors, diagnostic

    async def harvest_creator(
        self,
        username: str,
        *,
        max_scrolls: int = 8,
        max_reel_details: int = 5,
    ) -> tuple[list[DiscoveredCandidate], set[str]]:
        if self.blocked:
            raise RuntimeError("Instagram backend is blocked; stopping without further requests.")
        handle = username.strip().lstrip("@").casefold()
        if not handle or "/" in handle or " " in handle:
            raise ValueError(f"Invalid Instagram username: {username!r}")
        try:
            records, coauthors, diagnostic = await self._collect_surface(
                url=f"https://www.instagram.com/{quote(handle, safe='.')}/reels/",
                creator_handle=handle,
                surface="creator_reels_tab",
                hashtag=None,
                max_scrolls=max_scrolls,
                max_reel_details=max_reel_details,
            )
        except Exception as exc:
            self.creator_diagnostics.append({
                "surface": "creator_reels_tab",
                "handle": handle,
                "requested_url": f"https://www.instagram.com/{quote(handle, safe='.')}/reels/",
                "candidate_count": 0,
                "metric_count": 0,
                "reason": f"{type(exc).__name__}: {str(exc)[:180]}",
            })
            raise
        self.creator_diagnostics.append(diagnostic)
        if self.blocked:
            raise RuntimeError(diagnostic.get("reason") or "Instagram access restriction")
        return records, coauthors

    async def harvest_hashtag(
        self,
        hashtag: str,
        *,
        max_scrolls: int = 8,
        max_reel_details: int = 10,
    ) -> list[DiscoveredCandidate]:
        if self.blocked:
            raise RuntimeError("Instagram backend is blocked; stopping without further requests.")
        tag = hashtag.strip().lstrip("#").casefold()
        if not tag or not re.fullmatch(r"[\w.]{1,64}", tag, flags=re.UNICODE):
            raise ValueError(f"Invalid Instagram hashtag: {hashtag!r}")
        try:
            records, _, diagnostic = await self._collect_surface(
                url=f"https://www.instagram.com/explore/tags/{quote(tag, safe='.')}/",
                creator_handle=f"hashtag:{tag}",
                surface="hashtag_page",
                hashtag=tag,
                max_scrolls=max_scrolls,
                max_reel_details=max_reel_details,
            )
        except Exception as exc:
            self.hashtag_diagnostics.append({
                "surface": "hashtag_page",
                "hashtag": tag,
                "requested_url": f"https://www.instagram.com/explore/tags/{quote(tag, safe='.')}/",
                "candidate_count": 0,
                "metric_count": 0,
                "reason": f"{type(exc).__name__}: {str(exc)[:180]}",
            })
            raise
        self.hashtag_diagnostics.append(diagnostic)
        if self.blocked:
            raise RuntimeError(diagnostic.get("reason") or "Instagram access restriction")
        return records
