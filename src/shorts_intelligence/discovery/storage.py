"""Private SQLite inventory for deduplication, discovery runs and download jobs."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shorts_intelligence.discovery.models import DiscoveredCandidate

_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS discovery_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    requested_target INTEGER NOT NULL,
    min_views INTEGER NOT NULL,
    scanned_count INTEGER NOT NULL DEFAULT 0,
    new_eligible_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    summary_json TEXT
);
CREATE TABLE IF NOT EXISTS candidates (
    platform TEXT NOT NULL,
    source_id TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    title TEXT,
    description TEXT,
    creator TEXT,
    view_count INTEGER,
    play_count INTEGER,
    metric_source TEXT,
    duration_seconds REAL,
    upload_date TEXT,
    hashtags_json TEXT NOT NULL DEFAULT '[]',
    short_format_status TEXT NOT NULL,
    status TEXT NOT NULL,
    discovered_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    first_run_id TEXT,
    last_run_id TEXT,
    download_path TEXT,
    download_status TEXT NOT NULL DEFAULT 'not_downloaded',
    last_error TEXT,
    PRIMARY KEY (platform, source_id),
    FOREIGN KEY (first_run_id) REFERENCES discovery_runs(run_id),
    FOREIGN KEY (last_run_id) REFERENCES discovery_runs(run_id)
);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status, download_status);
CREATE INDEX IF NOT EXISTS idx_candidates_views ON candidates(view_count DESC);
"""


class DiscoveryStore:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(_SCHEMA)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> DiscoveryStore:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def start_run(self, run_id: str, requested_target: int, min_views: int) -> None:
        self.connection.execute(
            "INSERT INTO discovery_runs(run_id, started_at, requested_target, min_views) VALUES(?,?,?,?)",
            (run_id, datetime.now(UTC).isoformat(), requested_target, min_views),
        )
        self.connection.commit()

    def finish_run(self, run_id: str, summary: dict[str, Any]) -> None:
        self.connection.execute(
            "UPDATE discovery_runs SET finished_at=?, scanned_count=?, new_eligible_count=?, "
            "duplicate_count=?, error_count=?, summary_json=? WHERE run_id=?",
            (
                datetime.now(UTC).isoformat(), summary.get("scanned", 0),
                summary.get("new_eligible", 0), summary.get("duplicates", 0),
                summary.get("errors", 0), json.dumps(summary, ensure_ascii=False), run_id,
            ),
        )
        self.connection.commit()

    def upsert_candidate(
        self, candidate: DiscoveredCandidate, *, min_views: int, run_id: str,
        accept_instagram_play_count: bool = False,
    ) -> tuple[bool, bool]:
        metric = candidate.qualifying_metric(accept_instagram_play_count=accept_instagram_play_count)
        if candidate.short_format_status == "not_short":
            status = "not_short"
        elif candidate.view_count is None and not (accept_instagram_play_count and candidate.play_count is not None):
            status = "metric_unknown"
        elif metric is not None and metric < min_views:
            status = "below_threshold"
        elif candidate.short_format_status == "unknown":
            status = "format_unknown"
        else:
            status = "eligible"
        now = datetime.now(UTC).isoformat()
        existing = self.connection.execute(
            "SELECT status, download_status FROM candidates WHERE platform=? AND source_id=?",
            (candidate.platform, candidate.source_id),
        ).fetchone()
        is_new = existing is None
        was_eligible = bool(existing and existing["status"] == "eligible" and existing["download_status"] == "not_downloaded")
        self.connection.execute(
            """INSERT INTO candidates(
                platform, source_id, canonical_url, title, description, creator, view_count,
                play_count, metric_source, duration_seconds, upload_date, hashtags_json,
                short_format_status, status, discovered_at, updated_at, metadata_json,
                first_run_id, last_run_id
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(platform, source_id) DO UPDATE SET
                canonical_url=excluded.canonical_url,
                title=COALESCE(excluded.title, candidates.title),
                description=COALESCE(excluded.description, candidates.description),
                creator=COALESCE(excluded.creator, candidates.creator),
                view_count=COALESCE(excluded.view_count, candidates.view_count),
                play_count=COALESCE(excluded.play_count, candidates.play_count),
                metric_source=COALESCE(excluded.metric_source, candidates.metric_source),
                duration_seconds=COALESCE(excluded.duration_seconds, candidates.duration_seconds),
                upload_date=COALESCE(excluded.upload_date, candidates.upload_date),
                hashtags_json=CASE WHEN excluded.hashtags_json='[]' THEN candidates.hashtags_json ELSE excluded.hashtags_json END,
                short_format_status=excluded.short_format_status,
                status=excluded.status,
                updated_at=excluded.updated_at,
                metadata_json=excluded.metadata_json,
                last_run_id=excluded.last_run_id""",
            (
                candidate.platform, candidate.source_id, str(candidate.canonical_url),
                candidate.title, candidate.description, candidate.creator, candidate.view_count,
                candidate.play_count, candidate.metric_source, candidate.duration_seconds,
                candidate.upload_date, json.dumps(candidate.hashtags), candidate.short_format_status,
                status, candidate.discovered_at.isoformat(), now,
                json.dumps(candidate.metadata, ensure_ascii=False, default=str), run_id, run_id,
            ),
        )
        self.connection.commit()
        became_eligible = status == "eligible" and not was_eligible
        return is_new, became_eligible

    def eligible_candidates(self, limit: int = 100) -> list[DiscoveredCandidate]:
        rows = self.connection.execute(
            "SELECT * FROM candidates WHERE status='eligible' AND download_status='not_downloaded' "
            "ORDER BY view_count DESC LIMIT ?", (limit,),
        ).fetchall()
        return [self._candidate_from_row(row) for row in rows]

    def get_candidate(self, platform: str, source_id: str) -> DiscoveredCandidate | None:
        row = self.connection.execute(
            "SELECT * FROM candidates WHERE platform=? AND source_id=?", (platform, source_id)
        ).fetchone()
        return self._candidate_from_row(row) if row else None

    def mark_download(self, platform: str, source_id: str, *, path: str | None, error: str | None) -> None:
        status = "downloaded" if path else "download_failed"
        self.connection.execute(
            "UPDATE candidates SET download_status=?, download_path=?, last_error=?, updated_at=? "
            "WHERE platform=? AND source_id=?",
            (status, path, error, datetime.now(UTC).isoformat(), platform, source_id),
        )
        self.connection.commit()

    def summary(self) -> dict[str, int]:
        rows = self.connection.execute(
            "SELECT status, COUNT(*) AS n FROM candidates GROUP BY status"
        ).fetchall()
        return {str(row["status"]): int(row["n"]) for row in rows}

    @staticmethod
    def _candidate_from_row(row: sqlite3.Row) -> DiscoveredCandidate:
        return DiscoveredCandidate(
            platform=row["platform"], source_id=row["source_id"], canonical_url=row["canonical_url"],
            title=row["title"], description=row["description"], creator=row["creator"],
            view_count=row["view_count"], play_count=row["play_count"], metric_source=row["metric_source"],
            duration_seconds=row["duration_seconds"], upload_date=row["upload_date"],
            hashtags=json.loads(row["hashtags_json"]), short_format_status=row["short_format_status"],
            status=row["status"], discovered_at=datetime.fromisoformat(row["discovered_at"]),
            metadata=json.loads(row["metadata_json"]),
        )
