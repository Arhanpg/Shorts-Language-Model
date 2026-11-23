from pathlib import Path

from typer.testing import CliRunner

from shorts_intelligence.campaign import campaign_app


def test_sample_creates_platform_specific_random_seed_files(tmp_path: Path):
    catalogue = tmp_path / "catalogue"
    catalogue.mkdir()
    channel_id = "UC" + "a" * 22
    (catalogue / "youtube_creator_candidates.csv").write_text(
        "platform,identity,source,display_name,verification\n"
        f"youtube,{channel_id},source,Channel,unknown\n"
        "youtube,handle_only,source,Handle,unknown\n",
        encoding="utf-8",
    )
    (catalogue / "instagram_creator_candidates.csv").write_text(
        "platform,identity,source,display_name,verification\n"
        "instagram,creator.one,source,Creator,unknown\n",
        encoding="utf-8",
    )
    (catalogue / "hashtag_candidates.csv").write_text(
        "hashtag,language,domain,source\n"
        "comedy,en,entertainment,generated\n"
        "ಕನ್ನಡ,kn,comedy,generated\n",
        encoding="utf-8",
    )
    output = tmp_path / "sample"
    result = CliRunner().invoke(
        campaign_app,
        ["sample", "--catalogue-dir", str(catalogue), "--output-dir", str(output),
         "--creators", "10", "--hashtags", "1", "--seed", "42"],
    )
    assert result.exit_code == 0, result.output
    assert (output / "youtube_creator_seeds.txt").read_text(encoding="utf-8").strip() == channel_id
    assert (output / "instagram_creator_seeds.txt").read_text(encoding="utf-8").strip() == "creator.one"
    assert len((output / "youtube_hashtag_seeds.txt").read_text(encoding="utf-8").splitlines()) == 1
    assert len((output / "instagram_hashtag_seeds.txt").read_text(encoding="utf-8").splitlines()) == 1


def test_sample_is_reproducible_with_seed(tmp_path: Path):
    catalogue = tmp_path / "catalogue"
    catalogue.mkdir()
    rows = ["platform,identity,source,display_name,verification"]
    rows.extend(f"instagram,user{i},source,User {i},unknown" for i in range(20))
    (catalogue / "instagram_creator_candidates.csv").write_text("\n".join(rows) + "\n")
    (catalogue / "youtube_creator_candidates.csv").write_text(
        "platform,identity,source,display_name,verification\n"
    )
    (catalogue / "hashtag_candidates.csv").write_text(
        "hashtag,language,domain,source\ntag1,en,topic,generated\ntag2,en,topic,generated\n"
    )
    for output in (tmp_path / "one", tmp_path / "two"):
        result = CliRunner().invoke(
            campaign_app,
            ["sample", "--catalogue-dir", str(catalogue), "--output-dir", str(output),
             "--creators", "5", "--hashtags", "2", "--seed", "7"],
        )
        assert result.exit_code == 0, result.output
    assert (tmp_path / "one/instagram_creator_seeds.txt").read_text(encoding="utf-8") == (
        tmp_path / "two/instagram_creator_seeds.txt"
    ).read_text(encoding="utf-8")
