"""Passive Instagram Reels response observer using a local Playwright profile.

This adapter observes JSON responses produced by ordinary visible browser navigation.
It does not construct, replay, or modify Instagram requests.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from shorts_intelligence.discovery.models import DiscoveredCandidate

_CODE = re.compile(r"^[A-Za-z0-9_-]{5,}$")

def extract_reel_records(payload: object, *, creator_handle: str) -> list[DiscoveredCandidate]:
    """Extract only records with a Reel identifier and explicit video/Reel evidence."""
    found: dict[str, DiscoveredCandidate] = {}
    def walk(value: object) -> None:
        if isinstance(value, dict):
            code = value.get("code") or value.get("shortcode")
            product_type = str(value.get("product_type") or "").casefold()
            media_type = value.get("media_type")
            is_video = value.get("is_video")
            is_reel = product_type in {"clips", "reels", "reel"} or media_type == 2 or is_video is True
            if isinstance(code, str) and _CODE.fullmatch(code) and is_reel:
                raw_plays = value.get("play_count")
                if raw_plays is None:
                    raw_plays = value.get("video_play_count")
                raw_views = value.get("view_count")
                plays = raw_plays if isinstance(raw_plays, int) and not isinstance(raw_plays, bool) else None
                views = raw_views if isinstance(raw_views, int) and not isinstance(raw_views, bool) else None
                coauthors = value.get("coauthor_producers") or []
                handles = [
                    str(item.get("username")) for item in coauthors
                    if isinstance(item, dict) and item.get("username")
                ] if isinstance(coauthors, list) else []
                found[code] = DiscoveredCandidate(
                    platform="instagram",
                    source_id=code,
                    canonical_url=f"https://www.instagram.com/reel/{code}/",
                    creator=creator_handle,
                    view_count=views,
                    play_count=plays,
                    metric_source=("instagram_response.view_count" if views is not None
                                   else "instagram_response.play_count" if plays is not None else None),
                    short_format_status="confirmed",
                    metadata={
                        "provider": "playwright_response_observer",
                        "metric_kind": "views" if views is not None else "plays" if plays is not None else "unknown",
                        "coauthor_handles": handles,
                        "product_type": product_type or None,
                        "media_type": media_type,
                    })
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(payload)
    return list(found.values())

class InstagramPlaywrightProvider:
    """One visible persistent browser profile; account login is manual."""
    def __init__(self, *, profile_dir: Path, timeout_seconds: float = 15.0) -> None:
        self.profile_dir = profile_dir.expanduser().resolve()
        self.timeout_seconds = max(5.0, min(timeout_seconds, 30.0))
        self.requests_observed = 0
        self.responses_parsed = 0
        self.responses_unparsed = 0
        self.errors: list[str] = []
        self.blocked = False

    async def harvest_creator(self, username: str, *, max_scrolls: int = 4
                              ) -> tuple[list[DiscoveredCandidate], set[str]]:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                'Install browser support: pip install -e ".[instagram-browser]" '
                'then run playwright install chromium') from exc
        candidates: dict[str, DiscoveredCandidate] = {}
        handles: set[str] = set()
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir), headless=False,
                channel="chrome",
                viewport={"width": 1365, "height": 900})
            page = await context.new_page()
            async def observe(response: Any) -> None:
                if response.request.resource_type not in {"xhr", "fetch"}:
                    return
                content_type = response.headers.get("content-type", "").casefold()
                if "json" not in content_type:
                    return
                self.requests_observed += 1
                if response.status in {401, 403, 429}:
                    self.blocked = True
                    if len(self.errors) < 30:
                        self.errors.append(f"Instagram response blocked with HTTP {response.status}")
                    return
                try:
                    payload = await asyncio.wait_for(response.json(), timeout=self.timeout_seconds)
                except Exception as exc:
                    self.responses_unparsed += 1
                    if len(self.errors) < 30:
                        self.errors.append(f"response parse: {type(exc).__name__}: {str(exc)[:160]}")
                    return
                records = extract_reel_records(payload, creator_handle=username)
                self.responses_parsed += bool(records)
                self.responses_unparsed += not bool(records)
                for candidate in records:
                    candidates[candidate.source_id] = candidate
                    handles.update(candidate.metadata.get("coauthor_handles", []))
            page.on("response", observe)
            try:
                await asyncio.wait_for(
                    page.goto(f"https://www.instagram.com/{username.strip('@')}/reels/",
                              wait_until="domcontentloaded"),
                    timeout=self.timeout_seconds * 2)
                await page.wait_for_timeout(2500)
                current_url = page.url.casefold()
                if any(token in current_url for token in ("checkpoint", "challenge", "/accounts/login")):
                    raise RuntimeError(
                        "Instagram login/checkpoint is required. Complete it manually in the browser profile."
                    )
                for _ in range(max(0, min(max_scrolls, 10))):
                    if self.blocked:
                        break
                    await page.mouse.wheel(0, 2200)
                    await page.wait_for_timeout(1800)
            except Exception as exc:
                message = str(exc).casefold()
                if any(token in message for token in ("checkpoint", "challenge", "login")):
                    self.blocked = True
                if len(self.errors) < 30:
                    self.errors.append(f"creator {username}: {type(exc).__name__}: {str(exc)[:180]}")
                if not self.blocked:
                    raise
            finally:
                await context.close()
        if self.blocked:
            raise RuntimeError("Instagram login/checkpoint or HTTP 401/403/429 restriction; backend stopped without retry or fallback.")
        return list(candidates.values()), handles
