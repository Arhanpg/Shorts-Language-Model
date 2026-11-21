"""Persistent creator and video frontier for graph-based discovery."""
from __future__ import annotations
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

@dataclass(frozen=True, slots=True)
class FrontierCreator:
    platform: str
    creator_id: str
    handle: str | None
    discovered_via: str
    depth: int
    priority_score: float

_SCHEMA = """
CREATE TABLE IF NOT EXISTS creator_frontier (
 platform TEXT NOT NULL, creator_id TEXT NOT NULL, handle TEXT,
 discovered_via TEXT NOT NULL, priority_score REAL NOT NULL DEFAULT 1.0,
 depth INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending',
 discovered_at TEXT NOT NULL, last_crawled_at TEXT, next_crawl_after TEXT,
 lease_until TEXT, attempts INTEGER NOT NULL DEFAULT 0,
 eligible_yield_count INTEGER NOT NULL DEFAULT 0, last_error TEXT,
 metadata_json TEXT NOT NULL DEFAULT '{}', PRIMARY KEY(platform, creator_id)
);
CREATE INDEX IF NOT EXISTS idx_creator_frontier_due
 ON creator_frontier(platform, status, next_crawl_after, priority_score DESC);
CREATE TABLE IF NOT EXISTS expansion_seeds (
 platform TEXT NOT NULL, video_id TEXT NOT NULL, creator_id TEXT,
 depth INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending',
 discovered_at TEXT NOT NULL, expanded_at TEXT, attempts INTEGER NOT NULL DEFAULT 0,
 last_error TEXT, PRIMARY KEY(platform, video_id)
);
CREATE INDEX IF NOT EXISTS idx_expansion_seeds_due
 ON expansion_seeds(platform, status, depth, discovered_at);
CREATE TABLE IF NOT EXISTS creator_edges (
 platform TEXT NOT NULL, source_creator_id TEXT NOT NULL,
 target_creator_id TEXT NOT NULL, edge_type TEXT NOT NULL,
 source_video_id TEXT, observed_at TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}',
 PRIMARY KEY(platform, source_creator_id, target_creator_id, edge_type, source_video_id)
);
"""

