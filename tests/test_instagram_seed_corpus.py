from pathlib import Path

from shorts_intelligence.discovery.seed_loader import load_instagram_creator_seeds


def test_checked_in_instagram_seed_corpus_has_broad_repeatable_coverage():
    root = Path(__file__).resolve().parents[1]
    seeds = load_instagram_creator_seeds(root / "data" / "instagram_creator_seeds.txt")
    assert len(seeds) >= 70
    assert "taneja.gaurav" in seeds
    assert "souravjoshivlogs" in seeds
    assert "rvcjinsta" in seeds
    assert "ghantaa" in seeds
    assert len(seeds) == len(set(seeds))
