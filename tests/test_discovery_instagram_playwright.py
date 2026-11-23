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


def test_instagram_reuses_the_persistent_startup_tab_across_surfaces(monkeypatch, tmp_path):
    import asyncio
    import sys
    from types import ModuleType, SimpleNamespace

    from shorts_intelligence.discovery.providers.instagram_playwright import (
        InstagramPlaywrightProvider,
    )

    class FakeResponse:
        status = 200

    class FakeLocator:
        async def evaluate_all(self, _script):
            return []

        async def all_text_contents(self):
            return []

    class FakePage:
        def __init__(self):
            self.url = "about:blank"
            self.mouse = SimpleNamespace(wheel=self.wheel)
            self.handlers = {}
            self.goto_urls = []
            self.closed = False

        async def wheel(self, *_args):
            return None

        def on(self, event, handler):
            self.handlers.setdefault(event, []).append(handler)

        def remove_listener(self, event, handler):
            self.handlers.get(event, []).remove(handler)

        def is_closed(self):
            return self.closed

        async def goto(self, url, **_kwargs):
            self.url = url
            self.goto_urls.append(url)
            return FakeResponse()

        async def wait_for_timeout(self, *_args):
            return None

        async def title(self):
            return "Instagram"

        def locator(self, _selector):
            return FakeLocator()

    class FakeContext:
        def __init__(self, page):
            self.pages = [page]
            self.browser = SimpleNamespace(is_connected=lambda: True)
            self.new_page_calls = 0
            self.closed = False

        async def new_page(self):
            self.new_page_calls += 1
            raise AssertionError("The persistent startup tab should be reused")

        async def close(self):
            self.closed = True

    class FakePlaywright:
        def __init__(self, context):
            self.context = context
            self.chromium = self
            self.stops = 0

        async def launch_persistent_context(self, **_kwargs):
            return self.context

        async def stop(self):
            self.stops += 1

    class Manager:
        def __init__(self, playwright):
            self.playwright = playwright

        async def start(self):
            return self.playwright

    page = FakePage()
    context = FakeContext(page)
    playwright = FakePlaywright(context)
    api = ModuleType("playwright.async_api")
    api.async_playwright = lambda: Manager(playwright)
    package = ModuleType("playwright")
    package.async_api = api
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.async_api", api)

    provider = InstagramPlaywrightProvider(profile_dir=tmp_path / "profile")

    async def exercise():
        hashtag_records = await provider.harvest_hashtag(
            "getreadywithme", max_scrolls=0, max_reel_details=0
        )
        creator_records, coauthors = await provider.harvest_creator(
            "example_creator", max_scrolls=0, max_reel_details=0
        )
        assert hashtag_records == []
        assert creator_records == []
        assert coauthors == set()
        assert page.goto_urls == [
            "https://www.instagram.com/explore/search/keyword/?q=%23getreadywithme",
            "https://www.instagram.com/explore/tags/getreadywithme/",
            "https://www.instagram.com/example_creator/reels/",
        ]
        assert context.new_page_calls == 0
        assert page.handlers.get("response", []) == []
        await provider.close()

    asyncio.run(exercise())
    assert context.closed is True
    assert playwright.stops == 1


def test_instagram_creates_a_tab_only_when_persistent_context_has_none(monkeypatch, tmp_path):
    import asyncio
    import sys
    from types import ModuleType

    from shorts_intelligence.discovery.providers.instagram_playwright import (
        InstagramPlaywrightProvider,
    )

    class FakePage:
        def __init__(self):
            self.closed = False

        def is_closed(self):
            return self.closed

    class FakeContext:
        def __init__(self):
            self.pages = []
            self.browser = None
            self.created = 0

        async def new_page(self):
            self.created += 1
            page = FakePage()
            self.pages.append(page)
            return page

        async def close(self):
            return None

    class FakePlaywright:
        def __init__(self, context):
            self.chromium = self
            self.context = context

        async def launch_persistent_context(self, **_kwargs):
            return self.context

        async def stop(self):
            return None

    class Manager:
        def __init__(self, playwright):
            self.playwright = playwright

        async def start(self):
            return self.playwright

    context = FakeContext()
    playwright = FakePlaywright(context)
    api = ModuleType("playwright.async_api")
    api.async_playwright = lambda: Manager(playwright)
    package = ModuleType("playwright")
    package.async_api = api
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.async_api", api)

    provider = InstagramPlaywrightProvider(profile_dir=tmp_path / "profile")

    async def exercise():
        first = await provider._ensure_page()
        second = await provider._ensure_page()
        assert first is second
        assert context.created == 1
        await provider.close()

    asyncio.run(exercise())



