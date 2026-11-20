import numpy as np

from shorts_intelligence.media.sampling import SampledFrame, _select_frames
from shorts_intelligence.schemas import FrameEvidence


def test_frame_selector_respects_maximum_and_time_order() -> None:
    candidates = [
        SampledFrame(
            evidence=FrameEvidence(
                timestamp_seconds=float(index),
                frame_index=index,
                reason=["hook_window"] if index < 3 else ["uniform_1fps"],
                motion_score=float(index),
            ),
            image=np.zeros((10, 10, 3), dtype=np.uint8),
        )
        for index in range(20)
    ]
    selected = _select_frames(candidates, max_frames=8)
    assert len(selected) <= 8
    timestamps = [item.evidence.timestamp_seconds for item in selected]
    assert timestamps == sorted(timestamps)
    assert any(item.evidence.timestamp_seconds < 3 for item in selected)
