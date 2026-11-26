"""Canonical, versioned evidence bundle assembly for ShortsLM."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

BUNDLE_VERSION = "3.0.0"


def _dump(value: Any) -> Any:
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def build_feature_bundle(
    *,
    video: Any,
    hook_window: Any,
    frame_evidence: list[Any],
    cut_candidates: list[Any],
    motion: Any,
    transcript_segments: list[Any],
    ocr_spans: list[Any],
    audio: Any,
    stages: dict[str, Any],
    warnings: list[str],
    rights: Any,
    config: Any,
) -> dict[str, Any]:
    transcript_items = [_dump(item) for item in transcript_segments]
    ocr_items = [_dump(item) for item in ocr_spans]
    frames = [_dump(item) for item in frame_evidence]
    cuts = [_dump(item) for item in cut_candidates]
    stage_items = {name: _dump(value) for name, value in stages.items()}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for span in ocr_items:
        groups[span.get("track_id") or f"ocr_{span['frame_index']:05d}"].append(span)
    tracklets = []
    for track_id, observations in groups.items():
        observations.sort(key=lambda item: item["timestamp_seconds"])
        tracklets.append({
            "track_id": track_id,
            "text": observations[0].get("text_normalized") or observations[0]["text"],
            "script": observations[0].get("script", "Zyyy"),
            "start_seconds": min(item.get("track_start_seconds") or item["timestamp_seconds"] for item in observations),
            "end_seconds": max(item.get("track_end_seconds") or item["timestamp_seconds"] for item in observations),
            "observation_count": len(observations),
            "mean_confidence": sum(item["confidence"] for item in observations) / len(observations),
            "observations": observations,
        })

    events: list[dict[str, Any]] = []
    for index, segment in enumerate(transcript_items):
        events.append({
            "event_id": f"asr_{index:05d}", "modality": "audio",
            "event_type": "speech_transcript", "start_seconds": segment["start_seconds"],
            "end_seconds": segment["end_seconds"],
            "payload": {"text": segment["text"], "language": segment.get("language")},
            "confidence": segment.get("confidence"), "status": "PRESENT",
            "extractor": "faster-whisper",
        })
    for index, tracklet in enumerate(tracklets):
        events.append({
            "event_id": f"ocr_{index:05d}", "modality": "visual",
            "event_type": "on_screen_text", "start_seconds": tracklet["start_seconds"],
            "end_seconds": tracklet["end_seconds"],
            "payload": {"text": tracklet["text"], "script": tracklet["script"]},
            "confidence": tracklet["mean_confidence"],
            "status": "PRESENT" if all(x.get("accepted_candidate") for x in tracklet["observations"]) else "BELOW_CONFIDENCE_THRESHOLD",
            "extractor": "paddleocr",
        })
    for index, cut in enumerate(cuts):
        events.append({
            "event_id": f"cut_{index:05d}", "modality": "visual",
            "event_type": "shot_boundary_candidate",
            "start_seconds": cut["timestamp_seconds"], "end_seconds": cut["timestamp_seconds"],
            "payload": {"visual_difference": cut["visual_difference"]},
            "confidence": cut["confidence"], "status": "PRESENT",
            "extractor": cut.get("detector", "opencv"),
        })
    audio_items = _dump(audio)
    for index, beat in enumerate(audio_items.get("beat_times_seconds", [])):
        events.append({
            "event_id": f"beat_{index:05d}", "modality": "audio",
            "event_type": "beat_candidate", "start_seconds": beat, "end_seconds": beat,
            "payload": {}, "confidence": None, "status": "PRESENT",
            "extractor": audio_items.get("method") or "librosa",
        })
    events.sort(key=lambda item: (item["start_seconds"], item["event_id"]))
    languages = sorted({x.get("language") for x in transcript_items if x.get("language")})
    scripts = sorted({x.get("script") for x in transcript_items if x.get("script")})
    flagged_segments = sum(bool(x.get("quality_flags")) for x in transcript_items)
    accepted_ocr = sum(bool(x.get("accepted_candidate")) for x in ocr_items)
    review_required = (
        any(x.get("status") in {"partial", "failed"} for x in stage_items.values())
        or flagged_segments > 0 or accepted_ocr < len(ocr_items)
    )
    semantic = {
        "person_pose": {"status": "NOT_YET_PROCESSED", "phase": "P1", "reason": "Requires P0 quality gates and one licensed runtime benchmark."},
        "general_actions": {"status": "NOT_YET_PROCESSED", "phase": "P1", "reason": "Requires a selected action model and human-reviewed action taxonomy."},
        "objects_and_interactions": {"status": "NOT_YET_PROCESSED", "phase": "P1", "reason": "Requires detector license review and held-out evaluation."},
        "scene_context": {"status": "NOT_YET_PROCESSED", "phase": "P1", "reason": "Requires a measured scene classifier or reviewed VLM-assisted labels."},
        "music_and_sound_events": {"status": "NOT_YET_PROCESSED", "phase": "P1", "reason": "Signal descriptors are present; no music ID or sound-event classifier is claimed."},
        "text_speech_relation": {"status": "NOT_YET_PROCESSED", "phase": "P1", "reason": "Requires aligned text/audio pairs and reviewed labels."},
        "narrative_structure": {"status": "NOT_YET_PROCESSED", "phase": "P1", "reason": "Requires human-reviewed temporal labels."},
        "speaker_diarization": {"status": "NOT_YET_PROCESSED", "phase": "P2", "reason": "Deferred pending task validation and model selection."},
        "fine_grained_dance": {"status": "NOT_YET_PROCESSED", "phase": "P2", "reason": "Deferred pending reviewed taxonomy and class-wise benchmark."},
    }
    if transcript_items:
        speech_presence = {
            "status": "PRESENT",
            "reason": "At least one timestamped ASR segment was returned.",
        }
    elif not getattr(video, "audio_present", False):
        speech_presence = {
            "status": "ABSENT_IN_MEDIA",
            "reason": "The source media has no audio stream.",
        }
    else:
        speech_presence = {
            "status": "NOT_YET_PROCESSED",
            "reason": "ASR returned no segments after retry. Independent VAD or human review is required before marking speech absent.",
        }
    return {
        "bundle_version": BUNDLE_VERSION,
        "video_manifest": _dump(video),
        "transcript": {
            "segments": transcript_items, "segment_count": len(transcript_items),
            "language_codes": languages, "script_codes": scripts,
            "speech_presence": speech_presence,
            "quality": {"segments_flagged_for_review": flagged_segments, "quality_thresholds_calibrated": False,
                        "note": "Whisper decoding diagnostics are retained as review heuristics, not calibrated probabilities."},
        },
        "ocr": {
            "raw_candidates": ocr_items, "tracklets": tracklets,
            "raw_candidate_count": len(ocr_items), "accepted_candidate_count": accepted_ocr,
            "confidence_threshold": getattr(config, "ocr_confidence_threshold", 0.50),
            "threshold_calibration": "provisional_not_calibrated",
        },
        "audio_features": audio_items,
        "visual_features": {
            "hook_window": _dump(hook_window), "frames": frames,
            "cut_candidates": cuts, "motion": _dump(motion),
        },
        "temporal_events": events,
        "semantic_features": semantic,
        "quality_report": {
            "stage_statuses": stage_items, "warnings": list(warnings),
            "transcript_segments": len(transcript_items),
            "transcript_segments_flagged_for_review": flagged_segments,
            "ocr_raw_candidates": len(ocr_items), "ocr_accepted_candidates": accepted_ocr,
            "human_review_recommended": review_required,
        },
        "provenance": {
            "pipeline": "ShortsLM Phase 1 evidence extraction", "bundle_version": BUNDLE_VERSION,
            "rights_declaration": _dump(rights) if rights is not None else None,
            "config": {
                "asr_model": getattr(config, "asr_model", None),
                "asr_device_requested": getattr(config, "asr_device", None),
                "asr_compute_type": getattr(config, "asr_compute_type", None),
                "ocr_max_frames": getattr(config, "max_ocr_frames", None),
                "ocr_confidence_threshold": getattr(config, "ocr_confidence_threshold", None),
                "audio_enabled": getattr(config, "enable_audio_analysis", None),
            },
            "extractors": {name: item.get("engine") for name, item in stage_items.items()},
        },
    }
