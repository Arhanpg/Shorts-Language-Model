import json
from pathlib import Path

from shorts_intelligence.pilot.reporting import build_pilot_report


def test_report_marks_unprocessed_selection_as_awaiting_validation(tmp_path: Path) -> None:
    pilot = tmp_path / "pilot"
    pilot.mkdir()
    (pilot / "selection_report.json").write_text(
        json.dumps({
            "target": 300,
            "selected": 15,
            "candidate_pool": 25,
            "seed": 42,
            "unique_creator_groups_in_selection": 10,
            "unscored_creator_relative_records": 15,
            "coverage": {},
        }),
        encoding="utf-8",
    )
    output = pilot / "final.json"
    report = build_pilot_report(pilot, output)
    assert report["phase_2_exit_status"] == "awaiting_local_300_video_validation"
    assert report["selected_records"] == 15
    assert json.loads(output.read_text(encoding="utf-8"))["pilot_target"] == 300
