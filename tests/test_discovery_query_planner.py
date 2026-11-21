import random
from datetime import UTC, datetime, timedelta

from shorts_intelligence.discovery.query_planner import (
    SearchQuery,
    build_instagram_query_pool,
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
