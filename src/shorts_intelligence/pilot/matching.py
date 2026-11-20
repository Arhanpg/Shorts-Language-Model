"""Same-creator positive/control pair construction."""

from __future__ import annotations

from itertools import count

from shorts_intelligence.pilot.schemas import MatchPair, SelectedRecord


def build_matched_pairs(
    records: list[SelectedRecord],
    *,
    positive_threshold: float = 2.0,
    control_threshold: float = 0.5,
    max_publication_gap_days: int = 60,
    max_duration_gap_fraction: float = 0.30,
) -> list[MatchPair]:
    """Greedily match creator-relative outliers to same-creator controls.

    This generates comparison candidates, not causal pairs. Both records must have
    a computed creator-relative score using at least three comparable creator uploads.
    """
    if positive_threshold <= control_threshold:
        raise ValueError("positive threshold must exceed control threshold")
    positives = [
        item for item in records
        if item.creator_group and item.creator_relative_multiple is not None
        and item.creator_relative_multiple >= positive_threshold
        and item.published_at is not None
    ]
    controls = [
        item for item in records
        if item.creator_group and item.creator_relative_multiple is not None
        and item.creator_relative_multiple <= control_threshold
        and item.published_at is not None
    ]
    positives.sort(
        key=lambda item: item.creator_relative_multiple or 0, reverse=True
    )
    used_controls: set[str] = set()
    pairs: list[MatchPair] = []
    pair_index = count(1)

    for positive in positives:
        possible: list[tuple[float, SelectedRecord, int, float]] = []
        for control in controls:
            if control.record_id in used_controls:
                continue
            if control.creator_group != positive.creator_group:
                continue
            if control.platform != positive.platform:
                continue
            if control.language != positive.language or control.topic != positive.topic:
                continue
            if control.metric_name != positive.metric_name:
                continue
            if not positive.published_at or not control.published_at:
                continue
            publication_gap = abs(
                (positive.published_at - control.published_at).total_seconds()
            ) / 86400
            if publication_gap > max_publication_gap_days:
                continue
            duration_gap = abs(
                positive.duration_seconds - control.duration_seconds
            ) / max(positive.duration_seconds, control.duration_seconds, 0.001)
            if duration_gap > max_duration_gap_fraction:
                continue
            cost = publication_gap / max_publication_gap_days + duration_gap
            possible.append((cost, control, round(publication_gap), duration_gap))
        if not possible:
            continue
        _, control, publication_gap, duration_gap = min(
            possible, key=lambda item: (item[0], item[1].record_id)
        )
        used_controls.add(control.record_id)
        pairs.append(MatchPair(
            pair_id=f"pair_{next(pair_index):04d}",
            positive_record_id=positive.record_id,
            control_record_id=control.record_id,
            creator_group=positive.creator_group or "",
            platform=positive.platform,
            language=positive.language,
            topic=positive.topic,
            positive_relative_multiple=positive.creator_relative_multiple or 0,
            control_relative_multiple=control.creator_relative_multiple or 0,
            publication_gap_days=publication_gap,
            duration_gap_fraction=round(duration_gap, 4),
        ))
    return pairs
