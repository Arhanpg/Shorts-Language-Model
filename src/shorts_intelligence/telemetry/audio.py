"""Acoustic features for rhythm, energy and silence; no music identification."""

from __future__ import annotations

from pathlib import Path

from shorts_intelligence.schemas import AudioFeatures


def analyze_audio(audio_path: Path) -> AudioFeatures:
    try:
        import librosa
        import numpy as np
    except ImportError:
        return AudioFeatures(
            warning="librosa is not installed; install the ShortsLM audio extra."
        )

    try:
        signal, sample_rate = librosa.load(
            str(audio_path), sr=22050, mono=True
        )
        if signal.size == 0:
            return AudioFeatures(warning="The extracted audio stream is empty.")
        frame_length = 2048
        hop_length = 512
        rms = librosa.feature.rms(
            y=signal, frame_length=frame_length, hop_length=hop_length
        )[0]
        silence_ratio = float(np.mean(rms < 0.008)) if rms.size else 0.0
        onset_env = librosa.onset.onset_strength(
            y=signal, sr=sample_rate, hop_length=hop_length
        )
        onset_frames = librosa.onset.onset_detect(
            onset_envelope=onset_env, sr=sample_rate,
            hop_length=hop_length, backtrack=False, units="frames",
        )
        onset_times = librosa.frames_to_time(
            onset_frames, sr=sample_rate, hop_length=hop_length
        )
        tempo, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_env, sr=sample_rate, hop_length=hop_length
        )
        tempo_value = (
            float(np.asarray(tempo).reshape(-1)[0])
            if np.asarray(tempo).size else 0.0
        )
        beat_times = librosa.frames_to_time(
            beat_frames, sr=sample_rate, hop_length=hop_length
        )
        return AudioFeatures(
            analyzed=True,
            duration_seconds=float(len(signal) / sample_rate),
            sample_rate=sample_rate,
            rms_mean=float(np.mean(rms)) if rms.size else 0.0,
            silence_ratio=min(1.0, max(0.0, silence_ratio)),
            estimated_tempo_bpm=max(0.0, tempo_value),
            beat_times_seconds=[float(value) for value in beat_times[:1000]],
            onset_times_seconds=[float(value) for value in onset_times[:2000]],
            method=f"librosa-{librosa.__version__}",
        )
    except Exception as exc:
        return AudioFeatures(
            warning=f"Audio analysis failed: {type(exc).__name__}: {exc}"
        )
