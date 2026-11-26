"""Timestamped multilingual ASR with zero-segment retry and decoding diagnostics."""
from __future__ import annotations

import contextlib
import logging
import multiprocessing
import time
import unicodedata
from pathlib import Path
from typing import Any

from shorts_intelligence.schemas import TranscriptSegment

logger = logging.getLogger(__name__)


class ASRError(RuntimeError):
    """Raised when an installed ASR engine fails."""


def _script_for_text(text: str) -> str:
    """Unicode script label only; this is not a language classifier."""
    ranges = {
        "Latn": ((0x0041, 0x024F), (0x1E00, 0x1EFF)),
        "Deva": ((0x0900, 0x097F),), "Beng": ((0x0980, 0x09FF),),
        "Guru": ((0x0A00, 0x0A7F),), "Gujr": ((0x0A80, 0x0AFF),),
        "Orya": ((0x0B00, 0x0B7F),), "Taml": ((0x0B80, 0x0BFF),),
        "Telu": ((0x0C00, 0x0C7F),), "Knda": ((0x0C80, 0x0CFF),),
        "Mlym": ((0x0D00, 0x0D7F),), "Thai": ((0x0E00, 0x0E7F),),
        "Arab": ((0x0600, 0x06FF), (0x0750, 0x077F)),
        "Hebr": ((0x0590, 0x05FF),), "Cyrl": ((0x0400, 0x052F),),
        "Grek": ((0x0370, 0x03FF),), "Hang": ((0xAC00, 0xD7AF), (0x1100, 0x11FF)),
        "Hani": ((0x4E00, 0x9FFF),),
    }
    counts: dict[str, int] = {}
    for char in text:
        codepoint = ord(char)
        for label, blocks in ranges.items():
            if any(start <= codepoint <= end for start, end in blocks):
                counts[label] = counts.get(label, 0) + 1
                break
    if not counts:
        return "Zyyy"
    return "Mixed" if len(counts) > 1 else max(counts, key=counts.get)


