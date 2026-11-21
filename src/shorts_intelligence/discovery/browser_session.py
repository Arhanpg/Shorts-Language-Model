"""Locate the user's installed Google Chrome for manual browser sessions.

Manual sign-in deliberately runs outside Playwright automation. Playwright is used
later, with the same persistent profile, only for the user's requested collection.
"""
from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path


def find_chrome_executable(explicit_path: Path | None = None) -> Path:
    """Return an existing Google Chrome executable or raise an actionable error."""
    if explicit_path is not None:
        candidate = explicit_path.expanduser().resolve()
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"Chrome executable does not exist: {candidate}")

    for command in ("chrome", "google-chrome", "google-chrome-stable"):
        located = shutil.which(command)
        if located:
            return Path(located).resolve()

    system = platform.system()
    candidates: list[Path] = []
    if system == "Windows":
        for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            root = os.environ.get(variable)
            if root:
                candidates.append(
                    Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe"
                )
    elif system == "Darwin":
        candidates.append(
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        )
        home = Path.home()
        candidates.append(
            home / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        )
    else:
        for command in ("chromium", "chromium-browser"):
            located = shutil.which(command)
            if located:
                candidates.append(Path(located).resolve())

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    raise FileNotFoundError(
        "Google Chrome was not found. Install Google Chrome, or pass its executable "
        "path with --chrome-path. The login step uses ordinary Chrome so verification "
        "is completed manually rather than inside an automated Playwright browser."
    )
