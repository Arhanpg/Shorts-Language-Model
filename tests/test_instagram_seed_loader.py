from shorts_intelligence.discovery.seed_loader import (
    load_instagram_creator_seeds,
    normalize_instagram_handle,
)


def test_normalize_instagram_handles_and_profile_urls():
    assert normalize_instagram_handle("@Taneja.Gaurav") == "taneja.gaurav"
    assert normalize_instagram_handle("https://www.instagram.com/souravjoshivlogs/") == "souravjoshivlogs"
    assert normalize_instagram_handle("https://www.instagram.com/reel/AbCdEf123/") is None
    assert normalize_instagram_handle("not a handle") is None


def test_load_seed_file_merges_explicit_handles_and_deduplicates(tmp_path):
    path = tmp_path / "seeds.txt"
    path.write_text("# comment\n@CreatorOne\ncreatorTwo\n", encoding="utf-8")
    assert load_instagram_creator_seeds(
        path, explicit_handles=["@CREATORONE", "https://instagram.com/creatorThree/"]
    ) == ["creatorone", "creatortwo", "creatorthree"]


def test_seed_loader_missing_file_is_safe(tmp_path):
    assert load_instagram_creator_seeds(tmp_path / "missing.txt") == []
