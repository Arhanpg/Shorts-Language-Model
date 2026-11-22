"""Visible, user-session Instagram Reels discovery.

Uses a single persistent local Chrome context per run. The user signs in manually.
Only ordinary public profile, hashtag and Reel pages are visited; no private
requests are constructed or replayed and no access-control challenge is bypassed.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import re
from decimal import ROUND_FLOOR, Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urlparse

from shorts_intelligence.discovery.models import DiscoveredCandidate

_CODE = re.compile(r"^[A-Za-z0-9_-]{5,}$")
_REEL_PATH = re.compile(r"/reel/([A-Za-z0-9_-]{5,})/?", re.IGNORECASE)
_NUMERIC_COUNT = re.compile(r"^\s*[0-9][0-9,]*\s*$")
_PLAY_FIELDS = (
    "play_count", "video_play_count", "ig_play_count",
    "playCount", "videoPlayCount",
)
_VIEW_FIELDS = (
    "view_count", "video_view_count", "viewCount", "videoViewCount",
)
_DISPLAY_COUNT = re.compile(
    r"(?P<number>(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:[.][0-9]+)?)"
    r"[ ]*(?P<suffix>[KMB])?",
    re.IGNORECASE,
)


def _visible_metric_from_text(
    text: str,
    *,
    allow_bare_count: bool = False,
    bare_kind: str = "views",
) -> dict[str, object] | None:
    """Read a public UI views/plays label; abbreviations remain estimates."""
    cleaned = " ".join(text.split())
    if not cleaned:
        return None

    for match in _DISPLAY_COUNT.finditer(cleaned):
        before = cleaned[:match.start()]
        after = cleaned[match.end():]
        kind = None
        for metric_kind in ("plays", "views"):
            if re.match(r"^[ ]*" + metric_kind + r"?(?:[ ]|$)", after, re.IGNORECASE):
                kind = metric_kind
                break
            if re.search(
                r"(?:^|[ ])" + metric_kind + r"[ ]*[:=-]?[ ]*$",
                before,
                re.IGNORECASE,
            ):
                kind = metric_kind
                break

        token = match.group(0).strip()
        if kind is None and allow_bare_count and _DISPLAY_COUNT.fullmatch(cleaned):
            kind = bare_kind if bare_kind in {"plays", "views"} else "views"
        if kind is None:
            continue

        number_text = match.group("number").replace(",", "")
        suffix = (match.group("suffix") or "").upper()
        try:
            number = Decimal(number_text)
        except InvalidOperation:
            continue
        multiplier = {
            "": Decimal(1),
            "K": Decimal(1_000),
            "M": Decimal(1_000_000),
            "B": Decimal(1_000_000_000),
        }[suffix]
        nominal = number * multiplier
        if nominal < 0:
            continue

        approximate = bool(suffix)
        if approximate:
            decimals = len(number_text.partition(".")[2])
            display_step = multiplier / (Decimal(10) ** decimals)
            lower_bound = max(
                Decimal(0),
                (nominal - display_step / 2).to_integral_value(rounding=ROUND_FLOOR),
            )
        else:
            if number != number.to_integral_value():
                continue
            lower_bound = nominal

        return {
            "kind": kind,
            "display": token,
            "nominal_count": int(nominal),
            "lower_bound": int(lower_bound),
            "is_estimate": approximate,
        }
    return None


def _visible_hover_metric_from_texts(texts: list[str]) -> dict[str, object] | None:
    """Extract labeled counts first, then count-only tokens from a hovered Reel tile.

    Bare values are accepted only as abbreviated K/M/B counts or comma-grouped
    integers. Plain years, caption numbers and likes are not treated as plays.
    """
    for text in texts:
        metric = _visible_metric_from_text(text)
        if metric is not None:
            return metric

    for text in texts:
        for line in text.splitlines():
            token = " ".join(line.split())
            match = _DISPLAY_COUNT.fullmatch(token)
            if match is None:
                continue
            if not match.group("suffix") and "," not in match.group("number"):
                continue
            metric = _visible_metric_from_text(
                token,
                allow_bare_count=True,
                bare_kind="plays",
            )
            if metric is not None:
                return metric
    return None


def instagram_hashtag_keyword_search_url(hashtag: str) -> str:
    """Build the current Instagram keyword-search URL for a hashtag."""
    tag = hashtag.strip().lstrip("#").casefold()
    return "https://www.instagram.com/explore/search/keyword/?" + urlencode({"q": f"#{tag}"})


def _apply_visible_metric(
    candidate: DiscoveredCandidate,
    metric: dict[str, object],
    *,
    source: str,
) -> None:
    """Attach a conservative UI count while preserving its display precision."""
    value = int(metric["lower_bound"])
    kind = str(metric["kind"])
    # Keep rounded UI values out of exact numeric columns. The lower bound is
    # exposed only through qualifying_metric() for conservative discovery.
    if not metric["is_estimate"]:
        if kind == "plays":
            candidate.play_count = value
        else:
            candidate.view_count = value
    candidate.metric_source = source
    candidate.metadata.update({
        "metric_kind": kind,
        "metric_source": source,
        "metric_is_estimate": bool(metric["is_estimate"]),
        "metric_display_value": str(metric["display"]),
        "metric_nominal_value": int(metric["nominal_count"]),
        "metric_conservative_lower_bound": value,
        "metric_precision": "abbreviated_display" if metric["is_estimate"] else "exact_display",
        "metric_usage": "discovery_filter_only; not an exact training label"
        if metric["is_estimate"] else "exact_visible_numeric_count",
    })


def _response_shape(payload: object) -> dict[str, object]:
    """Return bounded schema-only diagnostics without retaining response values."""
    if isinstance(payload, dict):
        top_level = sorted(str(key) for key in payload)[:24]
    else:
        top_level = [type(payload).__name__]
    media_shapes: list[dict[str, object]] = []
    interesting = {
        "code", "shortcode", "media_code", "permalink", "url",
        "media_type", "product_type", "is_reel", "is_video",
        "is_unified_video", "__typename",
        "video_versions", "clips_metadata", "media_or_ad", "pk", "id",
        "view_count", "video_view_count", "play_count", "video_play_count",
    }

    def walk(value: object, depth: int = 0) -> None:
        if len(media_shapes) >= 8 or depth > 8:
            return
        if isinstance(value, dict):
            keys = {str(key) for key in value}
            signals = sorted(keys.intersection(interesting))
            if signals:
                media_shapes.append({
                    "keys": sorted(keys)[:32],
                    "signals": signals,
                    "typename": str(value.get("__typename") or "")[:80] or None,
                })
            for child in value.values():
                walk(child, depth + 1)
        elif isinstance(value, list):
            for child in value[:30]:
                walk(child, depth + 1)

    walk(payload)
    return {"top_level_keys": top_level, "media_like_objects": media_shapes}


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
            if not isinstance(code, str):
                permalink = (
                    value.get("permalink") or value.get("url")
                    or value.get("canonical_url")
                )
                link_match = _REEL_PATH.search(permalink) if isinstance(permalink, str) else None
                code = link_match.group(1) if link_match else None
            product_type = str(value.get("product_type") or "").casefold()
            media_type = value.get("media_type")
            media_type_text = str(media_type or "").casefold()
            if isinstance(media_type, str) and media_type.isdigit():
                media_type = int(media_type)
            typename = str(value.get("__typename") or value.get("typename") or "").casefold()
            is_reel = (
                product_type in {"clips", "reels", "reel"}
                or media_type == 2
                or media_type_text in {"video", "graphvideo", "clips", "reel", "reels"}
                or "graphvideo" in typename
                or "clip" in typename
                or "reel" in typename
                or value.get("is_reel") is True
                or value.get("is_video") is True
                or value.get("is_unified_video") is True
                or isinstance(value.get("clips_metadata"), dict)
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
                    direct_text = caption_value.get("text")
                    if isinstance(direct_text, str):
                        caption_value = direct_text
                    else:
                        edges = caption_value.get("edges")
                        caption_value = None
                        if isinstance(edges, list):
                            for edge in edges:
                                node = edge.get("node") if isinstance(edge, dict) else None
                                if isinstance(node, dict) and isinstance(node.get("text"), str):
                                    caption_value = node["text"]
                                    break
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
                        "instagram_typename": typename or None,
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
        self._page: Any = None

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
            # Keep the persistent context's initial tab alive. Closing the
            # only tab and recreating one for each surface is unreliable with
            # installed Chrome on Windows (Target.createTarget failures).
            self._page = next(
                (page for page in self._context.pages if not page.is_closed()),
                None,
            )
        except Exception as exc:
            playwright = self._playwright
            self._context = None
            self._page = None
            self._playwright = None
            if playwright is not None:
                with contextlib.suppress(Exception):
                    await playwright.stop()
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
        self._page = None
        self._playwright = None
        if context is not None:
            with contextlib.suppress(Exception):
                await context.close()
        if playwright is not None:
            with contextlib.suppress(Exception):
                await playwright.stop()

    async def _ensure_page(self) -> Any:
        """Return a live tab, preferring the persistent context's existing tab."""
        context = await self._ensure_context()
        if self._page is not None:
            try:
                if not self._page.is_closed():
                    return self._page
            except Exception:
                self._page = None

        try:
            open_pages = [
                page for page in context.pages
                if not page.is_closed()
            ]
        except Exception:
            open_pages = []
        if open_pages:
            self._page = open_pages[0]
            return self._page

        # Only create a tab when the persistent context genuinely has none.
        try:
            self._page = await context.new_page()
            return self._page
        except Exception as exc:
            message = str(exc).casefold()
            if any(token in message for token in (
                "targetclosederror",
                "target.createtarget",
                "target page, context or browser has been closed",
                "browser has been closed",
            )):
                await self.close()
                context = await self._ensure_context()
                try:
                    open_pages = [
                        page for page in context.pages
                        if not page.is_closed()
                    ]
                except Exception:
                    open_pages = []
                if open_pages:
                    self._page = open_pages[0]
                    return self._page
                try:
                    self._page = await context.new_page()
                    return self._page
                except Exception as retry_exc:
                    raise RuntimeError(
                        "Instagram Chrome started without an available tab. Close all "
                        "Chrome windows using the dedicated Instagram profile, check "
                        "Task Manager for leftover chrome.exe processes, and retry. "
                        "The collector will reuse the profile and will not delete it."
                    ) from retry_exc
            raise RuntimeError(
                "Could not obtain an Instagram browser tab. Close Chrome windows using "
                "the dedicated Instagram profile and retry."
            ) from exc

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
        page = await self._ensure_page()
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
            "response_shapes": [],
            "dom_metric_count": 0,
            "hovered_reel_cards": 0,
            "hovered_metric_cards": 0,
            "visible_detail_metrics": 0,
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
                if not records and len(diagnostic["response_shapes"]) < 8:
                    diagnostic["response_shapes"].append({
                        "path": parsed_url.path[:180],
                        **_response_shape(payload),
                    })
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

        def collect_rendered_links(raw_links: list[Any]) -> None:
            for entry in raw_links:
                item = entry if isinstance(entry, dict) else {"href": entry}
                href = str(item.get("href") or "")
                match = _REEL_PATH.search(href)
                if not match:
                    continue
                code = match.group(1)
                candidate = candidates.get(code)
                if candidate is None:
                    candidate = DiscoveredCandidate(
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
                    candidates[code] = candidate

                text_fields = [
                    str(item.get("text") or ""),
                    str(item.get("aria_label") or ""),
                    str(item.get("title") or ""),
                    str(item.get("label_text") or ""),
                    str(item.get("card_text") or ""),
                    *[str(value) for value in item.get("ancestor_texts", [])],
                    *[str(value) for value in item.get("leaf_texts", [])],
                ]
                metric = next(
                    (
                        parsed for text in text_fields
                        if (parsed := _visible_metric_from_text(text)) is not None
                    ),
                    None,
                )
                if metric is None:
                    metric = next(
                        (
                            parsed for text in text_fields
                            if (parsed := _visible_metric_from_text(
                                text, allow_bare_count=True
                            )) is not None
                        ),
                        None,
                    )
                if metric is not None and candidate.qualifying_metric() is None:
                    _apply_visible_metric(
                        candidate,
                        metric,
                        source="instagram_rendered_reel_card." + str(metric["kind"]),
                    )
                    diagnostic["dom_metric_count"] += 1

        async def capture_rendered_links() -> None:
            links = await page.locator('a[href*="/reel/"]').evaluate_all(
                "(els) => els.map((el) => {"
                "const ancestorTexts = [];"
                "let node = el;"
                "for (let i = 0; node && i < 5; i += 1, node = node.parentElement) {"
                "const value = (node.innerText || node.textContent || '').trim();"
                "if (value && value.length <= 700) ancestorTexts.push(value);"
                "}"
                "const leafTexts = Array.from(el.querySelectorAll('*'))"
                ".filter((node) => node.children.length === 0 && node.getClientRects().length)"
                ".map((node) => (node.innerText || node.textContent || '').trim())"
                ".filter((value) => value && value.length <= 80);"
                "return {"
                "href: el.getAttribute('href') || '',"
                "text: el.innerText || el.textContent || '',"
                "aria_label: el.getAttribute('aria-label') || '',"
                "title: el.getAttribute('title') || '',"
                "label_text: Array.from(el.querySelectorAll('[aria-label]'))"
                ".map((node) => node.getAttribute('aria-label') || '').join(' '),"
                "card_text: (el.closest('article') || el.parentElement?.parentElement)?.innerText || '',"
                "ancestor_texts: ancestorTexts,"
                "leaf_texts: leafTexts"
                "};"
                "})"
            )
            collect_rendered_links(links)
            diagnostic["dom_reel_links"] = sum(
                item.metadata.get("provider") == "playwright_rendered_reel_link"
                for item in candidates.values()
            )

        hovered_codes: set[str] = set()
        hover_budget = min(max(0, max_reel_details) * 3, 30)

        async def hover_visible_reel_cards() -> None:
            """Hover Reel tiles so Instagram can render its view-count overlay."""
            if hover_budget <= 0:
                return
            for code, candidate in list(candidates.items()):
                if diagnostic["hovered_reel_cards"] >= hover_budget:
                    break
                if code in hovered_codes or candidate.qualifying_metric() is not None:
                    continue
                if candidate.metadata.get("provider") != "playwright_rendered_reel_link":
                    continue
                hovered_codes.add(code)
                anchor = page.locator(f'a[href*="/reel/{code}/"]').first
                try:
                    await anchor.hover(timeout=1200)
                    await page.wait_for_timeout(300)
                    hovered = await anchor.evaluate(
                        "(el) => {"
                        "const ancestorTexts = [];"
                        "let node = el;"
                        "for (let i = 0; node && i < 5; i += 1, node = node.parentElement) {"
                        "const value = (node.innerText || node.textContent || '').trim();"
                        "if (value && value.length <= 700) ancestorTexts.push(value);"
                        "}"
                        "const leafTexts = Array.from(el.querySelectorAll('*'))"
                        ".filter((node) => node.children.length === 0 && node.getClientRects().length)"
                        ".map((node) => (node.innerText || node.textContent || '').trim())"
                        ".filter((value) => value && value.length <= 80);"
                        "return {"
                        "text: el.innerText || el.textContent || '',"
                        "aria_label: el.getAttribute('aria-label') || '',"
                        "title: el.getAttribute('title') || '',"
                        "label_text: Array.from(el.querySelectorAll('[aria-label]'))"
                        ".map((node) => node.getAttribute('aria-label') || '').join(' '),"
                        "ancestor_texts: ancestorTexts,"
                        "leaf_texts: leafTexts"
                        "};"
                        "}"
                    )
                    diagnostic["hovered_reel_cards"] += 1
                    values = [
                        str(hovered.get("text") or ""),
                        str(hovered.get("aria_label") or ""),
                        str(hovered.get("title") or ""),
                        str(hovered.get("label_text") or ""),
                        *[str(value) for value in hovered.get("ancestor_texts", [])],
                        *[str(value) for value in hovered.get("leaf_texts", [])],
                    ]
                    metric = _visible_hover_metric_from_texts(values)
                    if metric is not None and candidate.qualifying_metric() is None:
                        _apply_visible_metric(
                            candidate,
                            metric,
                            source="instagram_reel_hover_overlay." + str(metric["kind"]),
                        )
                        candidate.metadata["metric_hovered"] = True
                        diagnostic["hovered_metric_cards"] += 1
                except Exception as exc:
                    if len(self.errors) < 50:
                        self.errors.append(
                            f"hover reel {code}: {type(exc).__name__}: {str(exc)[:100]}"
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
                # Capture the initially rendered cards as well as subsequent
                # scroll batches; hashtag pages often load a useful first row
                # before the first wheel event.
                await capture_rendered_links()
                await hover_visible_reel_cards()
                previous_count = -1
                stable_rounds = 0
                for _ in range(max(0, min(max_scrolls, 20))):
                    await page.mouse.wheel(0, 1750)
                    await page.wait_for_timeout(1100)
                    await capture_rendered_links()
                    await hover_visible_reel_cards()
                    current_count = len(candidates)
                    stable_rounds = stable_rounds + 1 if current_count == previous_count else 0
                    previous_count = current_count
                    if stable_rounds >= 3:
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
                        target = candidates[code]
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
                                if kind == "plays":
                                    target.play_count = count
                                else:
                                    target.view_count = count
                                target.metric_source = source
                                target.metadata["metric_kind"] = kind
                                target.metadata["metric_source"] = source
                                target.metadata["metric_detail_enriched"] = True

                        # Logged-in public Reel pages do not always expose
                        # JSON-LD. Read only rendered body text and public
                        # description meta tags; never inspect private app state.
                        visible_texts: list[str] = []
                        meta_locator = page.locator(
                            'meta[name="description"], meta[property="og:description"]'
                        )
                        with contextlib.suppress(Exception):
                            visible_texts.extend(await meta_locator.evaluate_all(
                                "(els) => els.map((el) => el.getAttribute('content') || '')"
                            ))
                        with contextlib.suppress(Exception):
                            visible_texts.append(
                                await page.locator("body").inner_text(timeout=1800)
                            )
                        for visible_text in visible_texts:
                            visible_metric = _visible_metric_from_text(visible_text)
                            if visible_metric is not None:
                                _apply_visible_metric(
                                    target,
                                    visible_metric,
                                    source="instagram_reel_detail_visible_text."
                                    + str(visible_metric["kind"]),
                                )
                                target.metadata["metric_detail_enriched"] = True
                                diagnostic["visible_detail_metrics"] += 1
                                break
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
            # Detach this surface's response handler before the shared tab is
            # navigated for the next hashtag/profile. Keep the tab open for the
            # full run; the provider closes it with the persistent context.
            with contextlib.suppress(Exception):
                page.remove_listener("response", on_response)
            if tasks:
                await asyncio.gather(*tuple(tasks), return_exceptions=True)
            diagnostic["candidate_count"] = len(candidates)
            diagnostic["metric_count"] = sum(
                item.qualifying_metric() is not None for item in candidates.values()
            )
            try:
                if page.is_closed():
                    self._page = None
            except Exception:
                self._page = None

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
                url=instagram_hashtag_keyword_search_url(tag),
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
                "requested_url": instagram_hashtag_keyword_search_url(tag),
                "candidate_count": 0,
                "metric_count": 0,
                "reason": f"{type(exc).__name__}: {str(exc)[:180]}",
            })
            raise
        self.hashtag_diagnostics.append(diagnostic)
        if self.blocked:
            raise RuntimeError(diagnostic.get("reason") or "Instagram access restriction")
        return records
