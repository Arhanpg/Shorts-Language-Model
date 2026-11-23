"""Tests for large creator/account and hashtag seed catalogue generation."""
from __future__ import annotations
import csv
import json
from pathlib import Path
from scripts.build_large_seed_catalogue import (
    ACCOUNT_FIELDS,
    TAG_FIELDS,
    build_tags,
    dedupe,
    map_instagram,
    map_youtube,
    page_offsets,
    write_csv,
)

def test_evenly_spaced_page_sampling():
    offsets=page_offsets(7_264_739,10_000,100)
    assert len(offsets)==100 and offsets==sorted(set(offsets))
    assert offsets[0]==0 and offsets[-1]>7_000_000

def test_youtube_is_channel_unknown_identity():
    row=map_youtube({"channel_id":"UC123","channel_handle":"@creator","url":"https://youtube.com/@creator"})
    assert row["entity_type"]=="unknown_person_or_org"
    assert row["short_form_status"]=="NOT_VERIFIED_FOR_SHORTS"
    assert row["rights_status"]=="NOT_ASSESSED_DISCOVERY_ONLY"

def test_instagram_person_org_separation():
    person=map_instagram({"username":"someperson","type":"person","rank":"2"})
    org=map_instagram({"username":"somebrand","type":"org","rank":"3"})
    assert person["entity_type"]=="person"
    assert org["entity_type"]=="organization"

def test_ai_duplicates_are_replaced_by_account_dataset_source():
    a={"account_handle":"@same","source_dataset":"submitted_AI_research"}
    b={"account_handle":"@same","source_dataset":"public_dataset"}
    assert dedupe([a,b])==[b]

def test_generated_hashtags_are_unverified(tmp_path: Path):
    (tmp_path/"languages.csv").write_text("language_id,language,iso_code\nL1,Hindi,hi\nL2,Kannada,kn\n",encoding="utf-8")
    (tmp_path/"categories.csv").write_text("category_id,category_name\nC1,Comedy and humour\nC2,Science and knowledge\n",encoding="utf-8")
    tags=build_tags(tmp_path,20)
    assert len(tags)==20 and len({x["normalized_hashtag"] for x in tags})==20
    assert all(x["verification_state"]=="GENERATED_UNVERIFIED_COMPOSITIONAL_CANDIDATE" for x in tags)
    assert all(x["native_speaker_review_status"]=="PENDING" for x in tags)
    assert "generation_rule" in TAG_FIELDS

def test_csv_writer_preserves_unicode_and_schema(tmp_path: Path):
    path=tmp_path/"accounts.csv"
    write_csv(path,[{"account_id":"ig:x","display_name":"ಕನ್ನಡ"}],ACCOUNT_FIELDS)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert row["display_name"]=="ಕನ್ನಡ" and list(row)==ACCOUNT_FIELDS


def test_fetch_youtube_reads_split_size_before_paging(monkeypatch):
    from scripts import build_large_seed_catalogue as module
    calls = []
    def fake_get_json(endpoint, params):
        calls.append(endpoint)
        if endpoint == "splits":
            return {"splits": [{"config": "boinko-youtube-channel-0.0.2", "split": "train"}]}
        if endpoint == "size":
            return {"size": {"splits": [{"config": "boinko-youtube-channel-0.0.2", "split": "train", "num_rows": 1000}]}}
        if endpoint == "rows":
            return {"num_rows_total": 1000, "rows": [
                {"row": {"channel_id": f"UC{i:021d}", "channel_handle": f"creator{i}"}}
                for i in range(100)
            ]}
        raise AssertionError(endpoint)
    monkeypatch.setattr(module, "get_json", fake_get_json)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    rows, meta = module.fetch_youtube(200)
    assert len(rows) == 200
    assert meta["total_rows"] == 1000
    assert calls[:2] == ["splits", "size"]
    assert calls.count("rows") == 2


def test_build_tags_uses_bundled_catalogue_without_v01_tree(tmp_path):
    path = tmp_path / "hashtags_generated_compositional_v0.2.csv"
    write_csv(path, [
        {"hashtag_id": f"H{i}", "hashtag": f"#tag{i}", "normalized_hashtag": f"tag{i}",
         "verification_state": "GENERATED_UNVERIFIED_COMPOSITIONAL_CANDIDATE"}
        for i in range(3)
    ], TAG_FIELDS)
    from scripts.build_large_seed_catalogue import build_tags
    result = build_tags(tmp_path, 3)
    assert len(result) == 3
    assert result[0]["verification_state"] == "GENERATED_UNVERIFIED_COMPOSITIONAL_CANDIDATE"


def test_large_seed_fixture_pack_is_synthetic_and_unique():
    fixture_path = Path(__file__).parent / "fixtures" / "large_seed_catalogue_cases.jsonl"
    cases = [json.loads(line) for line in fixture_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(cases) == 20
    assert len({x["test_case_id"] for x in cases}) == 20
    assert all(x["fixture_type"] == "SYNTHETIC_CATALOGUE_BUILDER_CONTRACT" for x in cases)
    assert all(x["media_asset_included"] is False for x in cases)
    assert all(x["model_evaluation_eligible"] is False for x in cases)


def test_youtube_handle_can_be_extracted_from_channel_url():
    row = map_youtube({"url": "https://www.youtube.com/@samplechannel"})
    assert row is not None
    assert row["account_handle"] == "@samplechannel"
    assert row["account_url"] == "https://www.youtube.com/@samplechannel"


def test_http_bytes_honours_retry_after(monkeypatch):
    import urllib.error
    from scripts import build_large_seed_catalogue as module

    calls = {"count": 0}
    waits = []
    class DummyResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return b"ok"

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.HTTPError(
                request.full_url, 429, "Too Many Requests",
                {"Retry-After": "3"}, None
            )
        return DummyResponse()

    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    monkeypatch.setattr(module.time, "sleep", waits.append)
    assert module.http_bytes("https://example.test/data") == b"ok"
    assert waits == [3.0]
    assert calls["count"] == 2
