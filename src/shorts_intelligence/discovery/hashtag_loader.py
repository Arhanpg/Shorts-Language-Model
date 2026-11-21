"""Load and normalize repeatable Instagram hashtag discovery seeds."""
from __future__ import annotations

import re
from pathlib import Path

_HASHTAG = re.compile(r"^[\w.]{1,64}$", re.UNICODE)


def normalize_instagram_hashtag(value: str) -> str | None:
    tag = value.strip().lstrip("#").casefold()
    if not tag or not _HASHTAG.fullmatch(tag):
        return None
    return tag


def load_instagram_hashtags(
    path: Path, *, explicit_hashtags: list[str] | None = None
) -> list[str]:
    # Explicit CLI hashtags go first so max-hashtags respects the user's selection.
    values: list[str] = list(explicit_hashtags or [])
    if path.expanduser().is_file():
        values.extend(path.expanduser().read_text(encoding="utf-8-sig").splitlines())
    unique: dict[str, None] = {}
    for value in values:
        if value.strip() and not value.lstrip().startswith("# "):
            tag = normalize_instagram_hashtag(value)
            if tag:
                unique.setdefault(tag, None)
    return list(unique)
