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
    media_sha256 TEXT,
    downloaded_at TEXT,
    download_status TEXT NOT NULL DEFAULT 'not_downloaded',
    last_error TEXT,
    PRIMARY KEY (platform, source_id),
    FOREIGN KEY (first_run_id) REFERENCES discovery_runs(run_id),
    FOREIGN KEY (last_run_id) REFERENCES discovery_runs(run_id)
);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status, download_status);
CREATE INDEX IF NOT EXISTS idx_candidates_views ON candidates(view_count DESC);
CREATE TABLE IF NOT EXISTS discovery_queries (
    platform TEXT NOT NULL,
    query_key TEXT NOT NULL,
    query TEXT NOT NULL,
    language TEXT NOT NULL,
    region TEXT NOT NULL,
    strategy TEXT NOT NULL,
    last_run_at TEXT NOT NULL,
    run_count INTEGER NOT NULL DEFAULT 1,
    last_raw_results INTEGER NOT NULL DEFAULT 0,
    last_candidate_count INTEGER NOT NULL DEFAULT 0,
    total_raw_results INTEGER NOT NULL DEFAULT 0,
    total_candidate_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (platform, query_key)
);
CREATE INDEX IF NOT EXISTS idx_discovery_queries_last_run
    ON discovery_queries(platform, last_run_at);
