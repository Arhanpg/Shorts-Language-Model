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



def test_vidtrace_nested_quality_dictionary_is_preserved():
    from types import SimpleNamespace

    from shorts_intelligence.telemetry.asr import _convert_segments

    segment = SimpleNamespace(
        start=0.0,
        end=0.8,
        text="hello",
        words=[],
        quality={
            "no_speech_prob": 0.04,
            "avg_logprob": -0.3,
            "compression_ratio": 1.2,
            "temperature": 0.0,
        },
    )
    [converted] = _convert_segments([segment], "en", language_probability=0.93)
    assert converted.no_speech_probability == 0.04
    assert converted.average_log_probability == -0.3
    assert converted.compression_ratio == 1.2
    assert converted.temperature == 0.0



def test_low_language_probability_is_flagged_for_qa():
    from types import SimpleNamespace

    from shorts_intelligence.telemetry.asr import _convert_segments

    segment = SimpleNamespace(
        start=0.0,
        end=0.9,
        text="e que eu possa ver",
        words=[],
        no_speech_prob=0.2,
        avg_logprob=-0.4,
        compression_ratio=1.0,
        temperature=0.0,
    )
    [converted] = _convert_segments(
        [segment], "pt", language_probability=0.46
    )
    assert converted.language == "pt"
    assert converted.language_probability == 0.46
    assert "low_language_probability" in converted.quality_flags
    assert converted.quality_status == "needs_review"


def test_mixed_script_segment_is_flagged_for_multilingual_review():
    from types import SimpleNamespace

    from shorts_intelligence.telemetry.asr import _convert_segments

    segment = SimpleNamespace(
        start=0.0,
        end=0.9,
        text="नमस्ते hello",
        words=[],
        no_speech_prob=0.1,
        avg_logprob=-0.2,
        compression_ratio=1.0,
        temperature=0.0,
    )
    [converted] = _convert_segments(
        [segment], "hi", language_probability=0.9
    )
    assert converted.script == "Mixed"
    assert "mixed_script_segment" in converted.quality_flags
