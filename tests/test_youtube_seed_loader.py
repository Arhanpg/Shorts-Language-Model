from shorts_intelligence.discovery.seed_loader import load_youtube_channel_seeds


def test_youtube_channel_seed_loader_accepts_only_stable_channel_ids(tmp_path):
    path = tmp_path / "youtube_ids.txt"
    valid = "UC" + "a" * 22
    path.write_text(f"{valid}\n@handle\nUCshort\n{valid}\n", encoding="utf-8")
    assert load_youtube_channel_seeds(path) == [valid]


def test_youtube_channel_seed_loader_missing_file_is_safe(tmp_path):
    assert load_youtube_channel_seeds(tmp_path / "missing.txt") == []
