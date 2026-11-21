from shorts_intelligence.discovery.providers.instagram_playwright import (
    _jsonld_video_metric,
    _raw_count,
    extract_reel_records,
)


def test_instagram_parser_keeps_plays_distinct_and_extracts_coauthors():
    payload = {"items": [{
        "code": "AbCdEf12345",
        "product_type": "clips",
        "play_count": 1_500_000,
        "coauthor_producers": [{"username": "Collaborator"}],
    }]}
    records = extract_reel_records(payload, creator_handle="creator")
    assert len(records) == 1
    item = records[0]
    assert item.play_count == 1_500_000
    assert item.view_count is None
    assert item.qualifying_metric() == 1_500_000
    assert item.qualifying_metric_kind() == "plays"
    assert item.metadata["coauthor_handles"] == ["collaborator"]


def test_instagram_parser_rejects_non_reel_video_and_display_strings():
    payload = {"items": [
        {"code": "NotAReel123", "media_type": 1, "play_count": 9_000_000},
        {"code": "StringCount123", "media_type": 2, "play_count": "1.5M"},
    ]}
    records = extract_reel_records(payload, creator_handle="creator")
    assert len(records) == 1
    assert records[0].play_count is None
    assert records[0].qualifying_metric() is None


def test_instagram_parser_accepts_numeric_string_counts_and_reel_flags():
    payload = {"items": [
        {"shortcode": "NumericString123", "is_reel": True, "play_count": "1,500,000"},
        {"code": "MediaTypeString123", "media_type": "2", "video_play_count": "2000000"},
    ]}
    records = extract_reel_records(payload, creator_handle="creator")
    by_id = {item.source_id: item for item in records}
    assert by_id["NumericString123"].play_count == 1_500_000
    assert by_id["MediaTypeString123"].play_count == 2_000_000


def test_instagram_explicit_view_count_remains_a_views_metric():
    payload = {"items": [{
        "code": "ExplicitViews123",
        "product_type": "clips",
        "view_count": 2_000_000,
    }]}
    item = extract_reel_records(payload, creator_handle="creator")[0]
    assert item.view_count == 2_000_000
    assert item.play_count is None
    assert item.qualifying_metric() == 2_000_000
    assert item.qualifying_metric_kind() == "views"


def test_instagram_video_play_count_is_preserved_as_plays():
    payload = {"items": [{
        "code": "VideoPlayCount123",
        "product_type": "clips",
        "video_play_count": 1_250_000,
    }]}
    item = extract_reel_records(payload, creator_handle="creator")[0]
    assert item.play_count == 1_250_000
    assert item.qualifying_metric_kind() == "plays"


def test_raw_count_never_parses_abbreviated_display_values():
    assert _raw_count("1,500,000") == 1_500_000
    assert _raw_count("1.5M") is None
    assert _raw_count(True) is None


def test_instagram_parser_reads_nested_media_and_prefers_explicit_play_count():
    payload = {"data": {"items": [{
        "media": {
            "code": "NestedReelCode123",
            "product_type": "clips",
            "play_count": "1,250,000",
            "video_view_count": 1_100_000,
            "user": {"username": "OriginalCreator"},
            "caption": {"text": "A #Cricket #India reel"},
        }
    }]}}
    item = extract_reel_records(payload, creator_handle="seed")[0]
    assert item.source_id == "NestedReelCode123"
    assert item.play_count == 1_250_000
    assert item.view_count == 1_100_000
    assert item.creator == "originalcreator"
    assert item.hashtags == ["Cricket", "India"]


def test_instagram_jsonld_extracts_watch_and_view_metrics_without_likes():
    payload = {"@type": "VideoObject", "interactionStatistic": [
        {"interactionType": {"@type": "LikeAction"}, "userInteractionCount": 900_000},
        {"interactionType": {"@type": "ViewAction"}, "userInteractionCount": 1_100_000},
        {"interactionType": {"@type": "WatchAction"}, "userInteractionCount": 1_300_000},
    ]}
    assert _jsonld_video_metric(payload) == (
        "plays", 1_300_000, "instagram_jsonld.WatchAction"
    )


def test_instagram_jsonld_ignores_non_numeric_and_like_only_metrics():
    payload = {"interactionStatistic": [
        {"interactionType": {"@type": "LikeAction"}, "userInteractionCount": 9999999},
        {"interactionType": {"@type": "WatchAction"}, "userInteractionCount": "1.2M"},
    ]}
    assert _jsonld_video_metric(payload) is None


def test_provider_close_is_idempotent_after_external_browser_shutdown():
    import asyncio
    from pathlib import Path

    from shorts_intelligence.discovery.providers.instagram_playwright import (
        InstagramPlaywrightProvider,
    )

    class ClosedContext:
        async def close(self):
            raise RuntimeError("Target page, context or browser has been closed")

    class StoppedPlaywright:
        def __init__(self):
            self.calls = 0

        async def stop(self):
            self.calls += 1
            raise RuntimeError("I/O operation on closed pipe")

    provider = InstagramPlaywrightProvider(profile_dir=Path("profile"))
    playwright = StoppedPlaywright()
    provider._context = ClosedContext()
    provider._playwright = playwright

    asyncio.run(provider.close())
    asyncio.run(provider.close())

    assert provider._context is None
    assert provider._playwright is None
    assert playwright.calls == 1


def test_ensure_context_relaunches_after_chrome_was_closed(monkeypatch, tmp_path):
    import asyncio
    import sys
    from types import ModuleType

    from shorts_intelligence.discovery.providers.instagram_playwright import (
        InstagramPlaywrightProvider,
    )

    class Browser:
        def __init__(self, connected):
            self.connected = connected

        def is_connected(self):
            return self.connected

    class Context:
        def __init__(self, connected=True):
            self.browser = Browser(connected)
            self.pages = []
            self.closed = False

        async def close(self):
            self.closed = True

    class Playwright:
        def __init__(self, context):
            self.context = context
            self.launches = 0
            self.stops = 0
            self.chromium = self

        async def launch_persistent_context(self, **kwargs):
            self.launches += 1
            return self.context

        async def stop(self):
            self.stops += 1

    class Manager:
        def __init__(self, playwright):
            self.playwright = playwright

        async def start(self):
            return self.playwright

    old_context = Context(connected=False)
    old_playwright = Playwright(old_context)
    new_context = Context(connected=True)
    new_playwright = Playwright(new_context)
    managers = [Manager(new_playwright)]
    api = ModuleType("playwright.async_api")
    api.async_playwright = lambda: managers.pop(0)
    package = ModuleType("playwright")
    package.async_api = api
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.async_api", api)

    provider = InstagramPlaywrightProvider(profile_dir=tmp_path / "profile")
    provider._context = old_context
    provider._playwright = old_playwright

    async def exercise():
        context = await provider._ensure_context()
        assert context is new_context
        await provider.close()

    asyncio.run(exercise())
    assert old_context.closed is True
    assert old_playwright.stops == 1
    assert new_playwright.launches == 1
    assert new_context.closed is True
    assert new_playwright.stops == 1