def test_visible_metric_parser_reads_exact_and_abbreviated_views_and_plays():
    from shorts_intelligence.discovery.providers.instagram_playwright import (
        _visible_metric_from_text,
    )

    exact_views = _visible_metric_from_text("1,234,567 views")
    assert exact_views is not None
    assert exact_views["kind"] == "views"
    assert exact_views["nominal_count"] == 1_234_567
    assert exact_views["lower_bound"] == 1_234_567
    assert exact_views["is_estimate"] is False

    abbreviated_views = _visible_metric_from_text("1.2M views")
    assert abbreviated_views is not None
    assert abbreviated_views["kind"] == "views"
    assert abbreviated_views["nominal_count"] == 1_200_000
    assert abbreviated_views["lower_bound"] == 1_150_000
    assert abbreviated_views["is_estimate"] is True

    abbreviated_plays = _visible_metric_from_text("Plays 850K")
    assert abbreviated_plays is not None
    assert abbreviated_plays["kind"] == "plays"
    assert abbreviated_plays["lower_bound"] == 849_500


def test_visible_metric_parser_does_not_confuse_likes_or_caption_numbers():
    from shorts_intelligence.discovery.providers.instagram_playwright import (
        _visible_metric_from_text,
    )

    assert _visible_metric_from_text("1.2M likes") is None
    assert _visible_metric_from_text("2026 travel diaries") is None
    assert _visible_metric_from_text("A caption with 2026 and 3 friends") is None
    assert _visible_metric_from_text("1.2M", allow_bare_count=True) is not None


def test_instagram_parser_accepts_new_video_typenames_and_flags():
    payload = {
        "data": {
            "edges": [{
                "node": {
                    "__typename": "XDTGraphVideo",
                    "shortcode": "NewGraphVideo123",
                    "is_unified_video": True,
                    "videoViewCount": 2_400_000,
                }
            }]
        }
    }
    records = extract_reel_records(payload, creator_handle="hashtag:travel")
    assert len(records) == 1
    assert records[0].source_id == "NewGraphVideo123"
    assert records[0].view_count == 2_400_000
    assert records[0].qualifying_metric_kind() == "views"


def test_visible_metric_parser_supports_label_before_number():
    from shorts_intelligence.discovery.providers.instagram_playwright import (
        _visible_metric_from_text,
    )

    metric = _visible_metric_from_text("Views: 2.4M")
    assert metric is not None
    assert metric["kind"] == "views"
    assert metric["nominal_count"] == 2_400_000
    assert metric["lower_bound"] == 2_350_000


def test_apply_visible_metric_preserves_estimate_provenance():
    from shorts_intelligence.discovery.models import DiscoveredCandidate
    from shorts_intelligence.discovery.providers.instagram_playwright import (
        _apply_visible_metric,
        _visible_metric_from_text,
    )

    metric = _visible_metric_from_text("1.2M views")
    assert metric is not None
    candidate = DiscoveredCandidate(
        platform="instagram",
        source_id="VisibleCount123",
        canonical_url="https://www.instagram.com/reel/VisibleCount123/",
        creator="creator",
        short_format_status="confirmed",
    )
    _apply_visible_metric(
        candidate, metric, source="instagram_rendered_reel_card.views"
    )
    assert candidate.view_count is None
    assert candidate.play_count is None
    assert candidate.qualifying_metric() == 1_150_000
    assert candidate.metadata["metric_is_estimate"] is True
    assert candidate.metadata["metric_display_value"] == "1.2M"
    assert candidate.metadata["metric_usage"] == (
        "discovery_filter_only; not an exact training label"
    )


def test_instagram_parser_extracts_shortcode_from_observed_public_permalink():
    payload = {
        "sections": [{
            "layout_content": {
                "medias": [{
                    "media": {
                        "__typename": "XDTGraphVideo",
                        "permalink": "https://www.instagram.com/reel/PublicLink123/",
                        "is_unified_video": True,
                        "viewCount": 1_700_000,
                    }
                }]
            }
        }]
    }
    records = extract_reel_records(payload, creator_handle="hashtag:travel")
    assert len(records) == 1
    assert records[0].source_id == "PublicLink123"
    assert records[0].view_count == 1_700_000


def test_estimated_visible_metric_never_populates_exact_count_fields():
    from shorts_intelligence.discovery.models import DiscoveredCandidate
    from shorts_intelligence.discovery.providers.instagram_playwright import (
        _apply_visible_metric,
        _visible_metric_from_text,
    )

    metric = _visible_metric_from_text("1.2M views")
    assert metric is not None
    candidate = DiscoveredCandidate(
        platform="instagram",
        source_id="EstimateOnly123",
        canonical_url="https://www.instagram.com/reel/EstimateOnly123/",
        creator="creator",
        short_format_status="confirmed",
    )
    _apply_visible_metric(candidate, metric, source="instagram_rendered_reel_card.views")

    assert candidate.view_count is None
    assert candidate.play_count is None
    assert candidate.qualifying_metric() == 1_150_000
    assert candidate.qualifying_metric_kind() == "views"
    assert candidate.metadata["metric_is_estimate"] is True


