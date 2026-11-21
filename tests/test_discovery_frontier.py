from __future__ import annotations

import sqlite3

from shorts_intelligence.discovery.frontier import CreatorFrontier


def test_creator_frontier_deduplicates_and_claims_by_priority(tmp_path):
    connection = sqlite3.connect(tmp_path / "frontier.sqlite3")
    connection.row_factory = sqlite3.Row
    frontier = CreatorFrontier(connection)
    assert frontier.enqueue_creator("youtube", "UC" + "a" * 22, priority_score=10)
    assert not frontier.enqueue_creator("youtube", "UC" + "a" * 22, priority_score=20)
    frontier.enqueue_creator("youtube", "UC" + "b" * 22, priority_score=5)
    claimed = frontier.claim_creators("youtube", limit=2)
    assert [item.priority_score for item in claimed] == [20, 5]
    frontier.finish_creator("youtube", claimed[0].creator_id, exhausted=True, eligible_yield=3)
    summary = frontier.summary()
    assert summary["creators_exhausted"] == 1
    assert summary["creators_pending"] == 0
    connection.close()


def test_expansion_seed_is_claimed_once_and_edge_is_deduplicated(tmp_path):
    connection = sqlite3.connect(tmp_path / "frontier.sqlite3")
    connection.row_factory = sqlite3.Row
    frontier = CreatorFrontier(connection)
    assert frontier.enqueue_seed("youtube", "AbCdEfGh123", creator_id="UCsource")
    assert not frontier.enqueue_seed("youtube", "AbCdEfGh123", creator_id="UCsource")
    seed = frontier.claim_seeds("youtube", limit=1)[0]
    frontier.finish_seed("youtube", seed["video_id"])
    frontier.add_edge("youtube", "UCsource", "UCtarget", edge_type="related_short",
                      source_video_id="AbCdEfGh123")
    frontier.add_edge("youtube", "UCsource", "UCtarget", edge_type="related_short",
                      source_video_id="AbCdEfGh123")
    assert frontier.summary()["creator_edges"] == 1
    assert frontier.summary()["expansion_seeds_pending"] == 0
    connection.close()


def test_expired_creator_lease_can_be_reclaimed(tmp_path):
    connection = sqlite3.connect(tmp_path / "frontier.sqlite3")
    connection.row_factory = sqlite3.Row
    frontier = CreatorFrontier(connection)
    frontier.enqueue_creator("youtube", "UC" + "c" * 22)
    first = frontier.claim_creators("youtube", limit=1, lease_seconds=0)
    assert len(first) == 1
    second = frontier.claim_creators("youtube", limit=1)
    assert len(second) == 1
    connection.close()


def test_expired_expansion_seed_lease_can_be_reclaimed(tmp_path):
    connection = sqlite3.connect(tmp_path / "seed-lease.sqlite3")
    connection.row_factory = sqlite3.Row
    frontier = CreatorFrontier(connection)
    frontier.enqueue_seed("youtube", "SeedLease123")
    first = frontier.claim_seeds("youtube", limit=1, lease_seconds=0)
    assert len(first) == 1
    second = frontier.claim_seeds("youtube", limit=1)
    assert len(second) == 1
    assert second[0]["attempts"] == 1
    connection.close()


def test_force_requeues_completed_exhausted_empty_and_blocked_creators(tmp_path):
    connection = sqlite3.connect(tmp_path / "force.sqlite3")
    connection.row_factory = sqlite3.Row
    frontier = CreatorFrontier(connection)
    for handle, error, exhausted in [
        ("completed", None, False),
        ("empty", "empty_harvest", False),
        ("blocked", "HTTP 403", False),
        ("exhausted", None, True),
    ]:
        frontier.enqueue_creator("instagram", handle, handle=handle)
        claimed = frontier.claim_creators("instagram", limit=1)
        assert claimed[0].creator_id == handle
        frontier.finish_creator(
            "instagram", handle, error=error, exhausted=exhausted
        )
    assert frontier.summary("instagram")["creators_completed"] == 1
    assert frontier.summary("instagram")["creators_empty"] == 1
    assert frontier.summary("instagram")["creators_blocked"] == 1
    assert frontier.summary("instagram")["creators_exhausted"] == 1
    assert frontier.enqueue_creator(
        "instagram", "blocked", handle="blocked", force=True, priority_score=999
    )
    assert frontier.enqueue_creator(
        "instagram", "empty", handle="empty", force=True, priority_score=999
    )
    claimed = frontier.claim_creators("instagram", limit=2)
    assert {item.creator_id for item in claimed} == {"blocked", "empty"}
    connection.close()


def test_frontier_summary_is_platform_scoped(tmp_path):
    connection = sqlite3.connect(tmp_path / "scoped.sqlite3")
    connection.row_factory = sqlite3.Row
    frontier = CreatorFrontier(connection)
    frontier.enqueue_creator("instagram", "ig")
    frontier.enqueue_creator("youtube", "yt")
    assert frontier.summary("instagram")["creators_pending"] == 1
    assert frontier.summary("youtube")["creators_pending"] == 1
    assert frontier.summary()["creators_pending"] == 2
    connection.close()
