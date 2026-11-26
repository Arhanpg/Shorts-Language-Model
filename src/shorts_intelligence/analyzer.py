"""End-to-end single-video telemetry orchestration."""

from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from typing import Literal

import cv2

from shorts_intelligence.config import AnalyzerConfig
from shorts_intelligence.media.extract import extract_audio_wav
from shorts_intelligence.media.probe import MediaError, probe_video, validate_input
from shorts_intelligence.media.sampling import SamplingResult, sample_video
from shorts_intelligence.schemas import (
    AnalysisReport,
    AudioFeatures,
    HookWindow,
    MotionSummary,
    RightsDeclaration,
    StageStatus,
)
from shorts_intelligence.telemetry.asr import ASRError, transcribe_audio
from shorts_intelligence.telemetry.audio import analyze_audio
from shorts_intelligence.telemetry.ocr import OCRError, run_ocr

logger = logging.getLogger(__name__)


def _persist_frames(
    sampling: SamplingResult, output_path: Path, quality: int
) -> None:
    artifact_dir = output_path.parent / f"{output_path.stem}_frames"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    for index, item in enumerate(sampling.frames):
        name = (
            f"frame_{index:03d}_"
            f"{item.evidence.timestamp_seconds:08.2f}s.jpg"
        )
        destination = artifact_dir / name
        ok = cv2.imwrite(
            str(destination), item.image,
            [int(cv2.IMWRITE_JPEG_QUALITY), quality],
        )
        if not ok:
            raise MediaError(f"Could not write selected frame: {destination}")
        item.evidence.image_path = str(Path(artifact_dir.name) / name)


def _mean_hook_motion(sampling: SamplingResult, hook_end: float) -> float:
    values = [
        item.mean_flow_magnitude for item in sampling.motion_samples
        if item.timestamp_seconds <= hook_end
    ]
    return sum(values) / len(values) if values else 0.0


