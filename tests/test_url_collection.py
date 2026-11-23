from __future__ import annotations

import csv
import sys
from types import SimpleNamespace

from shorts_intelligence import url_collection


def test_balanced_hashtags_preserves_all_unique_tags(tmp_path):
    source = tmp_path / "hashtags.csv"
    source.write_text(
        "hashtag,language,domain\n"
        "marathi_comedy,mr,comedy\n"
        "hindi_math,hi,education\n"
        "kannada_food,kn,food\n"
        "marathi_comedy,mr,comedy\n",
        encoding="utf-8",
    )

    values = url_collection._balanced_hashtags(source)

    assert set(values) == {"marathi_comedy", "hindi_math", "kannada_food"}
    assert len(values) == 3


def test_resolution_cache_ignores_invalid_channel_ids(tmp_path):
    cache = tmp_path / "resolved.csv"
    with cache.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["reference", "channel_id"])
        writer.writeheader()
        writer.writerow({"reference": "valid", "channel_id": "UC" + "a" * 22})
        writer.writerow({"reference": "invalid", "channel_id": "not-a-channel-id"})

    assert url_collection._load_resolution_cache(cache) == {
        "valid": "UC" + "a" * 22
    }


def test_resolve_youtube_handle_uses_metadata_only_ytdlp(monkeypatch):
    calls = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            calls["options"] = options

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            calls["url"] = url
            calls["download"] = download
            return {"channel_id": "UC" + "b" * 22}

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    assert url_collection._resolve_youtube_channel_id("@sample_creator") == "UC" + "b" * 22
    assert calls["url"] == "https://www.youtube.com/@sample_creator"
    assert calls["download"] is False
    assert calls["options"]["skip_download"] is True


def test_resolve_youtube_channel_id_returns_stable_ids_without_network():
    channel_id = "UC" + "c" * 22

    assert url_collection._resolve_youtube_channel_id(channel_id) == channel_id


def test_export_urls_deduplicates_and_keeps_existing_urls(monkeypatch, tmp_path):
    class FakeConnection:
        def execute(self, query, params):
            assert params == ("instagram",)
            return [
                {"canonical_url": "https://www.instagram.com/reel/ABC123/"},
                {"canonical_url": "https://www.instagram.com/reel/DEF456/"},
                {"canonical_url": "https://www.instagram.com/reel/ABC123/"},
            ]

    class FakeStore:
        def __init__(self, path):
            self.connection = FakeConnection()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(url_collection, "DiscoveryStore", FakeStore)
    destination = tmp_path / "exports" / "instagram_reels.txt"
    destination.parent.mkdir()
    destination.write_text("https://www.instagram.com/reel/OLD123/\n", encoding="utf-8")

    count = url_collection._export_urls(tmp_path / "db.sqlite3", "instagram", destination)

    lines = destination.read_text(encoding="utf-8").splitlines()
    assert count == 3
    assert lines == sorted({
        "https://www.instagram.com/reel/OLD123/",
        "https://www.instagram.com/reel/ABC123/",
        "https://www.instagram.com/reel/DEF456/",
    })
