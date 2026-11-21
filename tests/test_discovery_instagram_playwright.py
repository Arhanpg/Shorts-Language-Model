from shorts_intelligence.discovery.providers.instagram_playwright import extract_reel_records


def test_instagram_parser_keeps_plays_distinct_and_extracts_coauthors():
    payload = {"items": [{
        "code": "AbCdEf12345",
        "product_type": "clips",
        "play_count": 1_500_000,
        "coauthor_producers": [{"username": "collaborator"}],
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