def analyze_video(
    input_path: Path,
    output_path: Path,
    rights_basis: Literal[
        "creator_owned", "creator_permission", "licensed_dataset", "approved_research"
    ] | None = None,
    rights_reference: str | None = None,
    training_permitted: bool = False,
    config: AnalyzerConfig | None = None,
) -> AnalysisReport:
    """Analyze one local file and atomically write an evidence-linked JSON report."""
    config = config or AnalyzerConfig()
    input_path = validate_input(input_path, config)
    metadata = probe_video(input_path, config)
    output_path = output_path.expanduser().resolve()
    if output_path == input_path:
        raise MediaError("The report destination cannot overwrite the source video.")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    stages: dict[str, StageStatus] = {
        "media_validation": StageStatus(status="complete", engine="ffprobe"),
        "frame_sampling": StageStatus(status="complete", engine="opencv"),
        "asr": StageStatus(status="skipped", detail="Disabled by configuration."),
        "ocr": StageStatus(status="skipped", detail="Disabled by configuration."),
        "audio_features": StageStatus(status="skipped", detail="Disabled by configuration."),
    }

    try:
        sampling = sample_video(input_path, metadata.duration_seconds, config)
    except ImportError as exc:
        raise MediaError(
            "OpenCV is required. Install the project base dependencies."
        ) from exc
    if not sampling.frames:
        warnings.append(
            "No frames were returned by OpenCV; check codec support and file integrity."
        )
        stages["frame_sampling"] = StageStatus(
            status="failed", engine="opencv", detail=warnings[-1]
        )

    transcript_segments = []
    ocr_spans = []
    audio_features = AudioFeatures(warning="No audio stream was detected.")

    with tempfile.TemporaryDirectory(prefix="shortslm_phase1_") as temp_dir:
        audio_path = Path(temp_dir) / "audio_16k_mono.wav"
        extracted_audio: Path | None = None
        if metadata.audio_present:
            try:
                extracted_audio = extract_audio_wav(input_path, audio_path)
            except MediaError as exc:
                warnings.append(str(exc))
                stages["audio_features"] = StageStatus(
                    status="failed", engine="ffmpeg", detail=str(exc)
                )
                stages["asr"] = StageStatus(
                    status="skipped", engine="ffmpeg",
                    detail="Audio extraction failed; ASR was not attempted.",
                )
        if (
            metadata.audio_present
            and extracted_audio is None
            and stages["audio_features"].status == "skipped"
        ):
                stages["audio_features"] = StageStatus(
                    status="skipped", engine="ffmpeg",
                    detail="No usable audio stream was extracted.",
                )

        if extracted_audio and config.enable_audio_analysis:
            audio_features = analyze_audio(extracted_audio)
            stages["audio_features"] = StageStatus(
                status="complete" if audio_features.analyzed else "partial",
                engine=audio_features.method or "librosa",
                detail=audio_features.warning,
            )
            if audio_features.warning:
                warnings.append(audio_features.warning)
        elif not metadata.audio_present:
            stages["audio_features"] = StageStatus(
                status="skipped", detail="No audio stream in source."
            )
        elif not config.enable_audio_analysis:
            stages["audio_features"] = StageStatus(
                status="skipped", detail="Disabled by configuration."
            )

        if extracted_audio and config.enable_asr:
            asr_started = time.monotonic()
            logger.info(
                "ASR stage started | file=%s | model=%s | requested_device=%s | timeout=%.0fs",
                input_path.name,
                config.asr_model,
                config.asr_device,
                config.asr_timeout_seconds,
            )
            try:
                transcript_segments, asr_engine, detected_language = transcribe_audio(
                    extracted_audio,
                    model_name=config.asr_model,
                    language=config.language,
                    device=config.asr_device,
                    compute_type=config.asr_compute_type,
                    timeout_seconds=config.asr_timeout_seconds,
                )
                logger.info(
                    "ASR stage completed | file=%s | engine=%s | segments=%d | elapsed=%.1fs",
                    input_path.name,
                    asr_engine,
                    len(transcript_segments),
                    time.monotonic() - asr_started,
                )
                stages["asr"] = StageStatus(
                    status="complete" if transcript_segments else "partial",
                    engine=asr_engine,
                    detail=(
                        f"Detected language: {detected_language or 'unknown'}; "
                        f"{len(transcript_segments)} segments."
                    ),
                )
                if not transcript_segments:
                    warnings.append(
                        "ASR completed but returned no speech segments; "
                        "this may be a music-only or silent clip."
                    )
            except ASRError as exc:
                logger.warning(
                    "ASR stage did not complete | file=%s | elapsed=%.1fs | error=%s",
                    input_path.name,
                    time.monotonic() - asr_started,
                    exc,
                )
                stages["asr"] = StageStatus(
                    status="failed", engine="faster-whisper/vidtrace",
                    detail=str(exc),
                )
                warnings.append(str(exc))
        elif not metadata.audio_present:
            stages["asr"] = StageStatus(
                status="skipped", detail="No audio stream in source."
            )
        elif extracted_audio is None:
            stages["asr"] = StageStatus(
                status="skipped", detail="No usable audio stream was extracted."
            )
        elif not config.enable_asr:
            stages["asr"] = StageStatus(
                status="skipped", detail="Disabled by configuration."
            )

        if config.enable_ocr and sampling.frames:
            ocr_started = time.monotonic()
            frames = [
                (item.evidence, item.image) for item in sampling.frames
            ]
            try:
                logger.info(
                    "OCR stage started | file=%s | frames=%d | requested_device=%s",
                    input_path.name,
                    min(len(frames), config.max_ocr_frames),
                    config.asr_device,
                )
                ocr_spans, ocr_engine = run_ocr(
                    frames,
                    max_frames=config.max_ocr_frames,
                    prefer_gpu=config.asr_device in {"cuda", "auto"},
                )
                logger.info(
                    "OCR stage completed | file=%s | engine=%s | spans=%d | elapsed=%.1fs",
                    input_path.name,
                    ocr_engine,
                    len(ocr_spans),
                    time.monotonic() - ocr_started,
                )
                stages["ocr"] = StageStatus(
                    status="complete" if ocr_spans else "partial",
                    engine=ocr_engine,
                    detail=(
                        f"{len(ocr_spans)} text spans from up to "
                        f"{min(len(frames), config.max_ocr_frames)} frames."
                    ),
                )
                if not ocr_spans:
                    warnings.append(
                        "OCR ran but found no text above its detector threshold."
                    )
            except OCRError as exc:
                logger.warning(
                    "OCR stage did not complete | file=%s | elapsed=%.1fs | error=%s",
                    input_path.name,
                    time.monotonic() - ocr_started,
                    exc,
                )
                stages["ocr"] = StageStatus(
                    status="failed", engine="paddleocr/vidtrace", detail=str(exc)
                )
                warnings.append(f"OCR failed: {exc}")
            except Exception as exc:
                # OCR is an optional analysis stage. An unexpected PaddleOCR/PaddleX
                # initialization or inference error must not discard all other features.
                logger.exception(
                    "OCR stage crashed | file=%s | elapsed=%.1fs",
                    input_path.name,
                    time.monotonic() - ocr_started,
                )
                detail = f"{type(exc).__name__}: {exc}"
                stages["ocr"] = StageStatus(
                    status="failed", engine="paddleocr", detail=detail
                )
                warnings.append(f"OCR failed unexpectedly: {detail}")
        elif not config.enable_ocr:
            stages["ocr"] = StageStatus(
                status="skipped", detail="Disabled by configuration."
            )

    if config.keep_artifacts and sampling.frames:
        _persist_frames(sampling, output_path, config.jpeg_quality)

    hook_end = min(metadata.duration_seconds, config.hook_window_seconds)
    hook_cut_count = sum(
        item.timestamp_seconds <= hook_end for item in sampling.cuts
    )
    report = AnalysisReport(
        rights=(
            RightsDeclaration(
                basis=rights_basis,
                reference=rights_reference,
                media_analysis_permitted=True,
                model_training_permitted=training_permitted,
            )
            if rights_basis is not None else None
        ),
        video=metadata,
        hook_window=HookWindow(
            end_seconds=hook_end,
            frame_count=sampling.hook_frame_count,
            cut_candidate_count=hook_cut_count,
            mean_motion_score=_mean_hook_motion(sampling, hook_end),
        ),
        frame_evidence=[item.evidence for item in sampling.frames],
        cut_candidates=sampling.cuts,
        motion=MotionSummary(
            sample_count=len(sampling.motion_samples),
            mean_flow_magnitude=sampling.mean_motion,
            p95_flow_magnitude=sampling.p95_motion,
            peak_timestamp_seconds=sampling.peak_timestamp,
            samples=sampling.motion_samples,
        ),
        transcript_segments=transcript_segments,
        ocr_spans=ocr_spans,
        audio=audio_features,
        stages=stages,
        warnings=warnings,
    )

    serialized = report.model_dump_json(indent=2)
    temporary_output = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_output.write_text(serialized + "\n", encoding="utf-8")
    temporary_output.replace(output_path)
    return report
