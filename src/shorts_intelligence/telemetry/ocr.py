"""OCR adapter that reuses VidTrace's maintained PaddleOCR wrapper when present."""

from __future__ import annotations

import logging
import re
from typing import Any

import numpy as np

from shorts_intelligence.schemas import FrameEvidence, OCRSpan

logger = logging.getLogger(__name__)


class OCRError(RuntimeError):
    """Raised when an OCR engine fails to initialize or execute."""


def _ocr_script(text: str) -> str:
    ranges = {
        "Latn": ((0x0041, 0x024F),), "Deva": ((0x0900, 0x097F),),
        "Beng": ((0x0980, 0x09FF),), "Taml": ((0x0B80, 0x0BFF),),
        "Telu": ((0x0C00, 0x0C7F),), "Knda": ((0x0C80, 0x0CFF),),
        "Mlym": ((0x0D00, 0x0D7F),), "Thai": ((0x0E00, 0x0E7F),),
        "Arab": ((0x0600, 0x06FF),), "Cyrl": ((0x0400, 0x052F),),
        "Hang": ((0xAC00, 0xD7AF),), "Hani": ((0x4E00, 0x9FFF),),
    }
    found = set()
    for char in text:
        for label, blocks in ranges.items():
            if any(start <= ord(char) <= end for start, end in blocks):
                found.add(label)
                break
    return "Zyyy" if not found else "Mixed" if len(found) > 1 else next(iter(found))


def _bbox_iou(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right:
        return 1.0
    x1, y1 = max(left[0], right[0]), max(left[1], right[1])
    x2, y2 = min(left[2], right[2]), min(left[3], right[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_left = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    area_right = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = area_left + area_right - intersection
    return intersection / union if union > 0 else 0.0


def _enrich_ocr_spans(spans, selected_frames, confidence_threshold: float):
    """Keep every raw detection; add normalized geometry, script, QA flags and temporal IDs."""
    import unicodedata

    dimensions = {
        evidence.frame_index: (image.shape[1], image.shape[0])
        for evidence, image in selected_frames
    }
    prepared = []
    for span in spans:
        normalized_text = " ".join(unicodedata.normalize("NFC", span.text).split())
        width, height = dimensions.get(span.frame_index, (0, 0))
        box = span.bbox_xyxy
        normalized_box = None
        if box and width > 0 and height > 0 and len(box) >= 4:
            normalized_box = [
                min(1.0, max(0.0, float(box[0]) / width)),
                min(1.0, max(0.0, float(box[1]) / height)),
                min(1.0, max(0.0, float(box[2]) / width)),
                min(1.0, max(0.0, float(box[3]) / height)),
            ]
        flags = []
        if span.confidence < confidence_threshold:
            flags.append("below_provisional_confidence_threshold")
        if len(normalized_text) < 2:
            flags.append("short_text_candidate")
        accepted = span.confidence >= confidence_threshold and len(normalized_text) >= 2
        prepared.append(span.model_copy(update={
            "text_normalized": normalized_text,
            "script": _ocr_script(normalized_text),
            "bbox_normalized_xyxy": normalized_box,
            "quality_status": "accepted_candidate" if accepted else "needs_review",
            "quality_flags": flags,
            "accepted_candidate": accepted,
        }))

    tracks = []
    output = []
    for span in sorted(prepared, key=lambda item: (item.timestamp_seconds, item.frame_index)):
        key = span.text_normalized.casefold() if span.text_normalized else span.text
        best_track = None
        best_iou = 0.0
        for track in tracks:
            if track["key"] != key:
                continue
            gap = span.timestamp_seconds - track["last_time"]
            if gap < 0 or gap > 1.25:
                continue
            overlap = _bbox_iou(span.bbox_normalized_xyxy, track["last_box"])
            if overlap >= 0.25 and overlap >= best_iou:
                best_track, best_iou = track, overlap
        if best_track is None:
            best_track = {
                "key": key,
                "track_id": f"ocr_{len(tracks):05d}",
                "first_time": span.timestamp_seconds,
                "last_time": span.timestamp_seconds,
                "last_box": span.bbox_normalized_xyxy,
            }
            tracks.append(best_track)
        best_track["last_time"] = span.timestamp_seconds
        best_track["last_box"] = span.bbox_normalized_xyxy
        output.append(span.model_copy(update={
            "track_id": best_track["track_id"],
            "track_start_seconds": best_track["first_time"],
            "track_end_seconds": best_track["last_time"],
        }))
    return output



def run_ocr(
    frames: list[tuple[FrameEvidence, np.ndarray]],
    max_frames: int = 12,
    prefer_gpu: bool = True,
    confidence_threshold: float = 0.50,
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
            return _enrich_ocr_spans(spans, chosen, confidence_threshold), f"vidtrace-paddleocr-{actual_device}"
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
            # The Colab traceback fails inside the oneDNN/PIR CPU executor.
            # Disable MKL-DNN so PaddleOCR does not select that execution path.
            enable_mkldnn=False,
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
    return _enrich_ocr_spans(spans, chosen, confidence_threshold), f"{version}-{actual_device}"
