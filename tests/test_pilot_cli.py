import json
from pathlib import Path

from typer.testing import CliRunner

from shorts_intelligence.pilot.cli import pilot_app


def test_template_command_writes_one_placeholder_jsonl_record(tmp_path: Path) -> None:
    output = tmp_path / "private" / "manifest.jsonl"
    result = CliRunner().invoke(pilot_app, ["template", "--output", str(output)])
    assert result.exit_code == 0
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["record_id"] == "clip_0001"
    assert record["rights"]["model_training"] is False
    assert "REPLACE_WITH_PRIVATE" in record["rights"]["evidence_ref"]
