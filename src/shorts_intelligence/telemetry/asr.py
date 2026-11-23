"""Timestamped multilingual ASR with optional reuse of Arhan's VidTrace engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shorts_intelligence.schemas import TranscriptSegment


class ASRError(RuntimeError):
    """Raised when an installed ASR engine fails."""


def _convert_segments(
    segments: list[Any], language: str | None
) -> list[TranscriptSegment]:
    converted: list[TranscriptSegment] = []
    for segment in segments:
        text = str(getattr(segment, "text", "")).strip()
        if not text:
            continue
        words: list[dict[str, object]] = []
        for word in (getattr(segment, "words", None) or []):
            words.append({
                "start": float(word.start) if getattr(word, "start", None) is not None else None,
                "end": float(word.end) if getattr(word, "end", None) is not None else None,
                "word": str(getattr(word, "word", "")),
                "probability": (
                    float(word.probability)
                    if getattr(word, "probability", None) is not None else None
                ),
            })
        converted.append(TranscriptSegment(
            start_seconds=max(0.0, float(segment.start)),
            end_seconds=max(0.0, float(segment.end)),
            text=text,
            language=language,
            confidence=None,
            words=words,
        ))
    return converted


def transcribe_audio(
    audio_path: Path,
    model_name: str = "small",
    language: str | None = None,
    device: str = "cpu",
    compute_type: str = "int8",
) -> tuple[list[TranscriptSegment], str, str | None]:
    """Run ASR using VidTrace when available, otherwise faster-whisper directly."""
    try:
        from vidtrace.audio.transcription import WhisperTranscriber
        from vidtrace.models.config import VidTraceConfig

        config = VidTraceConfig(whisper_model=model_name, language=language)
        engine = WhisperTranscriber(
            config,
            prefer_gpu=device in {"cuda", "auto"},
            compute_type=compute_type,
        )
        try:
            raw, meta = engine.transcribe(audio_path)
        finally:
            close = getattr(engine, "close", None)
            if callable(close):
                close()
        detected_language = meta.get("language") or language
        actual_device = str(meta.get("device") or "unknown")
        actual_compute = str(meta.get("compute_type") or "unknown")
        engine_name = f"vidtrace-faster-whisper-{actual_device}-{actual_compute}"
        return (
            _convert_segments(raw, detected_language),
            engine_name,
            detected_language,
        )
    except ImportError:
        pass
    except Exception as exc:
        raise ASRError(
            f"VidTrace ASR adapter failed: {type(exc).__name__}: {exc}"
        ) from exc

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ASRError(
            "faster-whisper is not installed. Install the ShortsLM audio extra "
            "or install your existing VidTrace checkout with its whisper extra."
        ) from exc

    actual_device = "cuda" if device in {"cuda", "auto"} else "cpu"
    actual_compute = compute_type if actual_device == "cuda" else "int8"
    try:
        engine = WhisperModel(
            model_name, device=actual_device, compute_type=actual_compute
        )
        segments_iter, info = engine.transcribe(
            str(audio_path),
            language=language,
            task="transcribe",
            beam_size=3,
            vad_filter=True,
            word_timestamps=True,
            condition_on_previous_text=False,
        )
        raw = list(segments_iter)
    except Exception as exc:
        if actual_device == "cuda":
            try:
                engine = WhisperModel(
                    model_name, device="cpu", compute_type="int8"
                )
                segments_iter, info = engine.transcribe(
                    str(audio_path), language=language, task="transcribe",
                    beam_size=3, vad_filter=True, word_timestamps=True,
                    condition_on_previous_text=False,
                )
                raw = list(segments_iter)
                actual_device = "cpu-fallback"
            except Exception as fallback_exc:
                raise ASRError(
                    f"ASR failed on CUDA and CPU fallback: {fallback_exc}"
                ) from fallback_exc
        else:
            raise ASRError(
                f"ASR failed: {type(exc).__name__}: {exc}"
            ) from exc
    detected_language = getattr(info, "language", None) or language
    return (
        _convert_segments(raw, detected_language),
        f"faster-whisper-{actual_device}",
        detected_language,
    )
