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