def test_hover_metric_parser_reads_count_only_reel_overlay_values_as_plays():
    from shorts_intelligence.discovery.providers.instagram_playwright import (
        _visible_hover_metric_from_texts,
    )

    abbreviated = _visible_hover_metric_from_texts(["1.2M"])
    assert abbreviated is not None
    assert abbreviated["kind"] == "plays"
    assert abbreviated["lower_bound"] == 1_150_000
    assert abbreviated["is_estimate"] is True

    exact = _visible_hover_metric_from_texts(["1,234,567"])
    assert exact is not None
    assert exact["kind"] == "plays"
    assert exact["lower_bound"] == 1_234_567
    assert exact["is_estimate"] is False


def test_hover_metric_parser_rejects_plain_caption_numbers_and_likes():
    from shorts_intelligence.discovery.providers.instagram_playwright import (
        _visible_hover_metric_from_texts,
    )

    assert _visible_hover_metric_from_texts(["2026"]) is None
    assert _visible_hover_metric_from_texts(["1.2M likes"]) is None
    assert _visible_hover_metric_from_texts(["A caption", "2026", "3 friends"]) is None


def test_hashtag_uses_instagram_keyword_search_route_seen_in_current_ui():
    from shorts_intelligence.discovery.providers.instagram_playwright import (
        instagram_hashtag_keyword_search_url,
        instagram_hashtag_page_url,
    )

    assert instagram_hashtag_page_url("getreadywithme") == (
        "https://www.instagram.com/explore/tags/getreadywithme/"
    )
    assert instagram_hashtag_page_url("#ViratKohli") == (
        "https://www.instagram.com/explore/tags/viratkohli/"
    )
    assert instagram_hashtag_keyword_search_url("getreadywithme") == (
        "https://www.instagram.com/explore/search/keyword/?q=%23getreadywithme"
    )
    assert instagram_hashtag_keyword_search_url("#ViratKohli") == (
        "https://www.instagram.com/explore/search/keyword/?q=%23viratkohli"
    )


def test_hashtag_falls_back_when_keyword_route_only_has_metricless_reel_links(tmp_path):
    import asyncio

    from shorts_intelligence.discovery.models import DiscoveredCandidate
    from shorts_intelligence.discovery.providers.instagram_playwright import (
        InstagramPlaywrightProvider,
    )

    provider = InstagramPlaywrightProvider(profile_dir=tmp_path / "profile")
    calls = []

    async def fake_collect_surface(**kwargs):
        calls.append(kwargs)
        if kwargs["surface"] == "hashtag_keyword_search":
            candidate = DiscoveredCandidate(
                platform="instagram",
                source_id="Metricless123",
                canonical_url="https://www.instagram.com/reel/Metricless123/",
                short_format_status="confirmed",
                metadata={"metric_kind": "unknown"},
            )
            return [candidate], set(), {
                "surface": kwargs["surface"],
                "requested_url": kwargs["url"],
                "candidate_count": 1,
                "metric_count": 0,
                "reason": "Reel link has no visible count",
            }

        candidate = DiscoveredCandidate(
            platform="instagram",
            source_id="GridFallback123",
            canonical_url="https://www.instagram.com/reel/GridFallback123/",
            play_count=1_500_000,
            short_format_status="confirmed",
            metadata={"discovery_surface": kwargs["surface"]},
        )
        return [candidate], set(), {
            "surface": kwargs["surface"],
            "requested_url": kwargs["url"],
            "candidate_count": 1,
            "metric_count": 1,
        }

    provider._collect_surface = fake_collect_surface

    records = asyncio.run(
        provider.harvest_hashtag(
            "getreadywithme",
            max_scrolls=2,
            max_reel_details=1,
        )
    )
    assert {item.source_id for item in records} == {
        "Metricless123",
        "GridFallback123",
    }
    assert [call["surface"] for call in calls] == [
        "hashtag_keyword_search",
        "hashtag_grid_fallback",
    ]
    assert provider.hashtag_diagnostics[1]["attempt"] == (
        "legacy_public_hashtag_grid_fallback"
    )
    assert provider.hashtag_diagnostics[1]["fallback_from"].endswith(
        "q=%23getreadywithme"
    )


def test_instagram_parser_stops_at_bounded_depth_and_node_count():
    payload = {}
    node = payload
    for _ in range(500):
        child = {}
        node["child"] = child
        node = child

    records = extract_reel_records(payload, creator_handle="creator")
    assert records == []


def test_response_shape_diagnostics_include_bounded_media_like_objects():
    from shorts_intelligence.discovery.providers.instagram_playwright import _response_shape

    payload = {
        "data": {
            "items": [{
                "media": {
                    "__typename": "XDTGraphVideo",
                    "code": "PublicReel123",
                    "play_count": 12345,
                }
            }]
        }
    }
    shape = _response_shape(payload)
    assert shape["top_level_keys"] == ["data"]
    assert shape["media_like_objects"]
    assert "code" in shape["media_like_objects"][0]["signals"]
