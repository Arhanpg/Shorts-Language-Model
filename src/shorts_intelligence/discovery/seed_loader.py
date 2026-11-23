"""Load a curated, human-reviewable Instagram creator seed file."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

_HANDLE = re.compile(r"^[A-Za-z0-9._]{1,30}$")


def normalize_instagram_handle(value: str) -> str | None:
    """Normalize @handle or Instagram profile URL into a bare username."""
    text = value.strip()
    if not text or text.startswith("#"):
        return None
    if "instagram.com" in text.casefold():
        parsed = urlparse(text if "://" in text else f"https://{text}")
        parts = [part for part in parsed.path.split("/") if part]
        if not parts or parts[0].casefold() in {
            "p", "reel", "reels", "stories", "explore", "accounts"
        }:
            return None
        text = parts[0]
    text = text.strip().lstrip("@").rstrip("/").casefold()
    if not _HANDLE.fullmatch(text):
        return None
    return text


def load_instagram_creator_seeds(
    path: Path, *, explicit_handles: list[str] | None = None
) -> list[str]:
    """Load one handle per line, merge CLI handles, preserve order and deduplicate."""
    # Explicit CLI handles go first so a small --max-creators smoke test
    # always tests the handles the user named, not the first entries in the file.
    values: list[str] = list(explicit_handles or [])
    if path.expanduser().is_file():
        values.extend(path.expanduser().read_text(encoding="utf-8-sig").splitlines())
    unique: dict[str, None] = {}
    for value in values:
        handle = normalize_instagram_handle(value)
        if handle:
            unique.setdefault(handle, None)
    return list(unique)


_YOUTUBE_CHANNEL_ID = re.compile(r"^UC[A-Za-z0-9_-]{22}$")


def load_youtube_channel_seeds(path: Path) -> list[str]:
    """Load stable YouTube channel IDs only; handle-only leads are not guessed."""
    if not path.expanduser().is_file():
        return []
    values = path.expanduser().read_text(encoding="utf-8-sig").splitlines()
    unique: dict[str, None] = {}
    for value in values:
        channel_id = value.strip()
        if _YOUTUBE_CHANNEL_ID.fullmatch(channel_id):
            unique.setdefault(channel_id, None)
    return list(unique)
