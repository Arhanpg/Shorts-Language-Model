from typer.testing import CliRunner

from shorts_intelligence.cli import app


def test_version_command() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.2.0" in result.stdout


def test_doctor_json_is_valid_json() -> None:
    import json

    result = CliRunner().invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "ffmpeg" in payload["checks"]
