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


def test_youtube_source_url_uses_shorts_tab_without_resolving_handle():
    assert url_collection._youtube_source_url("@creator_name") == (
        "https://www.youtube.com/@creator_name/shorts"
    )
    assert url_collection._youtube_source_url("UC" + "a" * 22) == (
        f"https://www.youtube.com/channel/{'UC' + 'a' * 22}/shorts"
    )
    assert url_collection._youtube_source_url("https://www.youtube.com/@creator") == (
        "https://www.youtube.com/@creator/shorts"
    )


def test_youtube_video_urls_normalizes_flat_entries_and_filters_long_search_results():
    info = {
        "entries": [
            {"id": "abcdefghijk"},
            {"id": "lmnopqrstuv", "duration": 45},
            {"id": "zyxwvutsrqp", "duration": 240},
            {"id": "not-a-video-id"},
            None,
        ]
    }

    assert url_collection._youtube_video_urls(info, source="hashtag") == [
        "https://www.youtube.com/shorts/abcdefghijk",
        "https://www.youtube.com/shorts/lmnopqrstuv",
    ]


def test_youtube_video_urls_keeps_creator_shorts_tab_entries():
    info = {"entries": [{"id": "abcdefghijk"}, {"id": "abcdefghijk"}]}

    assert url_collection._youtube_video_urls(info, source="creator") == [
        "https://www.youtube.com/shorts/abcdefghijk"
    ]


def test_collect_youtube_urls_uses_ytdlp_flat_mode_and_checkpoints(monkeypatch, tmp_path):
    calls = []

    class FakeYoutubeDL:
        def __init__(self, options):
            calls.append(("options", options))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            calls.append((url, download))
            if "missing_creator" in url:
                raise RuntimeError("HTTP Error 404: Not Found")
            if url.startswith("ytsearch"):
                return {"entries": [{"id": "bbbbbbbbbbb", "duration": 30}]}
            return {"entries": [{"id": "aaaaaaaaaaa"}]}

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))
    destination = tmp_path / "exports" / "youtube_shorts.txt"

    counts = url_collection._collect_youtube_urls(
        creators=["@working_creator", "@missing_creator"],
        hashtags=["regional_topic"],
        destination=destination,
        creator_batch_size=1,
        hashtag_batch_size=1,
        per_surface_limit=5,
    )

    lines = destination.read_text(encoding="utf-8").splitlines()
    assert lines == [
        "https://www.youtube.com/shorts/aaaaaaaaaaa",
        "https://www.youtube.com/shorts/bbbbbbbbbbb",
    ]
    options = calls[0][1]
    assert options["skip_download"] is True
    assert options["extract_flat"] == "in_playlist"
    assert options["logger"] is not None
    assert all(download is False for _, download in calls[1:])
    assert counts["creator_surfaces_processed"] == 1
    assert counts["creator_errors"] == 1
    assert counts["creator_404_or_unavailable"] == 1
    assert counts["hashtag_surfaces_processed"] == 1
    assert counts["unique_urls"] == 2


def test_export_urls_deduplicates_and_keeps_existing_urls(monkeypatch, tmp_path):
    class FakeConnection:
        def execute(self, query, params):
            assert params == ("instagram",)

            class Cursor:
                def fetchall(self):
                    return [
                        {"canonical_url": "https://www.instagram.com/reel/ABC123/"},
                        {"canonical_url": "https://www.instagram.com/reel/DEF456/"},
                        {"canonical_url": "https://www.instagram.com/reel/ABC123/"},
                    ]

            return Cursor()

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