"""


class DiscoveryStore:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(_SCHEMA)
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(candidates)")}
        if "media_sha256" not in columns:
            self.connection.execute("ALTER TABLE candidates ADD COLUMN media_sha256 TEXT")
        if "downloaded_at" not in columns:
            self.connection.execute("ALTER TABLE candidates ADD COLUMN downloaded_at TEXT")
        query_columns = {
            row["name"] for row in self.connection.execute("PRAGMA table_info(discovery_queries)")
        }
        if "total_raw_results" not in query_columns:
            self.connection.execute(
                "ALTER TABLE discovery_queries ADD COLUMN total_raw_results INTEGER NOT NULL DEFAULT 0"
            )
            self.connection.execute(
                "UPDATE discovery_queries SET total_raw_results=last_raw_results*run_count"
            )
        if "total_candidate_count" not in query_columns:
            self.connection.execute(
                "ALTER TABLE discovery_queries ADD COLUMN total_candidate_count INTEGER NOT NULL DEFAULT 0"
            )
            self.connection.execute(
                "UPDATE discovery_queries SET total_candidate_count=last_candidate_count*run_count"
            )
        # Existing databases may contain high-view candidates that were
        # previously accepted without confirmed Short/Reel format evidence.
        self.connection.execute(
            "UPDATE candidates SET status='format_unknown' "
            "WHERE status='eligible' AND short_format_status!='confirmed'"
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> DiscoveryStore:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def has_candidate(self, platform: str, source_id: str) -> bool:
        """Return whether the platform/source identity already exists locally."""
        row = self.connection.execute(
            "SELECT 1 FROM candidates WHERE platform=? AND source_id=? LIMIT 1",
            (platform, source_id),
        ).fetchone()
        return row is not None

    def query_history(self, platform: str) -> dict[str, str]:
        """Return last-use timestamps for exact platform query keys."""
        rows = self.connection.execute(
            "SELECT query_key, last_run_at FROM discovery_queries WHERE platform=?",
            (platform,),
        ).fetchall()
        return {str(row["query_key"]): str(row["last_run_at"]) for row in rows}

    def record_query(
        self,
        *,
        platform: str,
        query_key: str,
        query: str,
        language: str,
        region: str,
        strategy: str,
        raw_results: int,
        candidate_count: int,
        run_at: datetime | None = None,
    ) -> None:
        """Persist query rotation state and yield observations."""
        timestamp = (run_at or datetime.now(UTC)).isoformat()
        self.connection.execute(
            """INSERT INTO discovery_queries(
                platform, query_key, query, language, region, strategy,
                last_run_at, run_count, last_raw_results, last_candidate_count,
                total_raw_results, total_candidate_count
            ) VALUES(?,?,?,?,?,?,?,1,?,?,?,?)
            ON CONFLICT(platform, query_key) DO UPDATE SET
                query=excluded.query,
                language=excluded.language,
                region=excluded.region,
                strategy=excluded.strategy,
                last_run_at=excluded.last_run_at,
                run_count=discovery_queries.run_count+1,
                last_raw_results=excluded.last_raw_results,
                last_candidate_count=excluded.last_candidate_count,
                total_raw_results=discovery_queries.total_raw_results+excluded.last_raw_results,
                total_candidate_count=discovery_queries.total_candidate_count+excluded.last_candidate_count""",
            (
                platform, query_key, query, language, region, strategy,
                timestamp, raw_results, candidate_count, raw_results, candidate_count,
            ),
        )
        self.connection.commit()

    def query_performance(self, platform: str) -> dict[str, dict[str, int]]:
        """Return per-query average yield for the requested platform.

        The query planner compares strategies using average raw search results
        and average normalized candidates per execution. Totals are persisted
        so this remains stable across process restarts and database migrations.
        """
        rows = self.connection.execute(
            """SELECT query_key, run_count, total_raw_results, total_candidate_count
            FROM discovery_queries
            WHERE platform=?
            ORDER BY query_key""",
            (platform,),
        ).fetchall()
        performance: dict[str, dict[str, int]] = {}
        for row in rows:
            run_count = max(1, int(row["run_count"]))
            performance[str(row["query_key"])] = {
                "run_count": run_count,
                "raw_results": max(0, int(row["total_raw_results"])) // run_count,
                "candidate_count": max(0, int(row["total_candidate_count"])) // run_count,
            }
        return performance

    def query_summary(self, platform: str | None = None) -> dict[str, int]:
        """Summarize how many distinct search queries have been used."""
        if platform is None:
            rows = self.connection.execute(
                "SELECT platform, COUNT(*) AS n FROM discovery_queries GROUP BY platform"
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT platform, COUNT(*) AS n FROM discovery_queries WHERE platform=? GROUP BY platform",
                (platform,),
            ).fetchall()
        return {str(row["platform"]): int(row["n"]) for row in rows}

    def start_run(
        self,
        run_id: str,
        requested_target: int,
        min_views: int,
        *,
        started_at: datetime | None = None,
    ) -> None:
        self.connection.execute(
            "INSERT INTO discovery_runs(run_id, started_at, requested_target, min_views) VALUES(?,?,?,?)",
            (run_id, (started_at or datetime.now(UTC)).isoformat(), requested_target, min_views),
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
        self,
        candidate: DiscoveredCandidate,
        *,
        min_views: int,
        run_id: str,
    ) -> tuple[bool, bool]:
        """Insert/update one candidate without downgrading known metadata to unknown."""
        existing = self.connection.execute(
            "SELECT * FROM candidates WHERE platform=? AND source_id=?",
            (candidate.platform, candidate.source_id),
        ).fetchone()
        is_new = existing is None
        was_eligible = bool(existing and existing["status"] == "eligible")

        # Search metadata can be incomplete on a later run. Retain previously
        # observed counts and a prior format classification when the new result
        # does not supply stronger information.
        effective_view_count = (
            candidate.view_count
            if candidate.view_count is not None
            else existing["view_count"] if existing else None
        )
        effective_play_count = (
            candidate.play_count
            if candidate.play_count is not None
            else existing["play_count"] if existing else None
        )
        effective_format = candidate.short_format_status
        if existing:
            previous_format = existing["short_format_status"]
            if effective_format == "unknown" or (
                effective_format == "candidate" and previous_format in {"confirmed", "not_short"}
            ):
                effective_format = previous_format

        previous_metadata = (
            json.loads(existing["metadata_json"])
            if existing and existing["metadata_json"]
            else {}
        )
        effective_metadata = {**previous_metadata, **candidate.metadata}

        # Compare platform-native metrics without relabeling Instagram plays
        # as views. Reports must retain the metric kind and source.
        metric = effective_view_count if candidate.platform == "youtube" else effective_play_count

        if effective_format == "not_short":
            status = "not_short"
        elif metric is None:
            status = "metric_unknown"
        elif metric < min_views:
            status = "below_threshold"
        elif effective_format != "confirmed":
            status = "format_unknown"
        else:
            status = "eligible"

        now = datetime.now(UTC).isoformat()
        effective_metric_source = candidate.metric_source
        if effective_metric_source is None and existing:
            effective_metric_source = existing["metric_source"]

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
                candidate.platform,
                candidate.source_id,
                str(candidate.canonical_url),
                candidate.title,
                candidate.description,
                candidate.creator,
                effective_view_count,
                effective_play_count,
                effective_metric_source,
                candidate.duration_seconds,
                candidate.upload_date,
                json.dumps(candidate.hashtags),
                effective_format,
                status,
                candidate.discovered_at.isoformat(),
                now,
                json.dumps(effective_metadata, ensure_ascii=False, default=str),
                run_id if is_new else existing["first_run_id"],
                run_id,
            ),
        )
        self.connection.commit()
        became_eligible = status == "eligible" and not was_eligible
        return is_new, became_eligible

    def eligible_candidates(self, limit: int = 100) -> list[DiscoveredCandidate]:
        rows = self.connection.execute(
            "SELECT * FROM candidates WHERE status='eligible' AND download_status IN ('not_downloaded','download_failed') "
            "ORDER BY CASE WHEN platform='youtube' THEN view_count ELSE play_count END DESC LIMIT ?", (limit,),
        ).fetchall()
        return [self._candidate_from_row(row) for row in rows]

    def get_candidate(self, platform: str, source_id: str) -> DiscoveredCandidate | None:
        row = self.connection.execute(
            "SELECT * FROM candidates WHERE platform=? AND source_id=?", (platform, source_id)
        ).fetchone()
        return self._candidate_from_row(row) if row else None

    def find_media_hash(self, media_sha256: str) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT platform, source_id, download_path FROM candidates "
            "WHERE media_sha256=? AND download_status='downloaded' LIMIT 1",
            (media_sha256,),
        ).fetchone()

    def mark_download(
        self, platform: str, source_id: str, *, path: str, media_sha256: str
    ) -> None:
        now = datetime.now(UTC).isoformat()
        self.connection.execute(
            "UPDATE candidates SET download_status='downloaded', download_path=?, "
            "media_sha256=?, downloaded_at=?, last_error=NULL, updated_at=? "
            "WHERE platform=? AND source_id=?",
            (path, media_sha256, now, now, platform, source_id),
        )
        self.connection.commit()

    def mark_download_failure(self, platform: str, source_id: str, *, error: str) -> None:
        self.connection.execute(
            "UPDATE candidates SET download_status='download_failed', last_error=?, updated_at=? "
            "WHERE platform=? AND source_id=?",
            (error[:500], datetime.now(UTC).isoformat(), platform, source_id),
        )
        self.connection.commit()

    def mark_duplicate_media(
        self, platform: str, source_id: str, *, duplicate_of: str, media_sha256: str
    ) -> None:
        self.connection.execute(
            "UPDATE candidates SET download_status='duplicate_media', media_sha256=?, "
            "download_path=NULL, last_error=?, updated_at=? WHERE platform=? AND source_id=?",
            (media_sha256, f"Identical media already downloaded as {duplicate_of}",
             datetime.now(UTC).isoformat(), platform, source_id),
        )
        self.connection.commit()

    def summary(self) -> dict[str, int]:
        rows = self.connection.execute(
            "SELECT status, COUNT(*) AS n FROM candidates GROUP BY status"
        ).fetchall()
        return {str(row["status"]): int(row["n"]) for row in rows}

    def summary_by_platform(self) -> dict[str, dict[str, int]]:
        rows = self.connection.execute(
            "SELECT platform, status, COUNT(*) AS n FROM candidates "
            "GROUP BY platform, status ORDER BY platform, status"
        ).fetchall()
        result: dict[str, dict[str, int]] = {}
        for row in rows:
            result.setdefault(str(row["platform"]), {})[str(row["status"])] = int(row["n"])
        return result

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
