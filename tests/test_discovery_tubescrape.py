import sys
from types import SimpleNamespace

from shorts_intelligence.discovery.providers.youtube_tubescrape import TubeScrapeProvider


def test_tubescrape_provider_uses_verified_async_methods(monkeypatch):
    class FakeYouTube:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.closed = False
        async def asearch(self, query, **kwargs):
            assert kwargs["type"] == "short"
            assert kwargs["sort_by"] == "view_count"
            return SimpleNamespace(videos=[SimpleNamespace(video_id="AbCdEfGh123")])
        async def aget_channel_shorts(self, channel, **kwargs):
            assert kwargs["sort_by"] == "popular"
            return SimpleNamespace(shorts=[])
        async def aget_videos_info(self, ids, **kwargs):
            return []
        async def aget_related_shorts(self, video_id, **kwargs):
            return []
        async def aclose(self):
            self.closed = True
    monkeypatch.setitem(sys.modules, "tubescrape", SimpleNamespace(YouTube=FakeYouTube))
    provider = TubeScrapeProvider()
    result = __import__("asyncio").run(provider.search_seed_videos("cricket", limit=10))
    assert result[0].video_id == "AbCdEfGh123"
    assert provider.client.kwargs["max_retries"] == 1
    __import__("asyncio").run(provider.close())
    assert provider.client.closed
