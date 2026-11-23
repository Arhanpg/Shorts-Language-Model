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
    modules["vidtrace"].__path__ = []
    modules["vidtrace.audio"].__path__ = []
    modules["vidtrace.models"].__path__ = []
    modules["vidtrace.audio.transcription"].WhisperTranscriber = FakeWhisperTranscriber
    modules["vidtrace.models.config"].VidTraceConfig = FakeVidTraceConfig
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"test")

    segments, engine_name, language = transcribe_audio(
        audio_path,
        model_name="small",
        device="cuda",
        compute_type="int8_float16",
        timeout_seconds=0,
    )

    assert segments == []
    assert language == "en"
    assert engine_name == "vidtrace-faster-whisper-cuda-int8_float16"
    assert captured["prefer_gpu"] is True
    assert captured["compute_type"] == "int8_float16"
    assert captured["config"] == {"whisper_model": "small", "language": None}
    assert captured["closed"] is True


def test_asr_watchdog_terminates_a_stalled_worker(monkeypatch, tmp_path):
    import time

    import pytest

    import shorts_intelligence.telemetry.asr as asr

    class FakeConnection:
        def __init__(self):
            self.closed = False

        def poll(self, timeout=0):
            time.sleep(timeout)
            return False

        def recv(self):
            raise AssertionError("A timed-out worker must not return a result.")

        def close(self):
            self.closed = True

        def send(self, _payload):
            pass

    class FakeProcess:
        def __init__(self):
            self.started = False
            self.terminated = False
            self.killed = False
            self.closed = False
            self.exitcode = None

        def start(self):
            self.started = True

        def is_alive(self):
            return self.started and not self.terminated and not self.killed

        def join(self, timeout=None):
            pass

        def terminate(self):
            self.terminated = True
            self.exitcode = -15

        def kill(self):
            self.killed = True
            self.exitcode = -9

        def close(self):
            self.closed = True

    class FakeContext:
        def __init__(self):
            self.receiver = FakeConnection()
            self.sender = FakeConnection()
            self.process = FakeProcess()

        def Pipe(self, duplex=False):
            assert duplex is False
            return self.receiver, self.sender

        def Process(self, **kwargs):
            assert kwargs["name"].startswith("shortslm-asr-")
            return self.process

    context = FakeContext()
    monkeypatch.setattr(asr.multiprocessing, "get_context", lambda _method: context)

    audio_path = tmp_path / "stalled.wav"
    audio_path.write_bytes(b"audio")

    with pytest.raises(asr.ASRError, match="ASR timed out"):
        asr.transcribe_audio(
            audio_path,
            device="cuda",
            timeout_seconds=0.02,
            heartbeat_seconds=0,
        )

    assert context.process.started is True
    assert context.process.terminated is True
    assert context.receiver.closed is True
    assert context.sender.closed is True
