from __future__ import annotations

import sys
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace

from shorts_intelligence.discovery.providers import (
    InstagramSearchProvider,
    YouTubeSearchProvider,
)


def _fake_ytscrape(monkeypatch):
    class FakeSearchFilter:
        SHORTS = "shorts"

    class FakeRateLimited(Exception):
        pass

    class FakeBotDetected(Exception):
        pass

    class FakeRetryPolicy:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeYouTube:
        instances = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.search_calls = []
            self.video_calls = []
            self.closed = False
            self.__class__.instances.append(self)

        def search(self, query, *, filter, max_results):
            self.search_calls.append((query, filter, max_results))
            return [
                SimpleNamespace(
                    video_id="AbCdEfGh123",
                    title="Cricket finish #cricket",
                    channel="Sports Creator",
                    channel_id="UC" + "a" * 22,
                    description="Last ball #shorts",
                    duration="0:45",
                    views=1_450_000,
                    views_text="1.45M views",
                    published_text="2 days ago",
                    published_at=datetime(2026, 11, 19, tzinfo=UTC),
                    thumbnail="https://example.invalid/thumb.jpg",
                ),
                SimpleNamespace(
                    video_id="AbCdEfGh123",
                    title="Duplicate result",
                    channel="Sports Creator",
                    channel_id=None,
                    description=None,
                    duration="0:45",
                    views=1_450_000,
                    views_text="1.45M views",
                    published_text=None,
                    published_at=None,
                    thumbnail=None,
                ),
            ]

        def video(self, source_id):
            self.video_calls.append(source_id)
            return SimpleNamespace(
                views=1_500_000,
                length_seconds=45,
                title="Detailed cricket finish",
                description="Full detail #cricket",
                channel="Sports Creator",
                upload_date="20261119",
                published_at=datetime(2026, 11, 19, tzinfo=UTC),
                channel_id="UC" + "a" * 22,
                category="Sports",
            )

        def close(self):
            self.closed = True

    fake_module = ModuleType("ytscrape")
    fake_module.SearchFilter = FakeSearchFilter
    fake_module.RetryPolicy = FakeRetryPolicy
    fake_module.RateLimited = FakeRateLimited
    fake_module.BotDetected = FakeBotDetected
    fake_module.YouTube = FakeYouTube
    monkeypatch.setitem(sys.modules, "ytscrape", fake_module)
    return FakeYouTube


def test_youtube_provider_uses_shorts_filter_and_deduplicates(monkeypatch):
    FakeYouTube = _fake_ytscrape(monkeypatch)
    FakeYouTube.instances.clear()
    provider = YouTubeSearchProvider(request_timeout=9, request_interval=1.1)

    results = list(
        provider.search(
            "cricket shorts",
            limit=25,
            language="hi",
            region="IN",
        )
    )

    assert len(results) == 1
    assert results[0].source_id == "AbCdEfGh123"
    assert results[0].view_count == 1_450_000
    assert results[0].duration_seconds == 45
    assert results[0].short_format_status == "confirmed"
    assert results[0].metadata["search_filter"] == "shorts"
    assert results[0].metadata["search_language"] == "hi"
    assert provider.search_results_seen == 2

    client = FakeYouTube.instances[0]
    assert client.kwargs["language"] == "hi"
    assert client.kwargs["region"] == "IN"
    assert client.kwargs["timeout"] == 9
    assert client.kwargs["min_interval"] == 1.1
    assert client.search_calls == [("cricket shorts", "shorts", 25)]


def test_youtube_provider_reuses_locale_client(monkeypatch):
    FakeYouTube = _fake_ytscrape(monkeypatch)
    FakeYouTube.instances.clear()
    provider = YouTubeSearchProvider()

    list(provider.search("cricket shorts", language="en", region="IN", limit=10))
    list(provider.search("comedy shorts", language="en", region="IN", limit=10))

    assert len(FakeYouTube.instances) == 1
    assert len(FakeYouTube.instances[0].search_calls) == 2
    provider.close()
    assert FakeYouTube.instances[0].closed is True


def test_youtube_metadata_enrichment_is_bounded_and_merges_fields(monkeypatch):
    FakeYouTube = _fake_ytscrape(monkeypatch)
    FakeYouTube.instances.clear()
    provider = YouTubeSearchProvider(detail_enrichment_limit=1)
    candidate = list(
        provider.search("cricket shorts", language="en", region="IN", limit=10)
    )[0].model_copy(update={"view_count": None, "duration_seconds": None})

    enriched = provider.enrich(candidate, language="en", region="IN")
    assert enriched.view_count == 1_500_000
    assert enriched.duration_seconds == 45
    assert enriched.title == "Cricket finish #cricket"
    assert enriched.metadata["detail_enriched"] is True
    assert provider.enrichment_attempts == 1
    assert provider.enrichment_successes == 1
    assert FakeYouTube.instances[0].video_calls == ["AbCdEfGh123"]

    unchanged = provider.enrich(candidate, language="en", region="IN")
    assert unchanged.view_count is None
    assert provider.enrichment_attempts == 1
    provider.close()


def _fake_instaloader(monkeypatch, post_factory):
    class FakeInstaloader:
        instances = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.context = object()
            self.closed = False
            self.__class__.instances.append(self)

        def close(self):
            self.closed = True

    class FakePost:
        @staticmethod
        def from_shortcode(context, shortcode):
            return post_factory(shortcode)

    module = ModuleType("instaloader")
    module.Instaloader = FakeInstaloader
    module.Post = FakePost
    monkeypatch.setitem(sys.modules, "instaloader", module)
    return FakeInstaloader


