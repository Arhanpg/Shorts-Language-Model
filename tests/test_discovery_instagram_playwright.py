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
