from pathlib import Path

import pytest

from shorts_intelligence.discovery.browser_session import find_chrome_executable


def test_find_chrome_accepts_explicit_existing_executable(tmp_path):
    executable = tmp_path / "chrome.exe"
    executable.write_text("placeholder", encoding="utf-8")
    assert find_chrome_executable(executable) == executable.resolve()


def test_find_chrome_rejects_missing_explicit_executable(tmp_path):
    with pytest.raises(FileNotFoundError, match="does not exist"):
        find_chrome_executable(tmp_path / "missing-chrome.exe")


def test_find_chrome_uses_windows_install_locations(monkeypatch, tmp_path):
    executable = tmp_path / "Google" / "Chrome" / "Application" / "chrome.exe"
    executable.parent.mkdir(parents=True)
    executable.write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr("shorts_intelligence.discovery.browser_session.shutil.which", lambda _: None)
    monkeypatch.setattr("shorts_intelligence.discovery.browser_session.platform.system", lambda: "Windows")
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert find_chrome_executable() == executable.resolve()
