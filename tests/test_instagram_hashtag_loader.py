from shorts_intelligence.discovery.hashtag_loader import (
    load_instagram_hashtags,
    normalize_instagram_hashtag,
)


def test_normalize_instagram_hashtag():
    assert normalize_instagram_hashtag("#GetReadyWithMe") == "getreadywithme"
    assert normalize_instagram_hashtag("Virat.Kohli") == "virat.kohli"
    assert normalize_instagram_hashtag("##") is None
    assert normalize_instagram_hashtag("two words") is None


def test_explicit_hashtags_take_priority_over_seed_file(tmp_path):
    path = tmp_path / "hashtags.txt"
    path.write_text("# comments\n#Cricket\nViratKohli\n", encoding="utf-8")
    assert load_instagram_hashtags(
        path, explicit_hashtags=["#cricket", "GetReadyWithMe"]
    ) == ["cricket", "getreadywithme", "viratkohli"]


def test_missing_hashtag_file_is_safe(tmp_path):
    assert load_instagram_hashtags(tmp_path / "missing.txt") == []