def _normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def _convert_segments(
    segments: list[Any],
    language: str | None,
    language_probability: float | None = None,
    vad_retry_used: bool = False,
) -> list[TranscriptSegment]:
    converted: list[TranscriptSegment] = []
    for segment in segments:
        text = str(getattr(segment, "text", "")).strip()
        if not text:
            continue
        normalized = _normalize_text(text)
        words: list[dict[str, object]] = []
        for word in (getattr(segment, "words", None) or []):
            word_text = str(getattr(word, "word", ""))
            words.append({
                "start": float(word.start) if getattr(word, "start", None) is not None else None,
                "end": float(word.end) if getattr(word, "end", None) is not None else None,
                "word": word_text,
                "script": _script_for_text(word_text),
                "probability": float(word.probability) if getattr(word, "probability", None) is not None else None,
            })
        quality = getattr(segment, "quality", None)
        quality = quality if isinstance(quality, dict) else {}
        no_speech = getattr(segment, "no_speech_prob", None)
        if no_speech is None:
            no_speech = quality.get("no_speech_prob")
        avg_logprob = getattr(segment, "avg_logprob", None)
        if avg_logprob is None:
            avg_logprob = quality.get("avg_logprob")
        compression = getattr(segment, "compression_ratio", None)
        if compression is None:
            compression = quality.get("compression_ratio")
        temperature = getattr(segment, "temperature", None)
        if temperature is None:
            temperature = quality.get("temperature")
        flags: list[str] = []
        # Review heuristics only; thresholds are not calibrated correctness scores.
        if no_speech is not None and float(no_speech) >= 0.6:
            flags.append("high_no_speech_probability")
        if avg_logprob is not None and float(avg_logprob) < -1.0:
            flags.append("low_average_log_probability")
        if compression is not None and float(compression) > 2.4:
            flags.append("high_compression_ratio")
        converted.append(TranscriptSegment(
            start_seconds=max(0.0, float(segment.start)),
            end_seconds=max(0.0, float(segment.end)),
            text=text,
            text_normalized=normalized,
            script=_script_for_text(normalized),
            language=language,
            language_probability=language_probability,
            no_speech_probability=float(no_speech) if no_speech is not None else None,
            average_log_probability=float(avg_logprob) if avg_logprob is not None else None,
            compression_ratio=float(compression) if compression is not None else None,
            temperature=float(temperature) if temperature is not None else None,
            vad_retry_used=vad_retry_used,
            quality_status="needs_review" if flags else "unreviewed",
            quality_flags=flags,
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
    """Use VidTrace if it yields segments; otherwise use direct faster-whisper."""
    try:
        from vidtrace.audio.transcription import WhisperTranscriber
        from vidtrace.models.config import VidTraceConfig
        config = VidTraceConfig(whisper_model=model_name, language=language)
        adapter = WhisperTranscriber(
            config, prefer_gpu=device in {"cuda", "auto"}, compute_type=compute_type
        )
        try:
            raw, meta = adapter.transcribe(audio_path)
        finally:
            close = getattr(adapter, "close", None)
            if callable(close):
                close()
        detected = meta.get("language") or language
        converted = _convert_segments(raw, detected, meta.get("language_probability"))
        if converted:
            return converted, (
                f"vidtrace-faster-whisper-{meta.get('device', 'unknown')}-"
                f"{meta.get('compute_type', 'unknown')}"
            ), detected
        logger.warning("VidTrace returned zero segments; trying direct faster-whisper.")
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("VidTrace ASR fallback: %s: %s", type(exc).__name__, exc)

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ASRError("faster-whisper is not installed. Install the ShortsLM audio extra.") from exc

    actual_device = "cuda" if device in {"cuda", "auto"} else "cpu"
    actual_compute = compute_type if actual_device == "cuda" else "int8"
    try:
        engine = WhisperModel(model_name, device=actual_device, compute_type=actual_compute)
    except Exception as exc:
        if actual_device != "cuda":
            raise ASRError(f"ASR initialization failed: {type(exc).__name__}: {exc}") from exc
        logger.warning("CUDA model initialization failed; falling back to CPU: %s", exc)
        actual_device, actual_compute = "cpu-fallback", "int8"
        try:
            engine = WhisperModel(model_name, device="cpu", compute_type="int8")
        except Exception as fallback_exc:
            raise ASRError(f"ASR initialization failed on CUDA and CPU: {fallback_exc}") from fallback_exc

    def run_pass(vad_filter: bool):
        iterator, info = engine.transcribe(
            str(audio_path), language=language, task="transcribe", beam_size=3,
            vad_filter=vad_filter, word_timestamps=True,
            condition_on_previous_text=False, temperature=0.0,
        )
        return list(iterator), info

    try:
        raw, info = run_pass(True)
    except Exception as exc:
        if actual_device != "cuda":
            raise ASRError(f"ASR failed: {type(exc).__name__}: {exc}") from exc
        logger.warning("CUDA inference failed; retrying with CPU: %s", exc)
        try:
            engine = WhisperModel(model_name, device="cpu", compute_type="int8")
            actual_device, actual_compute = "cpu-fallback", "int8"
            raw, info = run_pass(True)
        except Exception as fallback_exc:
            raise ASRError(f"ASR failed on CUDA and CPU fallback: {fallback_exc}") from fallback_exc

    retry_used = False
    if not raw:
        retry_used = True
        logger.warning("Zero ASR segments with VAD; retrying once with vad_filter=False.")
        try:
            raw, info = run_pass(False)
        except Exception as exc:
            raise ASRError(f"ASR VAD-disabled retry failed: {type(exc).__name__}: {exc}") from exc

    detected = getattr(info, "language", None) or language
    language_probability = getattr(info, "language_probability", None)
    converted = _convert_segments(raw, detected, language_probability, retry_used)
    suffix = "-vad-disabled-retry" if retry_used else ""
    if retry_used and not converted:
        suffix += "-empty"
    return converted, f"faster-whisper-{actual_device}{suffix}", detected


def _transcription_worker(connection: Any, audio_path: str, model_name: str,
                          language: str | None, device: str, compute_type: str) -> None:
    """Run ASR outside the parent process so a stuck native call can be stopped."""
    try:
        segments, engine_name, detected_language = _transcribe_audio_inline(
            Path(audio_path), model_name=model_name, language=language,
            device=device, compute_type=compute_type,
        )
        connection.send({
            "ok": True, "segments": [segment.model_dump(mode="json") for segment in segments],
            "engine": engine_name, "language": detected_language,
        })
    except BaseException as exc:
        with contextlib.suppress(BrokenPipeError, EOFError, OSError):
            connection.send({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        connection.close()


def _stop_transcription_worker(process: Any) -> None:
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
    audio_path: Path, model_name: str = "small", language: str | None = None,
    device: str = "cpu", compute_type: str = "int8",
    timeout_seconds: float = 300.0, heartbeat_seconds: float = 15.0,
) -> tuple[list[TranscriptSegment], str, str | None]:
    """Run bounded ASR; timeout=0 keeps an in-process path for tests/embedded callers."""
    if timeout_seconds <= 0:
        return _transcribe_audio_inline(
            audio_path, model_name=model_name, language=language,
            device=device, compute_type=compute_type,
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
    logger.info("ASR worker starting | file=%s | model=%s | requested_device=%s | timeout=%.0fs",
                audio_path.name, model_name, device, timeout_seconds)
    try:
        try:
            process.start()
        except Exception as exc:
            raise ASRError(f"Could not start isolated ASR worker: {type(exc).__name__}: {exc}") from exc
        sender.close()
        while result is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                elapsed = time.monotonic() - started
                _stop_transcription_worker(process)
                raise ASRError(
                    f"ASR timed out after {elapsed:.1f}s; worker terminated. "
                    "Retry with --device cpu or a smaller Whisper model."
                )
            if receiver.poll(min(0.5, remaining)):
                try:
                    result = receiver.recv()
                except (EOFError, OSError) as exc:
                    raise ASRError(f"ASR worker exited without result: {exc}") from exc
                break
            if not process.is_alive():
                if receiver.poll(0.1):
                    result = receiver.recv()
                    break
                raise ASRError(f"ASR worker exited without a result (exit code {process.exitcode}).")
            now = time.monotonic()
            if heartbeat_seconds > 0 and now >= next_heartbeat:
                logger.info("ASR still running | file=%s | elapsed=%.0fs | requested_device=%s",
                            audio_path.name, now - started, device)
                next_heartbeat = now + heartbeat_seconds
        process.join(timeout=3)
        if process.is_alive():
            _stop_transcription_worker(process)
        if not isinstance(result, dict) or not result.get("ok"):
            detail = result.get("error", "unknown worker error") if isinstance(result, dict) else "invalid worker response"
            raise ASRError(f"ASR worker failed: {detail}")
        segments = [TranscriptSegment.model_validate(item) for item in result.get("segments", [])]
        elapsed = time.monotonic() - started
        engine_name = str(result.get("engine") or "unknown")
        detected_language = result.get("language")
        logger.info("ASR worker completed | file=%s | segments=%d | engine=%s | elapsed=%.1fs",
                    audio_path.name, len(segments), engine_name, elapsed)
        return segments, engine_name, detected_language
    except BaseException:
        _stop_transcription_worker(process)
        raise
    finally:
        receiver.close()
        with contextlib.suppress(OSError):
            sender.close()
        try:
            if not process.is_alive():
                process.close()
        except (AssertionError, OSError, ValueError):
            pass
