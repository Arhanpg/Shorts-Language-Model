from __future__ import annotations

import inspect
import sys
from pathlib import Path
from types import ModuleType

from shorts_intelligence.config import AnalyzerConfig
from shorts_intelligence.telemetry.asr import transcribe_audio
from shorts_intelligence.telemetry.ocr import run_ocr


def test_analyzer_defaults_to_cuda_with_vram_friendly_precision():
    config = AnalyzerConfig()
    assert config.asr_device == "cuda"
    assert config.asr_compute_type == "int8_float16"


def test_ocr_prefers_gpu_by_default():
    assert inspect.signature(run_ocr).parameters["prefer_gpu"].default is True


def test_asr_passes_cuda_and_compute_type_to_vidtrace(monkeypatch, tmp_path: Path):
    captured = {}

    class FakeWhisperTranscriber:
        def __init__(self, config, *, prefer_gpu=True, compute_type=None):
            captured["prefer_gpu"] = prefer_gpu
            captured["compute_type"] = compute_type

        def transcribe(self, _audio_path):
            return [], {
                "language": "en",
                "device": "cuda",
                "compute_type": "int8_float16",
            }

        def close(self):
            captured["closed"] = True

    class FakeVidTraceConfig:
        def __init__(self, **kwargs):
            captured["config"] = kwargs

    modules = {
        "vidtrace": ModuleType("vidtrace"),
        "vidtrace.audio": ModuleType("vidtrace.audio"),
        "vidtrace.audio.transcription": ModuleType("vidtrace.audio.transcription"),
        "vidtrace.models": ModuleType("vidtrace.models"),
        "vidtrace.models.config": ModuleType("vidtrace.models.config"),
    }
    modules["vidtrace.audio.transcription"].WhisperTranscriber = FakeWhisperTranscriber
    modules["vidtrace.models.config"].VidTraceConfig = FakeVidTraceConfig
    modules["vidtrace"].__path__ = []
    modules["vidtrace.audio"].__path__ = []
    modules["vidtrace.models"].__path__ = []
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"test")

    segments, engine_name, language = transcribe_audio(
        audio_path,
        model_name="small",
        device="cuda",
        compute_type="int8_float16",
    )

    assert segments == []
    assert language == "en"
    assert engine_name == "vidtrace-faster-whisper-cuda-int8_float16"
    assert captured["prefer_gpu"] is True
    assert captured["compute_type"] == "int8_float16"
    assert captured["config"] == {"whisper_model": "small", "language": None}
    assert captured["closed"] is True
