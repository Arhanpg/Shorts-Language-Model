from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import numpy as np

from shorts_intelligence.schemas import FrameEvidence
from shorts_intelligence.telemetry.ocr import run_ocr


def test_paddleocr_v3_disables_onednn_for_cpu(monkeypatch):
    constructor_options: dict[str, object] = {}

    class FakePaddleOCR:
        def __init__(self, **kwargs):
            constructor_options.update(kwargs)

        def predict(self, image):
            return [
                SimpleNamespace(
                    json={
                        "res": {
                            "rec_texts": ["sample text"],
                            "rec_scores": [0.98],
                            "rec_boxes": [[1, 2, 30, 20]],
                        }
                    }
                )
            ]

    fake_paddle = ModuleType("paddle")
    fake_paddle.is_compiled_with_cuda = lambda: False
    fake_paddleocr = ModuleType("paddleocr")
    fake_paddleocr.PaddleOCR = FakePaddleOCR

    monkeypatch.setitem(sys.modules, "paddle", fake_paddle)
    monkeypatch.setitem(sys.modules, "paddleocr", fake_paddleocr)

    evidence = FrameEvidence(
        timestamp_seconds=0.0,
        frame_index=0,
        reason=["preflight"],
        motion_score=0.0,
    )
    image = np.zeros((64, 128, 3), dtype=np.uint8)

    spans, engine_name = run_ocr(
        [(evidence, image)],
        max_frames=1,
        prefer_gpu=False,
    )

    assert constructor_options["enable_mkldnn"] is False
    assert constructor_options["device"] == "cpu"
    assert engine_name == "paddleocr-3-cpu"
    assert len(spans) == 1
    assert spans[0].text == "sample text"
    assert spans[0].text_normalized == "sample text"
    assert spans[0].script == "Latn"
    assert spans[0].accepted_candidate is True
    assert spans[0].bbox_normalized_xyxy == [1 / 128, 2 / 64, 30 / 128, 20 / 64]
    assert spans[0].track_id == "ocr_00000"
