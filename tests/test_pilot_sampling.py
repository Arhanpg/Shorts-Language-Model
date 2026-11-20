from datetime import UTC, datetime, timedelta
from pathlib import Path

from shorts_intelligence.pilot.manifest import ValidatedCandidate
from shorts_intelligence.pilot.matching import build_matched_pairs
from shorts_intelligence.pilot.sampling import (
    _relative_performance,
    age_band,
    duration_band,
    pseudonymize_creator,
    select_stratified,
)
from shorts_intelligence.pilot.schemas import (
    PerformanceSnapshot,
    PilotRecord,
    RightsScope,
    SelectedRecord,
)


def _candidate(
    index: int, *, creator: str, value: int, topic: str = "cricket"
) -> ValidatedCandidate:
    published = datetime(2026, 10, 1, tzinfo=UTC) + timedelta(days=index)
    observed = datetime(2026, 11, 20, tzinfo=UTC)
    record = PilotRecord(
        record_id=f"clip_{index:04d}",
        platform="creator_upload",
        media_path=f"clip_{index}.mp4",
        creator_id=creator,
        rights=RightsScope(
            basis="creator_owned", evidence_ref=f"owner-{creator}",
            media_analysis=True, temporary_processing=True,
            derived_artifact_retention=True,
        ),
        language="hi",
        topic=topic,
        speech_mode="music_only",
        published_at=published,
        performance=PerformanceSnapshot(
            metric_name="views", value=value, observed_at=observed,
        ),
    )
    return ValidatedCandidate(
        row_number=index + 1, record=record,
        media_path=Path(f"/tmp/clip_{index}.mp4"),
        media_sha256=f"{index:064x}", file_size_bytes=1000,
        duration_seconds=24.0,
    )


def test_duration_and_age_bands() -> None:
    assert duration_band(15) == "00-15s"
    assert duration_band(30) == "16-30s"
    assert age_band(None, None) == "unknown"


def test_creator_pseudonym_is_stable_and_platform_scoped() -> None:
    salt = b"x" * 32
    first = pseudonymize_creator("creator_upload", "creator-1", salt)
    assert first == pseudonymize_creator("creator_upload", "creator-1", salt)
    assert first != pseudonymize_creator("youtube_shorts", "creator-1", salt)


def test_stratified_sampler_is_deterministic_and_respects_cap() -> None:
    candidates = [
        _candidate(i, creator=f"creator-{i // 3}", value=1000 + i * 100)
        for i in range(30)
    ]
    first, summary1 = select_stratified(
        candidates, target=12, seed=7, max_per_creator=2, salt=b"z" * 32
    )
    second, summary2 = select_stratified(
        candidates, target=12, seed=7, max_per_creator=2, salt=b"z" * 32
    )
    assert [item.record_id for item in first] == [item.record_id for item in second]
    assert summary1["selected"] == 12
    assert summary1["unique_creator_groups_in_selection"] >= 6
    assert summary1["coverage"] == summary2["coverage"]


def test_matched_pairs_require_same_creator_and_outlier_thresholds() -> None:
    base = dict(
        platform="creator_upload", media_path="/tmp/a.mp4",
        media_sha256="a" * 64, file_size_bytes=1000,
        creator_group="creator-hash", rights_basis="creator_owned",
        rights_reference_hash="b" * 64, media_analysis_permitted=True,
        temporary_processing_permitted=True, derived_artifact_retention_permitted=True,
        model_training_permitted=False, language="hi", topic="cricket",
        speech_mode="music_only", duration_seconds=24.0, duration_band="16-30s",
        age_band="31-90d", metric_name="views", metric_value=10000,
        observed_at=datetime(2026, 11, 20, tzinfo=UTC),
    )
    positive = SelectedRecord(
        record_id="positive", published_at=datetime(2026, 10, 10, tzinfo=UTC),
        creator_relative_log_score=1.4, creator_relative_multiple=4.0,
        performance_tier="breakout_2x_5x", **base
    )
    control_fields = {
        key: value for key, value in base.items()
        if key not in {"media_path", "media_sha256"}
    }
    control = SelectedRecord(
        record_id="control", media_path="/tmp/b.mp4", media_sha256="c" * 64,
        published_at=datetime(2026, 10, 12, tzinfo=UTC),
        creator_relative_log_score=-1.0, creator_relative_multiple=0.35,
        performance_tier="below_baseline", **control_fields
    )
    pairs = build_matched_pairs([positive, control])
    assert len(pairs) == 1
    assert pairs[0].positive_record_id == "positive"
    assert pairs[0].control_record_id == "control"

def test_creator_baseline_is_separated_by_language_and_topic() -> None:
    candidates = [
        _candidate(0, creator="creator-A", value=1000, topic="cricket"),
        _candidate(1, creator="creator-A", value=1100, topic="cricket"),
        _candidate(2, creator="creator-A", value=900, topic="cricket"),
        _candidate(3, creator="creator-A", value=100000, topic="cooking"),
    ]
    groups = {item.record.record_id: "same-pseudonymous-creator" for item in candidates}
    scores = _relative_performance(candidates, groups)
    assert all(item.record.record_id in scores for item in candidates[:3])
    assert candidates[3].record.record_id not in scores


def test_sampler_reports_shortfall_when_creator_cap_is_reached() -> None:
    candidates = [
        _candidate(index, creator="one-creator", value=1000 + index * 10)
        for index in range(6)
    ]
    selected, summary = select_stratified(
        candidates, target=4, seed=11, max_per_creator=2, salt=b"s" * 32
    )
    assert len(selected) == 2
    assert summary["target"] == 4
    assert summary["shortfall"] == 2
