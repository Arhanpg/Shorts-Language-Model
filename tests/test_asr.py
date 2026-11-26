from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

from shorts_intelligence.telemetry.asr import _transcribe_audio_inline


class FakeSegment:
    start = 0.25
    end = 1.25
    text = "  नमस्ते hello  "
    words = []
    no_speech_prob = 0.03
    avg_logprob = -0.2
    compression_ratio = 1.1
    temperature = 0.0


def test_zero_segments_retries_without_vad(monkeypatch, tmp_path):
    calls = []

    class FakeWhisperModel:
        def __init__(self, model_name, *, device, compute_type):
            assert model_name == "small"
            assert device == "cpu"
            assert compute_type == "int8"

        def transcribe(self, _path, **kwargs):
            calls.append(kwargs["vad_filter"])
            segments = [] if kwargs["vad_filter"] else [FakeSegment()]
            return iter(segments), SimpleNamespace(language="hi", language_probability=0.87)

    fake_fw = ModuleType("faster_whisper")
    fake_fw.WhisperModel = FakeWhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_fw)
    monkeypatch.setitem(sys.modules, "vidtrace", None)
    path = tmp_path / "audio.wav"
    path.write_bytes(b"audio")

    segments, engine, language = _transcribe_audio_inline(path, device="cpu")

    assert calls == [True, False]
    assert len(segments) == 1
    assert segments[0].text_normalized == "नमस्ते hello"
    assert segments[0].script == "Mixed"
    assert segments[0].language_probability == 0.87
    assert segments[0].vad_retry_used is True
    assert language == "hi"
    assert engine.endswith("-vad-disabled-retry")


def test_zero_segments_after_retry_are_not_labeled_silence(monkeypatch, tmp_path):
    calls = []

    class FakeWhisperModel:
        def __init__(self, _model_name, *, device, compute_type):
            pass

        def transcribe(self, _path, **kwargs):
            calls.append(kwargs["vad_filter"])
            return iter([]), SimpleNamespace(language="en", language_probability=0.8)

    fake_fw = ModuleType("faster_whisper")
    fake_fw.WhisperModel = FakeWhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_fw)
    monkeypatch.setitem(sys.modules, "vidtrace", None)
    path = tmp_path / "music.wav"
    path.write_bytes(b"audio")

    segments, engine, _language = _transcribe_audio_inline(path, device="cpu")

    assert calls == [True, False]
    assert segments == []
    assert engine.endswith("-vad-disabled-retry-empty")
