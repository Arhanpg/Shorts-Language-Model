"""Visible, user-session Instagram Reels collector.

The user signs in manually in a dedicated Chrome profile. This adapter navigates
ordinary public profile/Reels pages and observes their normal browser responses
and rendered Reel links. It never constructs/replays private requests.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from shorts_intelligence.discovery.models import DiscoveredCandidate

_CODE = re.compile(r"^[A-Za-z0-9_-]{5,}$")
_REEL_PATH = re.compile(r"/reel/([A-Za-z0-9_-]{5,})/?")
_NUMERIC_COUNT = re.compile(r"^\s*[0-9][0-9,]*\s*$")


def _raw_count(value: object) -> int | None:
    """Accept raw integer/numeric-string counts, never display abbreviations like 1.2M."""
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


def extract_reel_records(
    payload: object, *, creator_handle: str
) -> list[DiscoveredCandidate]:
    """Extract Reel candidates from observed JSON without guessing view counts."""
    found: dict[str, DiscoveredCandidate] = {}

    def walk(value: object) -> None:
        if isinstance(value, dict):
            code = value.get("code") or value.get("shortcode")
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
                plays = _raw_count(value.get("play_count"))
                if plays is None:
                    plays = _raw_count(value.get("video_play_count"))
                views = _raw_count(value.get("view_count"))
                coauthors = value.get("coauthor_producers") or []
                handles = [
                    str(item.get("username")).strip().lstrip("@").casefold()
                    for item in coauthors
                    if isinstance(item, dict) and item.get("username")
                ] if isinstance(coauthors, list) else []
                found[code] = DiscoveredCandidate(
                    platform="instagram",
                    source_id=code,
                    canonical_url=f"https://www.instagram.com/reel/{code}/",
                    creator=creator_handle,
                    view_count=views,
                    play_count=plays,
                    metric_source=(
                        "instagram_response.view_count" if views is not None
                        else "instagram_response.play_count" if plays is not None else None
                    ),
                    short_format_status="confirmed",
                    metadata={
                        "provider": "playwright_response_observer",
                        "metric_kind": (
                            "views" if views is not None
                            else "plays" if plays is not None else "unknown"
                        ),
                        "coauthor_handles": handles,
                        "product_type": product_type or None,
                        "media_type": media_type,
                    },
                )
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return list(found.values())


class InstagramPlaywrightProvider:
    """One visible persistent Chrome profile; sign-in and verification stay manual."""

    def __init__(self, *, profile_dir: Path, timeout_seconds: float = 15.0) -> None:
        self.profile_dir = profile_dir.expanduser().resolve()
        self.timeout_seconds = max(5.0, min(timeout_seconds, 30.0))
        self.requests_observed = 0
        self.responses_parsed = 0
        self.responses_unparsed = 0
        self.errors: list[str] = []
        self.blocked = False
        self.creator_diagnostics: list[dict[str, Any]] = []

    async def harvest_creator(
        self, username: str, *, max_scrolls: int = 8
    ) -> tuple[list[DiscoveredCandidate], set[str]]:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                'Install browser support: pip install -e ".[instagram-browser]" '
                "then run playwright install chromium"
            ) from exc

        handle = username.strip().lstrip("@").casefold()
        if not handle or "/" in handle or " " in handle:
            raise ValueError(f"Invalid Instagram username: {username!r}")

        candidates: dict[str, DiscoveredCandidate] = {}
        handles: set[str] = set()
        diagnostic: dict[str, Any] = {
            "handle": handle,
            "requested_url": f"https://www.instagram.com/{handle}/reels/",
            "final_url": None,
            "page_title": None,
            "http_json_responses": 0,
            "responses_with_reels": 0,
            "responses_without_reels": 0,
            "parse_errors": 0,
            "dom_reel_links": 0,
            "candidate_count": 0,
            "login_or_checkpoint": False,
            "reason": None,
        }
        tasks: set[asyncio.Task[Any]] = set()
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=False,
                channel="chrome",
                viewport={"width": 1365, "height": 900},
            )
            page = await context.new_page()

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
                        if len(self.errors) < 30:
                            self.errors.append(diagnostic["reason"])
                        return
                    payload = await asyncio.wait_for(
                        response.json(), timeout=self.timeout_seconds
                    )
                    records = extract_reel_records(payload, creator_handle=handle)
                    if records:
                        self.responses_parsed += 1
                        diagnostic["responses_with_reels"] += 1
                    else:
                        self.responses_unparsed += 1
                        diagnostic["responses_without_reels"] += 1
                    for candidate in records:
                        candidates[candidate.source_id] = candidate
                        handles.update(candidate.metadata.get("coauthor_handles", []))
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.responses_unparsed += 1
                    diagnostic["parse_errors"] += 1
                    if len(self.errors) < 30:
                        self.errors.append(
                            f"{handle} response: {type(exc).__name__}: {str(exc)[:140]}"
                        )

            def on_response(response: Any) -> None:
                task = asyncio.create_task(parse_response(response))
                tasks.add(task)
                task.add_done_callback(tasks.discard)

            def collect_rendered_links(raw_links: list[str]) -> None:
                for href in raw_links:
                    match = _REEL_PATH.search(href)
                    if not match:
                        continue
                    code = match.group(1)
                    if code in candidates:
                        continue
                    candidates[code] = DiscoveredCandidate(
                        platform="instagram",
                        source_id=code,
                        canonical_url=f"https://www.instagram.com/reel/{code}/",
                        creator=handle,
                        view_count=None,
                        play_count=None,
                        metric_source=None,
                        short_format_status="confirmed",
                        metadata={
                            "provider": "playwright_rendered_reel_link",
                            "metric_kind": "unknown",
                        },
                    )

            page.on("response", on_response)
            try:
                response = await asyncio.wait_for(
                    page.goto(diagnostic["requested_url"], wait_until="domcontentloaded"),
                    timeout=self.timeout_seconds * 2,
                )
                await page.wait_for_timeout(2200)
                diagnostic["final_url"] = page.url
                diagnostic["page_title"] = (await page.title())[:160]
                current_url = page.url.casefold()
                if any(
                    token in current_url
                    for token in ("checkpoint", "challenge", "/accounts/login")
                ):
                    self.blocked = True
                    diagnostic["login_or_checkpoint"] = True
                    diagnostic["reason"] = "Instagram redirected to login/checkpoint/challenge"
                elif response is not None and response.status in {401, 403, 429}:
                    self.blocked = True
                    diagnostic["reason"] = f"Profile page returned HTTP {response.status}"

                if not self.blocked:
                    for _ in range(max(0, min(max_scrolls, 20))):
                        await page.mouse.wheel(0, 1900)
                        await page.wait_for_timeout(1250)
                        links = await page.locator('a[href*="/reel/"]').evaluate_all(
                            "(els) => els.map((el) => el.getAttribute('href')).filter(Boolean)"
                        )
                        collect_rendered_links(links)
                        diagnostic["dom_reel_links"] = len(candidates)
                        if self.blocked:
                            break

                if tasks:
                    await asyncio.gather(*tuple(tasks), return_exceptions=True)

                diagnostic["candidate_count"] = len(candidates)
                if self.blocked:
                    diagnostic["reason"] = diagnostic["reason"] or (
                        "Instagram login/checkpoint or rate-limit restriction"
                    )
                elif not candidates:
                    if diagnostic["http_json_responses"] == 0:
                        diagnostic["reason"] = (
                            "No Instagram JSON responses captured and no rendered Reel links; "
                            "check login state, profile availability, and browser page"
                        )
                    elif diagnostic["responses_with_reels"] == 0:
                        diagnostic["reason"] = (
                            "Instagram responses arrived but no recognized Reel records were parsed; "
                            "response schema may have changed"
                        )
                    else:
                        diagnostic["reason"] = "No Reel links were rendered during this bounded scroll"
            except Exception as exc:
                diagnostic["reason"] = (
                    f"{type(exc).__name__}: {str(exc)[:180]}"
                )
                if any(
                    token in diagnostic["reason"].casefold()
                    for token in ("checkpoint", "challenge", "login", "429", "403", "captcha")
                ):
                    self.blocked = True
                    diagnostic["login_or_checkpoint"] = True
                if len(self.errors) < 30:
                    self.errors.append(f"{handle}: {diagnostic['reason']}")
                if not self.blocked:
                    raise
            finally:
                if tasks:
                    await asyncio.gather(*tuple(tasks), return_exceptions=True)
                diagnostic["candidate_count"] = len(candidates)
                self.creator_diagnostics.append(diagnostic)
                await context.close()

        if self.blocked:
            raise RuntimeError(
                diagnostic["reason"]
                or "Instagram login/checkpoint or HTTP restriction; backend stopped"
            )
        return list(candidates.values()), handles