class CreatorFrontier:
    """Additive graph state backed by the existing discovery SQLite connection."""
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.executescript(_SCHEMA)
        self.connection.commit()

    def enqueue_creator(self, platform: str, creator_id: str, *, handle: str | None = None,
                        discovered_via: str = "seed", priority_score: float = 1.0,
                        depth: int = 0, metadata: dict[str, object] | None = None) -> bool:
        creator_id = creator_id.strip()
        if not creator_id:
            return False
        now = datetime.now(UTC).isoformat()
        cursor = self.connection.execute(
            """INSERT OR IGNORE INTO creator_frontier(
            platform, creator_id, handle, discovered_via, priority_score, depth,
            status, discovered_at, metadata_json) VALUES(?,?,?,?,?,?,'pending',?,?)""",
            (platform, creator_id, handle, discovered_via, priority_score, depth, now,
             json.dumps(metadata or {}, ensure_ascii=False)))
        if cursor.rowcount == 0:
            self.connection.execute(
                """UPDATE creator_frontier SET priority_score=MAX(priority_score, ?),
                depth=MIN(depth, ?), handle=COALESCE(handle, ?)
                WHERE platform=? AND creator_id=? AND status='pending'""",
                (priority_score, depth, handle, platform, creator_id))
        self.connection.commit()
        return cursor.rowcount == 1

    def enqueue_seed(self, platform: str, video_id: str, *,
                     creator_id: str | None = None, depth: int = 0) -> bool:
        cursor = self.connection.execute(
            """INSERT OR IGNORE INTO expansion_seeds(
            platform, video_id, creator_id, depth, status, discovered_at)
            VALUES(?,?,?,?,'pending',?)""",
            (platform, video_id, creator_id, depth, datetime.now(UTC).isoformat()))
        self.connection.commit()
        return cursor.rowcount == 1

    def claim_creators(self, platform: str, *, limit: int = 10,
                       lease_seconds: int = 180) -> list[FrontierCreator]:
        now = datetime.now(UTC)
        timestamp = now.isoformat()
        lease = (now + timedelta(seconds=lease_seconds)).isoformat()
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            rows = self.connection.execute(
                """SELECT * FROM creator_frontier WHERE platform=? AND (
                (status='pending' AND (next_crawl_after IS NULL OR next_crawl_after<=?))
                OR (status='active' AND lease_until<=?)
                ) ORDER BY priority_score DESC, depth ASC, discovered_at ASC LIMIT ?""",
                (platform, timestamp, timestamp, max(1, limit))).fetchall()
            for row in rows:
                self.connection.execute(
                    """UPDATE creator_frontier SET status='active', lease_until=?,
                    attempts=attempts+1 WHERE platform=? AND creator_id=?""",
                    (lease, platform, row["creator_id"]))
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return [FrontierCreator(platform, str(r["creator_id"]), r["handle"],
                str(r["discovered_via"]), int(r["depth"]), float(r["priority_score"]))
                for r in rows]

    def finish_creator(self, platform: str, creator_id: str, *, eligible_yield: int = 0,
                       cooldown_days: int = 14, exhausted: bool = False,
                       error: str | None = None) -> None:
        now = datetime.now(UTC)
        blocked = bool(error and any(t in error.casefold()
                       for t in ("checkpoint", "challenge", "rate limit", "429", "403")))
        attempts_row = self.connection.execute(
            "SELECT attempts FROM creator_frontier WHERE platform=? AND creator_id=?",
            (platform, creator_id),
        ).fetchone()
        attempts = int(attempts_row["attempts"]) if attempts_row else 0
        failed = bool(error and attempts >= 3 and not blocked)
        status = "blocked" if blocked else "failed" if failed else "exhausted" if exhausted else "pending"
        if exhausted and not blocked:
            next_crawl = (now + timedelta(days=cooldown_days)).isoformat()
        elif error and not blocked and not failed:
            next_crawl = (now + timedelta(minutes=30)).isoformat()
        else:
            next_crawl = None
        self.connection.execute(
            """UPDATE creator_frontier SET status=?, last_crawled_at=?, next_crawl_after=?,
            lease_until=NULL, eligible_yield_count=eligible_yield_count+?, last_error=?
            WHERE platform=? AND creator_id=?""",
            (status, now.isoformat(), next_crawl, max(0, eligible_yield),
             error[:500] if error else None, platform, creator_id))
        self.connection.commit()

    def claim_seeds(self, platform: str, *, limit: int = 20) -> list[sqlite3.Row]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            rows = self.connection.execute(
                """SELECT * FROM expansion_seeds WHERE platform=? AND status='pending'
                ORDER BY depth ASC, discovered_at ASC LIMIT ?""",
                (platform, max(1, limit))).fetchall()
            for row in rows:
                self.connection.execute(
                    "UPDATE expansion_seeds SET status='active', attempts=attempts+1 "
                    "WHERE platform=? AND video_id=?", (platform, row["video_id"]))
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return rows

    def finish_seed(self, platform: str, video_id: str, *, error: str | None = None) -> None:
        self.connection.execute(
            """UPDATE expansion_seeds SET status=CASE WHEN ? IS NULL THEN 'expanded'
                WHEN attempts>=2 THEN 'failed' ELSE 'pending' END,
                expanded_at=?, last_error=? WHERE platform=? AND video_id=?""",
            (error, datetime.now(UTC).isoformat(),
             error[:500] if error else None, platform, video_id))
        self.connection.commit()

    def add_edge(self, platform: str, source_creator_id: str, target_creator_id: str, *,
                 edge_type: str, source_video_id: str | None = None,
                 metadata: dict[str, object] | None = None) -> None:
        if not source_creator_id or not target_creator_id or source_creator_id == target_creator_id:
            return
        self.connection.execute(
            """INSERT OR IGNORE INTO creator_edges(platform, source_creator_id,
            target_creator_id, edge_type, source_video_id, observed_at, metadata_json)
            VALUES(?,?,?,?,?,?,?)""",
            (platform, source_creator_id, target_creator_id, edge_type, source_video_id,
             datetime.now(UTC).isoformat(), json.dumps(metadata or {}, ensure_ascii=False)))
        self.connection.commit()

    def summary(self) -> dict[str, int]:
        queries = {
            "creators_pending": "SELECT COUNT(*) FROM creator_frontier WHERE status='pending'",
            "creators_exhausted": "SELECT COUNT(*) FROM creator_frontier WHERE status='exhausted'",
            "creators_blocked": "SELECT COUNT(*) FROM creator_frontier WHERE status='blocked'",
            "creators_failed": "SELECT COUNT(*) FROM creator_frontier WHERE status='failed'",
            "expansion_seeds_pending": "SELECT COUNT(*) FROM expansion_seeds WHERE status='pending'",
            "creator_edges": "SELECT COUNT(*) FROM creator_edges",
        }
        return {key: int(self.connection.execute(sql).fetchone()[0])
                for key, sql in queries.items()}
