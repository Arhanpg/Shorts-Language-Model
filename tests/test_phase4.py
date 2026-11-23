import csv
import json
from pathlib import Path

from typer.testing import CliRunner

from shorts_intelligence.phase4 import _identity, _tag, _training_rights, phase4_app


def test_unicode_normalization():
    assert _identity({"profile_url": "https://instagram.com/Some.User/"}) == "some.user"
    assert _identity({"account_handle": "@new.creator"}) == "new.creator"
    channel_id = "UC" + "a" * 22
    assert _identity({"channel_id": channel_id}) == channel_id
    assert _tag({"hashtag": "#ಕನ್ನಡ"}) == "ಕನ್ನಡ"
    assert _tag({"hashtag": "two words"}) is None


def test_catalogue_materializes_all_csvs(tmp_path: Path):
    source = tmp_path / "catalogue"
    source.mkdir()
    (source / "youtube_channel_candidates.csv").write_text(
        "channel_id,title\nUC" + "a" * 22 + ",Channel A\n", encoding="utf-8")
    (source / "instagram_account_candidates.csv").write_text(
        "username,entity_type\nalpha,person\nbeta,org\n", encoding="utf-8")
    (source / "creators_ai_research_leads_v0.1.csv").write_text(
        "platform,handle,creator_name\nyoutube,flyingbeast320,Flying Beast\ninstagram,taneja.gaurav,Gaurav\n",
        encoding="utf-8")
    (source / "hashtags_master_candidates.csv").write_text(
        "hashtag,language,domain\n#kannada,kn,comedy\n#science,en,science\n", encoding="utf-8")
    out = tmp_path / "out"
    result = CliRunner().invoke(phase4_app, ["catalogue", "--catalogue-dir", str(source),
        "--output-dir", str(out), "--batch-size", "10"])
    assert result.exit_code == 0, result.output
    report = json.loads((out / "catalogue_report.json").read_text())
    assert report["unique_instagram_accounts"] == 4
    assert report["unique_youtube_channel_candidates"] == 2
    assert report["youtube_channel_id_seedable"] == 1
    assert report["unique_normalized_hashtags"] == 2
    assert (out / "batches/instagram_creators_0001.txt").exists()
    assert (out / "batches/youtube_channel_ids_0001.txt").exists()


def test_rights_scopes_are_separate():
    row = {"rights": {"evidence_ref": "contract-1", "media_analysis": True,
        "temporary_processing": True, "derived_artifact_retention": True,
        "model_training": True, "revoked": False}}
    assert _training_rights(row)
    row["rights"]["model_training"] = False
    assert not _training_rights(row)


def test_release_blocks_non_training_permission(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    row = {"record_id": "vid_001", "media_sha256": "a" * 64, "duration_seconds": 15,
        "rights": {"evidence_ref": "evidence", "media_analysis": True,
        "temporary_processing": True, "derived_artifact_retention": True,
        "model_training": False, "revoked": False}}
    manifest.write_text(json.dumps(row) + "\n", encoding="utf-8")
    annotations = tmp_path / "annotations.csv"
    annotations.write_text(
        "record_id,review_status,language_primary,content_domain,summary_grounded,hook_type\n"
        "vid_001,approved,kn,comedy,checked,unknown\n", encoding="utf-8")
    out = tmp_path / "release"
    result = CliRunner().invoke(phase4_app, ["release", "--manifest", str(manifest),
        "--annotations", str(annotations), "--output-dir", str(out)])
    assert result.exit_code != 0
    blockers = json.loads((out / "release_blockers.json").read_text())
    assert blockers["issues"][0]["issue"] == "rights_not_training_eligible"


def test_release_keeps_creator_group_together(tmp_path: Path):
    manifest = tmp_path / "selected.jsonl"
    rows = []
    for i, creator in enumerate(("same", "same", "other-a", "other-b", "other-c"), 1):
        rows.append({"record_id": f"vid_{i}", "media_sha256": f"{i:064x}",
            "duration_seconds": 12, "published_at": f"2026-01-0{i}T00:00:00+00:00",
            "creator_group": creator, "language": "kn", "topic": "comedy",
            "rights_reference_hash": "b" * 64, "media_analysis_permitted": True,
            "temporary_processing_permitted": True, "derived_artifact_retention_permitted": True,
            "model_training_permitted": True})
    manifest.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    annotations = tmp_path / "annotations.csv"
    with annotations.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["record_id", "review_status", "language_primary",
            "content_domain", "summary_grounded", "hook_type"])
        writer.writeheader()
        for row in rows:
            writer.writerow({"record_id": row["record_id"], "review_status": "approved",
                "language_primary": "kn", "content_domain": "comedy",
                "summary_grounded": "human checked", "hook_type": "unknown"})
    out = tmp_path / "release"
    result = CliRunner().invoke(phase4_app, ["release", "--manifest", str(manifest),
        "--annotations", str(annotations), "--output-dir", str(out), "--golden-fraction", "0"])
    assert result.exit_code == 0, result.output
    split_map = {}
    for split in ("train", "validation", "test", "golden_locked"):
        for line in (out / f"{split}.jsonl").read_text().splitlines():
            split_map[json.loads(line)["record_id"]] = split
    assert split_map["vid_1"] == split_map["vid_2"]
