from __future__ import annotations

import sys
from types import ModuleType

from shorts_intelligence.discovery.providers import YouTubeSearchProvider


class FakeYoutubeDL:
    instances: list[FakeYoutubeDL] = []

    def __init__(self, options):
        self.options = options
        self.calls = 0
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def extract_info(self, query, download=False):
        self.calls += 1
        assert query.startswith("ytsearch")
        assert download is False
        return {
            "entries": [
                {
                    "id": "AbCdEfGh123",
                    "webpage_url": "https://www.youtube.com/watch?v=AbCdEfGh123",
                    "title": "A popular vertical short",
                    "duration": 32,
                    "upload_date": "20251101",
                    "width": 1080,
                    "height": 1920,
                    "view_count": 1_450_000,
                },
                {
                    "id": "AbCdEfGh123",
                    "webpage_url": "https://www.youtube.com/watch?v=AbCdEfGh123",
                    "title": "Duplicate result",
                    "duration": 32,
                    "upload_date": "20251101",
                    "width": 1080,
                    "height": 1920,
                    "view_count": 1_450_000,
                },
            ]
        }


def test_youtube_search_uses_flat_playlist_mode_and_deduplicates(monkeypatch, capsys):
    FakeYoutubeDL.instances.clear()
    fake_module = ModuleType("yt_dlp")
    fake_module.YoutubeDL = FakeYoutubeDL
    monkeypatch.setitem(sys.modules, "yt_dlp", fake_module)

    provider = YouTubeSearchProvider()
    candidates = list(provider.search("Indian cricket Shorts", limit=20))

    assert len(candidates) == 1
    assert candidates[0].source_id == "AbCdEfGh123"
    assert candidates[0].view_count == 1_450_000
    assert candidates[0].short_format_status == "confirmed"
    assert provider.search_results_seen == 2
    assert FakeYoutubeDL.instances[0].options["extract_flat"] == "in_playlist"
    assert FakeYoutubeDL.instances[0].calls == 1
    captured = capsys.readouterr()
    assert "This video is not available" not in captured.out
    assert "This video is not available" not in captured.err


def test_youtube_search_logger_collects_errors_without_printing(monkeypatch, capsys):
    class ErrorYoutubeDL(FakeYoutubeDL):
        def extract_info(self, query, download=False):
            self.calls += 1
            self.options["logger"].error("[youtube] deadbeef: This video is not available")
            return {"entries": []}

    fake_module = ModuleType("yt_dlp")
    fake_module.YoutubeDL = ErrorYoutubeDL
    monkeypatch.setitem(sys.modules, "yt_dlp", fake_module)

    provider = YouTubeSearchProvider()
    assert list(provider.search("Hindi comedy Shorts", limit=10)) == []
    assert provider.errors == ["[youtube] deadbeef: This video is not available"]
    captured = capsys.readouterr()
    assert "This video is not available" not in captured.out
    assert "This video is not available" not in captured.err
