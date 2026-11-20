import pytest
from pathlib import Path

from shorts_intelligence.config import AnalyzerConfig
from shorts_intelligence.media.probe import MediaError, _parse_rate, validate_input


def test_parse_fractional_frame_rate() -> None:
    assert _parse_rate("30000/1001") == pytest.approx(29.97003, rel=1e-5)


def test_parse_invalid_frame_rate() -> None:
    assert _parse_rate("0/0") == 0.0
    assert _parse_rate(None) == 0.0


def test_validate_rejects_directory(tmp_path: Path) -> None:
    with pytest.raises(MediaError, match="single local file"):
        validate_input(tmp_path, AnalyzerConfig())


def test_validate_rejects_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "archive.zip"
    path.write_bytes(b"not a video")
    with pytest.raises(MediaError, match="Unsupported extension"):
        validate_input(path, AnalyzerConfig())


def test_validate_rejects_oversized_input(tmp_path: Path) -> None:
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"x" * (1024 * 1024 + 1))
    config = AnalyzerConfig(max_file_size_mb=1)
    with pytest.raises(MediaError, match="configured limit"):
        validate_input(path, config)
