from __future__ import annotations

import sys
from types import ModuleType

from shorts_intelligence.discovery.downloader import _download_with_ytdlp
from shorts_intelligence.discovery.models import DiscoveredCandidate


def test_downloader_prefers_node_runtime_when_node_is_available(monkeypatch, tmp_path):
    candidate = DiscoveredCandidate(
        platform="youtube",
        source_id="NodeRuntime01",
        canonical_url="https://www.youtube.com/shorts/NodeRuntime01",
        short_format_status="confirmed",
    )
    captured = {}
    node_path = r"C:\Program Files\nodejs\node.exe"
    monkeypatch.setattr(
        "shorts_intelligence.discovery.downloader.shutil.which",
        lambda name: node_path if name == "node" else None,
    )

    class FakeYoutubeDL:
        def __init__(self, options):
            captured["options"] = options

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def extract_info(self, url, download=True):
            assert url == str(candidate.canonical_url)
            assert download is True
            media_path = tmp_path / f"{candidate.source_id}.mp4"
            media_path.write_bytes(b"fake-mp4")
            return {
                "id": candidate.source_id,
                "requested_downloads": [{"filepath": str(media_path)}],
            }

        def prepare_filename(self, info):
            return str(tmp_path / f"{info['id']}.mp4")

    module = ModuleType("yt_dlp")
    module.YoutubeDL = FakeYoutubeDL
    monkeypatch.setitem(sys.modules, "yt_dlp", module)

    result = _download_with_ytdlp(candidate, tmp_path)

    assert result.is_file()
    assert captured["options"]["js_runtimes"] == {
        "node": {"path": node_path}
    }
