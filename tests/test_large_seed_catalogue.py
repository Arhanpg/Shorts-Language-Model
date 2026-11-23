"""Tests for large creator/account and hashtag seed catalogue generation."""
from __future__ import annotations
import csv
from pathlib import Path
from scripts.build_large_seed_catalogue import ACCOUNT_FIELDS,TAG_FIELDS,build_tags,dedupe,map_instagram,map_youtube,page_offsets,write_csv

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
    with path.open(encoding="utf-8-sig",newline="") as stream: row=next(csv.DictReader(stream))
    assert row["display_name"]=="ಕನ್ನಡ" and list(row)==ACCOUNT_FIELDS