def _fake_ddgs(monkeypatch, result_urls):
    class FakeDDGS:
        instances = []

        def __init__(self, timeout=None):
            self.timeout = timeout
            self.calls = []
            self.__class__.instances.append(self)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def text(self, query, **kwargs):
            self.calls.append((query, kwargs))
            if kwargs["backend"] == "broken":
                raise TimeoutError("operation timed out")
            return [{"href": url} for url in result_urls]

    module = ModuleType("ddgs")
    module.DDGS = FakeDDGS
    monkeypatch.setitem(sys.modules, "ddgs", module)
    return FakeDDGS


def _fake_post(shortcode):
    return SimpleNamespace(
        is_video=True,
        shortcode=shortcode,
        caption="Cricket #cricket #shorts",
        title=None,
        owner_username="creator",
        video_view_count=1_200_000,
        video_play_count=None,
        video_duration=20.0,
        date_utc=datetime(2026, 11, 19, tzinfo=UTC),
        caption_hashtags=["cricket", "shorts"],
        likes=1000,
        comments=20,
        typename="GraphVideo",
    )


def test_instagram_provider_uses_bounded_timeouts_and_metadata(monkeypatch):
    urls = [
        "https://www.instagram.com/reel/ABCxyz_123/",
        "https://www.instagram.com/reel/DEFxyz_456/",
    ]
    FakeDDGS = _fake_ddgs(monkeypatch, urls)
    FakeLoader = _fake_instaloader(monkeypatch, _fake_post)
    monkeypatch.setattr("shorts_intelligence.discovery.providers.time.sleep", lambda _: None)

    provider = InstagramSearchProvider(
        region="in-en",
        backend="bing,brave",
        request_timeout=10,
        search_timeout=7,
        max_connection_attempts=1,
        request_pause_seconds=1,
        max_lookups=5,
    )
    results = list(provider.search("site:instagram.com/reel/ cricket", limit=10))

    assert len(results) == 2
    assert all(item.view_count == 1_200_000 for item in results)
    assert provider.metadata_lookups == 2
    assert provider.metadata_successes == 2
    assert provider.circuit_open is False
    assert FakeDDGS.instances[0].timeout == 7
    assert FakeDDGS.instances[0].calls[0][1]["backend"] == "bing,brave"
    assert FakeLoader.instances[0].kwargs["request_timeout"] == 10
    assert FakeLoader.instances[0].kwargs["max_connection_attempts"] == 1
    assert FakeLoader.instances[0].kwargs["fatal_status_codes"] == [401, 403, 429]
    provider.close()
    assert FakeLoader.instances[0].closed is True


def test_instagram_provider_circuit_breaks_after_repeated_metadata_failures(monkeypatch):
    urls = [
        "https://www.instagram.com/reel/ABCxyz_123/",
        "https://www.instagram.com/reel/DEFxyz_456/",
        "https://www.instagram.com/reel/GHIxyz_789/",
    ]
    _fake_ddgs(monkeypatch, urls)
    _fake_instaloader(
        monkeypatch,
        lambda shortcode: (_ for _ in ()).throw(RuntimeError("Fetching Post metadata failed")),
    )
    monkeypatch.setattr("shorts_intelligence.discovery.providers.time.sleep", lambda _: None)

    provider = InstagramSearchProvider(
        request_pause_seconds=1,
        failure_threshold=2,
        max_lookups=10,
    )
    results = list(provider.search("cricket reels", limit=10))

    assert results == []
    assert provider.metadata_lookups == 2
    assert provider.metadata_failures == 2
    assert provider.circuit_open is True
    assert len(provider.errors) == 2
    provider.close()


def test_instagram_provider_falls_back_once_after_primary_timeout(monkeypatch):
    urls = ["https://www.instagram.com/reel/ABCxyz_123/"]
    FakeDDGS = _fake_ddgs(monkeypatch, urls)
    _fake_instaloader(monkeypatch, _fake_post)
    monkeypatch.setattr("shorts_intelligence.discovery.providers.time.sleep", lambda _: None)

    provider = InstagramSearchProvider(
        request_pause_seconds=1,
        backend="broken",
        fallback_backend="bing",
        search_timeout=6,
        max_lookups=5,
    )
    results = list(provider.search("cricket reels", limit=10))

    assert len(results) == 1
    assert provider.ddgs_failures == 1
    assert len(FakeDDGS.instances[0].calls) == 2
    assert provider.circuit_open is False
    provider.close()


def test_youtube_provider_opens_circuit_on_timeout(monkeypatch):
    class FakeSearchFilter:
        SHORTS = "shorts"

    class FakeRetryPolicy:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FailingYouTube:
        instances = []

        def __init__(self, **kwargs):
            self.calls = 0
            self.__class__.instances.append(self)

        def search(self, query, *, filter, max_results):
            self.calls += 1
            raise TimeoutError("YouTube request timed out")

        def close(self):
            return None

    module = ModuleType("ytscrape")
    module.SearchFilter = FakeSearchFilter
    module.RetryPolicy = FakeRetryPolicy
    module.YouTube = FailingYouTube
    module.RateLimited = type("RateLimited", (Exception,), {})
    module.BotDetected = type("BotDetected", (Exception,), {})
    monkeypatch.setitem(sys.modules, "ytscrape", module)

    provider = YouTubeSearchProvider()
    assert list(provider.search("cricket shorts", limit=10)) == []
    assert provider.circuit_open is True
    assert len(FailingYouTube.instances) == 1
    assert list(provider.search("comedy shorts", limit=10)) == []
    assert FailingYouTube.instances[0].calls == 1
    assert provider.circuit_reason is not None
