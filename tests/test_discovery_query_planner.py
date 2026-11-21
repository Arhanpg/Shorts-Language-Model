import random
from datetime import UTC, datetime, timedelta

from shorts_intelligence.discovery.query_planner import (
    SearchQuery,
    build_instagram_query_pool,
    build_youtube_hashtag_pool,
    build_youtube_query_pool,
    select_due_queries,
)


def test_youtube_query_pool_covers_indian_languages_and_other_regions():
    queries = build_youtube_query_pool()
    locales = {(item.language, item.region) for item in queries}
    assert ("hi", "IN") in locales
    assert ("mr", "IN") in locales
    assert ("kn", "IN") in locales
    assert ("ta", "IN") in locales
    assert ("te", "IN") in locales
    assert ("en", "US") in locales
    assert ("es", "ES") in locales
    assert len(queries) >= 100


def test_instagram_query_pool_respects_custom_default_region():
    queries = build_instagram_query_pool(["cricket", "  comedy  "], default_region="in-hi")
    assert len(queries) == 2
    assert all(item.region == "in-hi" for item in queries)
    assert all(item.language == "hi" for item in queries)
    assert queries[1].query == "comedy"


def test_query_selection_prefers_never_used_and_cooldown_expired():
    now = datetime(2026, 11, 21, tzinfo=UTC)
    queries = [
        SearchQuery("youtube", "one", "en", "IN", "topic"),
        SearchQuery("youtube", "two", "en", "IN", "topic"),
        SearchQuery("youtube", "three", "en", "IN", "topic"),
    ]
    history = {
        queries[0].key: (now - timedelta(days=1)).isoformat(),
        queries[1].key: (now - timedelta(days=10)).isoformat(),
    }

    selected = select_due_queries(
        queries,
        history,
        limit=2,
        cooldown_days=7,
        rng=random.Random(1),
        now=now,
    )

    assert queries[2] in selected  # never used
    assert queries[1] in selected  # cooldown has expired
    assert queries[0] not in selected  # used within the cooldown


def test_query_selection_can_replay_with_seed():
    queries = build_youtube_query_pool()
    a = select_due_queries(
        queries, {}, limit=15, cooldown_days=7, rng=random.Random(42)
    )
    b = select_due_queries(
        queries, {}, limit=15, cooldown_days=7, rng=random.Random(42)
    )
    assert [item.key for item in a] == [item.key for item in b]


def test_query_selection_does_not_reuse_queries_inside_cooldown():
    now = datetime(2026, 11, 21, tzinfo=UTC)
    queries = [
        SearchQuery("youtube", "one", "en", "IN", "topic"),
        SearchQuery("youtube", "two", "en", "IN", "topic"),
    ]
    history = {
        item.key: (now - timedelta(days=1)).isoformat()
        for item in queries
    }

    selected = select_due_queries(
        queries,
        history,
        limit=10,
        cooldown_days=7,
        rng=random.Random(2),
        now=now,
    )

    assert selected == []


def test_youtube_hashtag_pool_creates_distinct_shorts_shelf_queries():
    queries = build_youtube_hashtag_pool(["Cricket", "Cooking"])
    assert len(queries) == 2
    assert {item.strategy for item in queries} == {"hashtag_shorts_shelf"}
    assert {item.query for item in queries} == {"cricket", "cooking"}


def test_query_selection_ranks_historically_productive_queries():
    now = datetime(2026, 11, 21, tzinfo=UTC)
    productive = SearchQuery("youtube", "productive", "en", "IN", "topic")
    weak = SearchQuery("youtube", "weak", "en", "IN", "topic")
    history = {
        productive.key: (now - timedelta(days=10)).isoformat(),
        weak.key: (now - timedelta(days=10)).isoformat(),
    }
    selected = select_due_queries(
        [weak, productive],
        history,
        limit=2,
        cooldown_days=7,
        rng=random.Random(1),
        performance={
            productive.key: {"run_count": 2, "raw_results": 40, "candidate_count": 18},
            weak.key: {"run_count": 3, "raw_results": 1, "candidate_count": 0},
        },
        now=now,
    )
    assert selected[0] == productive


def test_query_selection_explores_and_exploits_when_pool_is_large():
    now = datetime(2026, 11, 21, tzinfo=UTC)
    never_used = [
        SearchQuery("youtube", f"new-{index}", "en", "IN", "topic")
        for index in range(10)
    ]
    productive = SearchQuery("youtube", "productive", "en", "IN", "topic")
    weak = SearchQuery("youtube", "weak", "en", "IN", "topic")
    history = {
        productive.key: (now - timedelta(days=10)).isoformat(),
        weak.key: (now - timedelta(days=10)).isoformat(),
    }
    selected = select_due_queries(
        never_used + [weak, productive],
        history,
        limit=10,
        cooldown_days=7,
        rng=random.Random(5),
        performance={
            productive.key: {"run_count": 2, "raw_results": 80, "candidate_count": 20},
            weak.key: {"run_count": 4, "raw_results": 2, "candidate_count": 0},
        },
        now=now,
    )
    assert len(selected) == 10
    assert productive in selected
    assert len([item for item in selected if item in never_used]) >= 7
