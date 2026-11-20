"""Hook-aware frame sampling and approximate cut/motion telemetry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from shorts_intelligence.config import AnalyzerConfig
from shorts_intelligence.schemas import CutCandidate, FrameEvidence, MotionSample


@dataclass(slots=True)
class SampledFrame:
    evidence: FrameEvidence
    image: np.ndarray


@dataclass(slots=True)
class SamplingResult:
    frames: list[SampledFrame]
    cuts: list[CutCandidate]
    motion_samples: list[MotionSample]
    mean_motion: float
    p95_motion: float
    peak_timestamp: float | None
    hook_frame_count: int


def _resize(frame: np.ndarray, width: int) -> np.ndarray:
    height, original_width = frame.shape[:2]
    if original_width <= width:
        return frame
    target_height = max(1, round(height * width / original_width))
    return cv2.resize(frame, (width, target_height), interpolation=cv2.INTER_AREA)


def _signature(frame: np.ndarray) -> np.ndarray:
    small = cv2.resize(frame, (96, 54), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256])
    cv2.normalize(hist, hist, alpha=1.0, norm_type=cv2.NORM_L1)
    return hist


def _histogram_difference(a: np.ndarray | None, b: np.ndarray) -> float:
    if a is None:
        return 0.0
    return float(
        cv2.compareHist(
            a.astype(np.float32), b.astype(np.float32), cv2.HISTCMP_BHATTACHARYYA
        )
    )


def _optical_flow_magnitude(previous: np.ndarray | None, current: np.ndarray) -> float:
    if previous is None:
        return 0.0
    prev_gray = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
    curr_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
    flow = cv2.calcOpticalFlowFarneback(
        prev_gray, curr_gray, None, 0.5, 2, 15, 2, 5, 1.1, 0
    )
    return float(np.mean(np.linalg.norm(flow, axis=2)))


def _select_frames(
    candidates: list[SampledFrame], max_frames: int
) -> list[SampledFrame]:
    """Select a temporally distributed subset; retained for direct unit testing."""
    if len(candidates) <= max_frames:
        return candidates
    hook = [item for item in candidates if "hook_window" in item.evidence.reason]
    cut = [item for item in candidates if "cut_candidate" in item.evidence.reason]
    selected: dict[int, SampledFrame] = {
        item.evidence.frame_index: item for item in hook[:max_frames // 3]
    }
    for item in cut:
        if len(selected) >= max_frames * 2 // 3:
            break
        selected[item.evidence.frame_index] = item
    remaining = [
        item for item in candidates if item.evidence.frame_index not in selected
    ]
    slots = max(0, max_frames - len(selected))
    if slots and remaining:
        targets = np.linspace(
            0, len(remaining) - 1, num=min(slots, len(remaining)), dtype=int
        )
        for index in targets:
            item = remaining[int(index)]
            selected[item.evidence.frame_index] = item
    if len(selected) < max_frames:
        leftovers = sorted(
            (item for item in candidates if item.evidence.frame_index not in selected),
            key=lambda item: item.evidence.motion_score,
            reverse=True,
        )
        for item in leftovers[:max_frames - len(selected)]:
            selected[item.evidence.frame_index] = item
    return sorted(
        selected.values(), key=lambda item: item.evidence.timestamp_seconds
    )


def sample_video(path: Path, duration: float, config: AnalyzerConfig) -> SamplingResult:
    """Decode sequentially while retaining a bounded number of keyframe images.

    The opening hook is sampled densely. The remaining frame budget is split
    into temporal bins; each bin retains its most informative sampled frame.
    """
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(
            "OpenCV could not open the video. Check FFmpeg codec support."
        )
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    if fps <= 0:
        fps = 30.0
    frame_index = -1
    next_sample_time = 0.0
    previous_signature: np.ndarray | None = None
    previous_small: np.ndarray | None = None
    hook_frames: list[SampledFrame] = []
    temporal_bins: dict[int, tuple[float, SampledFrame]] = {}
    cuts: list[CutCandidate] = []
    motions: list[MotionSample] = []
    all_motion: list[float] = []

    hook_end = min(duration, config.hook_window_seconds)
    hook_cap = min(
        max(1, config.max_keyframes // 3),
        max(1, int(np.ceil(hook_end / config.analysis_sample_interval_seconds))),
    )
    hook_cap = min(hook_cap, max(1, config.max_keyframes - 1))
    remaining_slots = max(0, config.max_keyframes - hook_cap)
    remaining_duration = max(0.001, duration - hook_end)

    try:
        while True:
            ok, raw = capture.read()
            if not ok:
                break
            frame_index += 1
            timestamp = min(frame_index / fps, duration)
            if timestamp + 0.001 < next_sample_time:
                continue
            if timestamp > duration + 0.05:
                break
            sample_interval = (
                config.hook_sample_interval_seconds
                if timestamp <= min(duration, config.hook_window_seconds)
                else config.analysis_sample_interval_seconds
            )
            next_sample_time = timestamp + sample_interval

            preview = _resize(raw, config.keyframe_width)
            small = _resize(raw, config.motion_resize_width)
            signature = _signature(preview)
            difference = _histogram_difference(previous_signature, signature)
            flow = _optical_flow_magnitude(previous_small, small)
            previous_signature, previous_small = signature, small
            all_motion.append(flow)
            motions.append(
                MotionSample(timestamp_seconds=timestamp, mean_flow_magnitude=flow)
            )

            reasons: list[str] = []
            if timestamp <= hook_end:
                reasons.append("hook_window")
            if difference >= config.cut_threshold:
                reasons.append("cut_candidate")
                cuts.append(
                    CutCandidate(
                        timestamp_seconds=timestamp,
                        visual_difference=min(1.0, max(0.0, difference)),
                        confidence=min(0.95, max(0.1, difference)),
                    )
                )
            if flow >= 1.5:
                reasons.append("motion_peak_candidate")

            if timestamp <= hook_end:
                if len(hook_frames) < hook_cap:
                    hook_frames.append(
                        SampledFrame(
                            evidence=FrameEvidence(
                                timestamp_seconds=timestamp,
                                frame_index=frame_index,
                                reason=reasons or ["hook_window"],
                                motion_score=flow,
                            ),
                            image=preview,
                        )
                    )
                continue

            if remaining_slots <= 0:
                continue
            bin_index = min(
                remaining_slots - 1,
                max(
                    0,
                    int((timestamp - hook_end) / remaining_duration * remaining_slots),
                ),
            )
            reasons.append("temporal_bin")
            candidate = SampledFrame(
                evidence=FrameEvidence(
                    timestamp_seconds=timestamp,
                    frame_index=frame_index,
                    reason=reasons,
                    motion_score=flow,
                ),
                image=preview,
            )
            score = (
                0.65 * min(1.0, max(0.0, difference))
                + 0.35 * min(1.0, max(0.0, flow / 20.0))
            )
            previous = temporal_bins.get(bin_index)
            if previous is None or score > previous[0]:
                temporal_bins[bin_index] = (score, candidate)
    finally:
        capture.release()

    selected = hook_frames + [
        item
        for _, item in sorted(
            temporal_bins.values(),
            key=lambda pair: pair[1].evidence.timestamp_seconds,
        )
    ]
    selected = sorted(selected, key=lambda item: item.evidence.timestamp_seconds)
    values = np.asarray(all_motion, dtype=np.float32)
    mean_motion = float(np.mean(values)) if values.size else 0.0
    p95_motion = float(np.percentile(values, 95)) if values.size else 0.0
    peak_index = int(np.argmax(values)) if values.size else None
    peak_time = motions[peak_index].timestamp_seconds if peak_index is not None else None
    hook_count = sum(
        "hook_window" in item.evidence.reason for item in selected
    )
    return SamplingResult(
        frames=selected[:config.max_keyframes],
        cuts=cuts,
        motion_samples=motions,
        mean_motion=mean_motion,
        p95_motion=p95_motion,
        peak_timestamp=peak_time,
        hook_frame_count=hook_count,
    )
