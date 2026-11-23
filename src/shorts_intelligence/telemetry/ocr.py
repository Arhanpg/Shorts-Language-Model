"""OCR adapter that reuses VidTrace's maintained PaddleOCR wrapper when present."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from shorts_intelligence.schemas import FrameEvidence, OCRSpan


logger = logging.getLogger(__name__)


class OCRError(RuntimeError):
    """Raised when an OCR engine fails to initialize or execute."""


def run_ocr(
    frames: list[tuple[FrameEvidence, np.ndarray]],
    max_frames: int = 12,
    prefer_gpu: bool = True,
) -> tuple[list[OCRSpan], str]:
    """OCR selected frames, preferring CUDA when PaddlePaddle has GPU support."""
    if not frames:
        return [], "not-run-no-frames"

    paddle_cuda_available = False
    try:
        import paddle
        paddle_cuda_available = bool(paddle.is_compiled_with_cuda())
    except Exception as exc:
        logger.warning("Could not inspect PaddlePaddle CUDA support: %s", exc)
    if prefer_gpu and not paddle_cuda_available:
        logger.warning(
            "CUDA was requested for PaddleOCR, but the installed PaddlePaddle build "
            "does not have CUDA support. OCR will run on CPU. Install the Windows "
            "paddlepaddle-gpu wheel and re-check paddle.is_compiled_with_cuda()."
        )

    # Spread OCR across the full video while reserving coverage for the hook
    # and scenes where the visual telemetry detected a candidate cut.
    hook_frames = [
        item for item in frames if "hook_window" in item[0].reason
    ]
    cut_frames = [
        item for item in frames if "cut_candidate" in item[0].reason
    ]
    chosen_map: dict[int, tuple[FrameEvidence, np.ndarray]] = {}
    hook_budget = min(max(2, max_frames // 3), max_frames)
    if hook_frames:
        hook_indices = np.linspace(
            0, len(hook_frames) - 1,
            num=min(hook_budget, len(hook_frames)), dtype=int,
        )
        for index in hook_indices:
            evidence, image = hook_frames[int(index)]
            chosen_map[evidence.frame_index] = (evidence, image)
    cut_budget = max(0, max_frames // 3)
    for evidence, image in cut_frames:
        if len(chosen_map) >= hook_budget + cut_budget:
            break
        chosen_map[evidence.frame_index] = (evidence, image)
    remaining = [
        item for item in frames if item[0].frame_index not in chosen_map
    ]
    slots = max(0, max_frames - len(chosen_map))
    if remaining and slots:
        indices = np.linspace(
            0, len(remaining) - 1,
            num=min(slots, len(remaining)), dtype=int,
        )
        for index in indices:
            evidence, image = remaining[int(index)]
            chosen_map[evidence.frame_index] = (evidence, image)
    chosen = sorted(
        chosen_map.values(), key=lambda item: item[0].timestamp_seconds
    )[:max_frames]

    try:
        from vidtrace.vision.ocr import PaddleOCREngine

        engine = PaddleOCREngine(prefer_gpu=prefer_gpu)
        spans: list[OCRSpan] = []
        try:
            for evidence, image in chosen:
                boxes, _variant = engine.run(image)
                for box in boxes:
                    text = str(box.text).strip()
                    if not text:
                        continue
                    spans.append(OCRSpan(
                        timestamp_seconds=evidence.timestamp_seconds,
                        text=text,
                        confidence=min(1.0, max(0.0, float(box.confidence))),
                        bbox_xyxy=[
                            int(box.x1), int(box.y1), int(box.x2), int(box.y2)
                        ],
                        engine="vidtrace-paddleocr",
                        frame_index=evidence.frame_index,
                    ))
            actual_device = str(getattr(engine, "device", "unknown")).replace(":", "-")
            return spans, f"vidtrace-paddleocr-{actual_device}"
        finally:
            close = getattr(engine, "close", None)
            if callable(close):
                close()
    except ImportError:
        pass
    except Exception as exc:
        raise OCRError(
            f"VidTrace PaddleOCR adapter failed: {type(exc).__name__}: {exc}"
        ) from exc

    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise OCRError(
            "PaddleOCR is not installed. Install the ShortsLM OCR extra "
            "or install your existing VidTrace checkout with its OCR extra."
        ) from exc

    try:
        engine: Any = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device="gpu:0" if prefer_gpu and paddle_cuda_available else "cpu",
        )
        version = "paddleocr-3"
    except TypeError:
        engine = PaddleOCR(
            use_angle_cls=True, lang="en", show_log=False,
            use_gpu=prefer_gpu and paddle_cuda_available
        )
        version = "paddleocr-2"

    spans = []
    actual_device = "gpu-0" if prefer_gpu and paddle_cuda_available else "cpu"
    for evidence, image in chosen:
        if version == "paddleocr-3":
            results = engine.predict(image)
            for result in results:
                data = getattr(result, "json", {})
                if callable(data):
                    data = data()
                if isinstance(data, dict) and "res" in data:
                    data = data["res"]
                texts = data.get("rec_texts", []) if isinstance(data, dict) else []
                scores = data.get("rec_scores", []) if isinstance(data, dict) else []
                boxes = data.get("rec_boxes", []) if isinstance(data, dict) else []
                for index, text in enumerate(texts):
                    if not str(text).strip():
                        continue
                    box = boxes[index] if index < len(boxes) else None
                    spans.append(OCRSpan(
                        timestamp_seconds=evidence.timestamp_seconds,
                        text=str(text).strip(),
                        confidence=float(scores[index]) if index < len(scores) else 0.5,
                        bbox_xyxy=[int(value) for value in box] if box is not None else None,
                        engine=version,
                        frame_index=evidence.frame_index,
                    ))
        else:
            results = engine.ocr(image, cls=True) or []
            for line in (results[0] if results else []):
                box, content = line
                text, confidence = content
                if str(text).strip():
                    points = np.asarray(box)
                    bbox = [
                        int(points[:, 0].min()), int(points[:, 1].min()),
                        int(points[:, 0].max()), int(points[:, 1].max()),
                    ]
                    spans.append(OCRSpan(
                        timestamp_seconds=evidence.timestamp_seconds,
                        text=str(text).strip(),
                        confidence=float(confidence),
                        bbox_xyxy=bbox,
                        engine=version,
                        frame_index=evidence.frame_index,
                    ))
    return spans, f"{version}-{actual_device}"
