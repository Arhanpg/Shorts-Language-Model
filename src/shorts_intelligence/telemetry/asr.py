"""Timestamped multilingual ASR with optional reuse of Arhan's VidTrace engine."""

from __future__ import annotations

import logging
import multiprocessing
import time
from pathlib import Path
from typing import Any

from shorts_intelligence.schemas import TranscriptSegment

logger = logging.getLogger(__name__)


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


def _transcribe_audio_inline(
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


def _transcription_worker(
    connection: Any,
    audio_path: str,
    model_name: str,
    language: str | None,
    device: str,
    compute_type: str,
) -> None:
    """Run ASR outside the parent process so a stuck CUDA call can be stopped."""
    try:
        segments, engine_name, detected_language = _transcribe_audio_inline(
            Path(audio_path),
            model_name=model_name,
            language=language,
            device=device,
            compute_type=compute_type,
        )
        connection.send({
            "ok": True,
            "segments": [segment.model_dump(mode="json") for segment in segments],
            "engine": engine_name,
            "language": detected_language,
        })
    except BaseException as exc:
        try:
            connection.send({
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            })
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        connection.close()


def _stop_transcription_worker(process: Any) -> None:
    """Terminate a worker even if a native CUDA/CPU inference call is stuck."""
    try:
        if process.is_alive():
            process.terminate()
            process.join(timeout=3)
        if process.is_alive():
            process.kill()
            process.join(timeout=3)
    except (AssertionError, OSError, ValueError):
        pass


def transcribe_audio(
    audio_path: Path,
    model_name: str = "small",
    language: str | None = None,
    device: str = "cpu",
    compute_type: str = "int8",
    timeout_seconds: float = 300.0,
    heartbeat_seconds: float = 15.0,
) -> tuple[list[TranscriptSegment], str, str | None]:
    """Run bounded ASR; timeout=0 keeps an in-process path for embedded callers/tests."""
    if timeout_seconds <= 0:
        return _transcribe_audio_inline(
            audio_path,
            model_name=model_name,
            language=language,
            device=device,
            compute_type=compute_type,
        )

    audio_path = Path(audio_path).expanduser().resolve(strict=True)
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_transcription_worker,
        args=(sender, str(audio_path), model_name, language, device, compute_type),
        name=f"shortslm-asr-{audio_path.stem[:32]}",
    )
    started = time.monotonic()
    deadline = started + float(timeout_seconds)
    next_heartbeat = started + max(1.0, float(heartbeat_seconds))
    result: dict[str, Any] | None = None

    logger.info(
        "ASR worker starting | file=%s | model=%s | requested_device=%s | timeout=%.0fs",
        audio_path.name,
        model_name,
        device,
        timeout_seconds,
    )
    try:
        try:
            process.start()
        except Exception as exc:
            raise ASRError(
                f"Could not start isolated ASR worker: {type(exc).__name__}: {exc}"
            ) from exc
        sender.close()

        while result is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                elapsed = time.monotonic() - started
                _stop_transcription_worker(process)
                raise ASRError(
                    f"ASR timed out after {elapsed:.1f}s; the worker was terminated. "
                    "Retry with --device cpu or a smaller Whisper model."
                )

            if receiver.poll(min(0.5, remaining)):
                try:
                    result = receiver.recv()
                except (EOFError, OSError) as exc:
                    raise ASRError(
                        f"ASR worker exited without a result: {type(exc).__name__}: {exc}"
                    ) from exc
                break

            if not process.is_alive():
                if receiver.poll(0.1):
                    result = receiver.recv()
                    break
                raise ASRError(
                    f"ASR worker exited without a result (exit code {process.exitcode})."
                )

            now = time.monotonic()
            if heartbeat_seconds > 0 and now >= next_heartbeat:
                logger.info(
                    "ASR still running | file=%s | elapsed=%.0fs | requested_device=%s",
                    audio_path.name,
                    now - started,
                    device,
                )
                next_heartbeat = now + heartbeat_seconds

        process.join(timeout=3)
        if process.is_alive():
            _stop_transcription_worker(process)

        if not isinstance(result, dict) or not result.get("ok"):
            detail = result.get("error", "unknown worker error") if isinstance(result, dict) else "invalid worker response"
            raise ASRError(f"ASR worker failed: {detail}")

        segments = [
            TranscriptSegment.model_validate(item)
            for item in result.get("segments", [])
        ]
        elapsed = time.monotonic() - started
        engine_name = str(result.get("engine") or "unknown")
        detected_language = result.get("language")
        logger.info(
            "ASR worker completed | file=%s | segments=%d | engine=%s | elapsed=%.1fs",
            audio_path.name,
            len(segments),
            engine_name,
            elapsed,
        )
        return segments, engine_name, detected_language
    except BaseException:
        _stop_transcription_worker(process)
        raise
    finally:
        receiver.close()
        try:
            sender.close()
        except OSError:
            pass
        try:
            if not process.is_alive():
                process.close()
        except (AssertionError, OSError, ValueError):
            pass
