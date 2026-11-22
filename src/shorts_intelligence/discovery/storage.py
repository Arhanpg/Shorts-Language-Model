"""Private SQLite inventory for deduplication, discovery runs and download jobs."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from shorts_intelligence.discovery.models import (
    AcquisitionAuthorization,
    DiscoveredCandidate,
)

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
CREATE TABLE IF NOT EXISTS rights_authorizations (
    platform TEXT NOT NULL,
    source_id TEXT NOT NULL,
    basis TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    media_retrieval INTEGER NOT NULL DEFAULT 0,
    media_analysis INTEGER NOT NULL DEFAULT 0,
    temporary_processing INTEGER NOT NULL DEFAULT 0,
    derived_artifact_retention INTEGER NOT NULL DEFAULT 0,
    model_training INTEGER NOT NULL DEFAULT 0,
    revoked INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (platform, source_id)
);
CREATE TABLE IF NOT EXISTS media_processing (
    platform TEXT NOT NULL,
    source_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    media_path TEXT,
    media_sha256 TEXT,
    analysis_path TEXT,
    transcript_path TEXT,
    ocr_path TEXT,
    transcript_segments INTEGER NOT NULL DEFAULT 0,
    ocr_spans INTEGER NOT NULL DEFAULT 0,
    detected_language TEXT,
    asr_engine TEXT,
    ocr_engine TEXT,
    metric_value INTEGER,
    metric_kind TEXT,
    metric_is_estimate INTEGER NOT NULL DEFAULT 0,
    metric_display_value TEXT,
    rights_basis TEXT,
    evidence_ref TEXT,
    quality_flags_json TEXT NOT NULL DEFAULT '[]',
    started_at TEXT,
    completed_at TEXT,
    last_error TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (platform, source_id),
    FOREIGN KEY (platform, source_id)
        REFERENCES candidates(platform, source_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_media_processing_status
    ON media_processing(status, updated_at);
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

        # A newer exact observation supersedes an earlier rounded UI estimate.
        # Do not let stale estimate provenance keep an exact-count item out of
        # the default processing queue.
        if exact_metric := (
            effective_view_count if candidate.platform == "youtube"
            else effective_play_count if effective_play_count is not None
            else effective_view_count
        ):
            effective_metadata["metric_is_estimate"] = False
            effective_metadata["metric_precision"] = "exact_numeric"
            effective_metadata["metric_usage"] = "exact_platform_native_metric"
            effective_metadata.pop("metric_conservative_lower_bound", None)

        # Compare platform-native metrics without relabeling Instagram plays
        # as views. Reports must retain the metric kind and source.
        exact_metric = (
            effective_view_count if candidate.platform == "youtube"
            else effective_play_count if effective_play_count is not None
            else effective_view_count
        )
        metric = exact_metric if exact_metric is not None else candidate.qualifying_metric()

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
            "ORDER BY CASE WHEN platform='youtube' THEN view_count ELSE COALESCE(play_count, view_count) END DESC LIMIT ?", (limit,),
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

    def replace_rights_authorizations(
        self,
        authorizations: Iterable[AcquisitionAuthorization],
    ) -> int:
        """Atomically replace the private per-item rights index from a JSONL manifest."""
        timestamp = datetime.now(UTC).isoformat()
        count = 0
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute("DELETE FROM rights_authorizations")
            for item in authorizations:
                expires_at = (
                    item.expires_at.isoformat()
                    if item.expires_at is not None else None
                )
                self.connection.execute(
                    """INSERT INTO rights_authorizations(
                        platform, source_id, basis, evidence_ref, media_retrieval,
                        media_analysis, temporary_processing, derived_artifact_retention,
                        model_training, revoked, expires_at, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        item.platform, item.source_id, item.basis, item.evidence_ref,
                        int(item.media_retrieval), int(item.media_analysis),
                        int(item.temporary_processing), int(item.derived_artifact_retention),
                        int(item.model_training), int(item.revoked), expires_at, timestamp,
                    ),
                )
                count += 1
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return count

    def processing_candidates(
        self,
        *,
        min_metric: int = 1_000_000,
        allow_estimated_metrics: bool = False,
        limit: int = 25,
    ) -> list[
        tuple[
            DiscoveredCandidate,
            AcquisitionAuthorization,
            str | None,
            str,
            str | None,
        ]
    ]:
        """Return eligible, confirmed candidates with a current complete training grant.

        Exact YouTube views and exact Instagram-native metrics are preferred.
        Rounded Instagram display metrics can be included only with an explicit
        opt-in; the caller still marks those records as review-required.
        """
        maximum = max(0, int(limit))
        if maximum == 0:
            return []
        now = datetime.now(UTC).isoformat()
        cursor = self.connection.execute(
            """SELECT
                c.*,
                r.basis AS auth_basis,
                r.evidence_ref AS auth_evidence_ref,
                r.media_retrieval AS auth_media_retrieval,
                r.media_analysis AS auth_media_analysis,
                r.temporary_processing AS auth_temporary_processing,
                r.derived_artifact_retention AS auth_derived_artifact_retention,
                r.model_training AS auth_model_training,
                r.revoked AS auth_revoked,
                r.expires_at AS auth_expires_at
            FROM candidates AS c
            JOIN rights_authorizations AS r
              ON r.platform=c.platform AND r.source_id=c.source_id
            LEFT JOIN media_processing AS p
              ON p.platform=c.platform AND p.source_id=c.source_id
            WHERE c.status='eligible'
              AND c.short_format_status='confirmed'
              AND c.download_status IN ('not_downloaded','download_failed','downloaded')
              AND COALESCE(p.status, '') NOT IN ('complete','duplicate_media')
              AND CASE
                    WHEN c.platform='youtube' THEN COALESCE(c.view_count, 0)
                    ELSE COALESCE(
                        c.play_count,
                        c.view_count,
                        CAST(json_extract(c.metadata_json, '$.metric_conservative_lower_bound') AS INTEGER),
                        0
                    )
                  END >= ?
              AND r.media_retrieval=1
              AND r.media_analysis=1
              AND r.temporary_processing=1
              AND r.derived_artifact_retention=1
              AND r.model_training=1
              AND r.revoked=0
              AND (r.expires_at IS NULL OR r.expires_at > ?)
            ORDER BY
              CASE WHEN c.platform='youtube'
                   THEN COALESCE(c.view_count, 0)
                   ELSE COALESCE(
                       c.play_count,
                       c.view_count,
                       CAST(json_extract(c.metadata_json, '$.metric_conservative_lower_bound') AS INTEGER),
                       0
                   )
              END DESC,
              c.discovered_at ASC""",
            (int(min_metric), now),
        )
        output = []
        for row in cursor:
            candidate = self._candidate_from_row(row)
            if (
                candidate.metadata.get("metric_is_estimate") is True
                and not allow_estimated_metrics
            ):
                continue
            authorization = AcquisitionAuthorization(
                platform=row["platform"],
                source_id=row["source_id"],
                basis=row["auth_basis"],
                evidence_ref=row["auth_evidence_ref"],
                media_retrieval=bool(row["auth_media_retrieval"]),
                media_analysis=bool(row["auth_media_analysis"]),
                temporary_processing=bool(row["auth_temporary_processing"]),
                derived_artifact_retention=bool(row["auth_derived_artifact_retention"]),
                model_training=bool(row["auth_model_training"]),
                revoked=bool(row["auth_revoked"]),
                expires_at=(
                    datetime.fromisoformat(row["auth_expires_at"])
                    if row["auth_expires_at"] else None
                ),
            )
            output.append((
                candidate,
                authorization,
                row["download_path"],
                str(row["download_status"]),
                row["media_sha256"],
            ))
            if len(output) >= maximum:
                break
        return output

    def count_processing_blocked(self, *, min_metric: int = 1_000_000) -> int:
        """Count above-threshold, confirmed candidates lacking a current complete grant."""
        now = datetime.now(UTC).isoformat()
        row = self.connection.execute(
            """SELECT COUNT(*) AS n
            FROM candidates AS c
            LEFT JOIN media_processing AS p
              ON p.platform=c.platform AND p.source_id=c.source_id
            WHERE c.status='eligible'
              AND c.short_format_status='confirmed'
              AND c.download_status IN ('not_downloaded','download_failed','downloaded')
              AND COALESCE(p.status, '') NOT IN ('complete','duplicate_media')
              AND CASE
                    WHEN c.platform='youtube' THEN COALESCE(c.view_count, 0)
                    ELSE COALESCE(
                        c.play_count,
                        c.view_count,
                        CAST(json_extract(c.metadata_json, '$.metric_conservative_lower_bound') AS INTEGER),
                        0
                    )
                  END >= ?
              AND NOT EXISTS (
                SELECT 1 FROM rights_authorizations AS r
                WHERE r.platform=c.platform AND r.source_id=c.source_id
                  AND r.media_retrieval=1 AND r.media_analysis=1
                  AND r.temporary_processing=1 AND r.derived_artifact_retention=1
                  AND r.model_training=1 AND r.revoked=0
                  AND (r.expires_at IS NULL OR r.expires_at > ?)
              )""",
            (int(min_metric), now),
        ).fetchone()
        return int(row["n"]) if row else 0

    def mark_processing_started(
        self,
        candidate: DiscoveredCandidate,
        authorization: AcquisitionAuthorization,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        metric = candidate.qualifying_metric()
        is_estimate = candidate.metadata.get("metric_is_estimate") is True
        display_value = candidate.metadata.get("metric_display_value")
        self.connection.execute(
            """INSERT INTO media_processing(
                platform, source_id, status, attempts, metric_value, metric_kind,
                metric_is_estimate, metric_display_value, rights_basis, evidence_ref,
                started_at, last_error, updated_at
            ) VALUES(?,?,'processing',1,?,?,?,?,?,?,?,NULL,?)
            ON CONFLICT(platform, source_id) DO UPDATE SET
                status='processing',
                attempts=media_processing.attempts+1,
                metric_value=excluded.metric_value,
                metric_kind=excluded.metric_kind,
                metric_is_estimate=excluded.metric_is_estimate,
                metric_display_value=excluded.metric_display_value,
                rights_basis=excluded.rights_basis,
                evidence_ref=excluded.evidence_ref,
                started_at=excluded.started_at,
                completed_at=NULL,
                last_error=NULL,
                updated_at=excluded.updated_at""",
            (
                candidate.platform, candidate.source_id, metric,
                candidate.qualifying_metric_kind(), int(is_estimate),
                str(display_value) if display_value is not None else None,
                authorization.basis, authorization.evidence_ref, now, now,
            ),
        )
        self.connection.commit()

    def mark_processing_complete(
        self,
        platform: str,
        source_id: str,
        *,
        media_path: str,
        media_sha256: str,
        analysis_path: str,
        transcript_path: str,
        ocr_path: str,
        transcript_segments: int,
        ocr_spans: int,
        detected_language: str | None,
        asr_engine: str | None,
        ocr_engine: str | None,
        quality_flags: list[str],
    ) -> None:
        now = datetime.now(UTC).isoformat()
        self.connection.execute(
            """UPDATE media_processing SET
                status='complete',
                media_path=?, media_sha256=?, analysis_path=?,
                transcript_path=?, ocr_path=?,
                transcript_segments=?, ocr_spans=?, detected_language=?,
                asr_engine=?, ocr_engine=?, quality_flags_json=?,
                completed_at=?, last_error=NULL, updated_at=?
            WHERE platform=? AND source_id=?""",
            (
                media_path, media_sha256, analysis_path, transcript_path, ocr_path,
                transcript_segments, ocr_spans, detected_language, asr_engine, ocr_engine,
                json.dumps(quality_flags, ensure_ascii=False), now, now, platform, source_id,
            ),
        )
        self.connection.commit()

    def mark_processing_failure(
        self,
        platform: str,
        source_id: str,
        *,
        error: str,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        self.connection.execute(
            """UPDATE media_processing
            SET status='failed', last_error=?, updated_at=?
            WHERE platform=? AND source_id=?""",
            (error[:1000], now, platform, source_id),
        )
        self.connection.commit()

    def mark_processing_duplicate(
        self,
        platform: str,
        source_id: str,
        *,
        duplicate_of: str,
        media_sha256: str,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        self.connection.execute(
            """UPDATE media_processing SET status='duplicate_media',
                media_sha256=?, last_error=?, completed_at=?, updated_at=?
            WHERE platform=? AND source_id=?""",
            (
                media_sha256, f"Identical media already acquired as {duplicate_of}",
                now, now, platform, source_id,
            ),
        )
        self.connection.commit()

    def iter_processing_records(self) -> Iterator[dict[str, Any]]:
        """Stream completed records whose current grant still permits training."""
        now = datetime.now(UTC).isoformat()
        rows = self.connection.execute(
            """SELECT
                c.platform, c.source_id, c.canonical_url, c.title, c.description,
                c.creator, c.view_count, c.play_count, c.metric_source,
                c.duration_seconds, c.upload_date, c.hashtags_json, c.discovered_at,
                c.short_format_status, c.status AS candidate_status,
                c.metadata_json,
                p.status AS processing_status, p.media_path, p.media_sha256,
                p.analysis_path, p.transcript_path, p.ocr_path,
                p.transcript_segments, p.ocr_spans, p.detected_language,
                p.asr_engine, p.ocr_engine, p.metric_value, p.metric_kind,
                p.metric_is_estimate, p.metric_display_value, p.rights_basis,
                p.evidence_ref, p.quality_flags_json, p.completed_at,
                r.media_retrieval, r.media_analysis, r.temporary_processing,
                r.derived_artifact_retention, r.model_training
            FROM media_processing AS p
            JOIN candidates AS c
              ON c.platform=p.platform AND c.source_id=p.source_id
            JOIN rights_authorizations AS r
              ON r.platform=p.platform AND r.source_id=p.source_id
            WHERE p.status='complete'
              AND c.status='eligible' AND c.short_format_status='confirmed'
              AND r.media_retrieval=1 AND r.media_analysis=1
              AND r.temporary_processing=1 AND r.derived_artifact_retention=1
              AND r.model_training=1 AND r.revoked=0
              AND (r.expires_at IS NULL OR r.expires_at > ?)
            ORDER BY p.completed_at ASC""",
            (now,),
        )
        for row in rows:
            yield dict(row)

    def processing_records(self) -> list[dict[str, Any]]:
        """Return a materialized view for small inspection/test workloads."""
        return list(self.iter_processing_records())

    def processing_summary(self) -> dict[str, int]:
        rows = self.connection.execute(
            "SELECT status, COUNT(*) AS n FROM media_processing GROUP BY status"
        ).fetchall()
        return {str(row["status"]): int(row["n"]) for row in rows}

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
