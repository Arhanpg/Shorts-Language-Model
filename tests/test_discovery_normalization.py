from shorts_intelligence.discovery.models import AcquisitionAuthorization, DiscoveredCandidate
from shorts_intelligence.discovery.normalization import (
    candidate_from_instagram_post,
    candidate_from_ytdlp,
    canonical_instagram_url,
    canonical_youtube_url,
    extract_hashtags,
    instagram_shortcode_from_url,
    youtube_id_from_url,
)


def test_youtube_short_and_watch_urls_normalize():
    short = "https://youtube.com/shorts/AbCdEfGh123?feature=share"
    watch = "https://www.youtube.com/watch?v=AbCdEfGh123&t=4s"
    assert youtube_id_from_url(short) == "AbCdEfGh123"
    assert canonical_youtube_url(short) == "https://www.youtube.com/shorts/AbCdEfGh123"
    assert canonical_youtube_url(watch) == "https://www.youtube.com/watch?v=AbCdEfGh123"


def test_instagram_reel_url_normalizes():
    url = "https://www.instagram.com/reel/ABCxyz_123/?igsh=abc"
    assert instagram_shortcode_from_url(url) == "ABCxyz_123"
    assert canonical_instagram_url(url) == "https://www.instagram.com/reel/ABCxyz_123/"


def test_hashtags_are_deduplicated_case_insensitively():
    assert extract_hashtags("Great #Cricket #Shorts", "again #cricket") == ["cricket", "shorts"]


def test_missing_instagram_views_do_not_become_zero():
    candidate = DiscoveredCandidate(
        platform="instagram",
        source_id="ABCxyz_123",
        canonical_url="https://www.instagram.com/reel/ABCxyz_123/",
        view_count=None,
        play_count=None,
        short_format_status="confirmed",
    )
    assert candidate.qualifying_metric() is None


def test_instagram_play_count_is_opt_in_metric():
    candidate = DiscoveredCandidate(
        platform="instagram",
        source_id="ABCxyz_123",
        canonical_url="https://www.instagram.com/reel/ABCxyz_123/",
        view_count=None,
        play_count=1_200_000,
        short_format_status="confirmed",
    )
    assert candidate.qualifying_metric() is None
    assert candidate.qualifying_metric(accept_instagram_play_count=True) == 1_200_000


def test_training_rights_require_all_separate_scopes():
    rights = AcquisitionAuthorization(
        platform="youtube",
        source_id="AbCdEfGh123",
        basis="creator_permission",
        evidence_ref="consent-record-123",
        media_retrieval=True,
        media_analysis=True,
        temporary_processing=True,
        derived_artifact_retention=True,
        model_training=True,
    )
    rights.validate_for_training()


def test_ytdlp_vertical_short_is_confirmed():
    candidate = candidate_from_ytdlp({
        "id": "AbCdEfGh123",
        "webpage_url": "https://www.youtube.com/watch?v=AbCdEfGh123",
        "title": "Cricket moment #shorts",
        "description": "A fun clip #Cricket",
        "duration": 35,
        "upload_date": "20251101",
        "width": 1080,
        "height": 1920,
        "view_count": 1_450_000,
    })
    assert candidate is not None
    assert candidate.short_format_status == "confirmed"
    assert candidate.view_count == 1_450_000
    assert set(candidate.hashtags) == {"cricket", "shorts"}


def test_ytdlp_landscape_video_is_not_short():
    candidate = candidate_from_ytdlp({
        "id": "AbCdEfGh123",
        "webpage_url": "https://www.youtube.com/watch?v=AbCdEfGh123",
        "duration": 35,
        "upload_date": "20251101",
        "width": 1920,
        "height": 1080,
        "view_count": 2_000_000,
    })
    assert candidate is not None
    assert candidate.short_format_status == "not_short"


def test_ytdlp_unknown_upload_date_does_not_confirm_three_minute_short():
    candidate = candidate_from_ytdlp({
        "id": "AbCdEfGh123",
        "webpage_url": "https://www.youtube.com/watch?v=AbCdEfGh123",
        "duration": 120,
        "width": 1080,
        "height": 1920,
        "view_count": 2_000_000,
    })
    assert candidate is not None
    assert candidate.short_format_status == "unknown"


def test_instaloader_missing_lazy_view_metric_is_unknown():
    class FakePost:
        is_video = True
        shortcode = "ABCxyz_123"
        caption = "Test reel"
        video_duration = 20.0
        date_utc = None
        caption_hashtags = ["test"]
        owner_username = "sample_creator"

        @property
        def video_view_count(self):
            raise RuntimeError("field is not available")

        @property
        def video_play_count(self):
            raise RuntimeError("field is not available")

    candidate = candidate_from_instagram_post(FakePost())
    assert candidate is not None
    assert candidate.view_count is None
    assert candidate.play_count is None
    assert candidate.qualifying_metric() is None


def test_training_rights_reject_missing_scope_and_revocation():
    import pytest

    incomplete = AcquisitionAuthorization(
        platform="youtube",
        source_id="AbCdEfGh123",
        basis="creator_permission",
        evidence_ref="consent-record-123",
        media_retrieval=True,
        media_analysis=True,
        temporary_processing=True,
        derived_artifact_retention=True,
        model_training=False,
    )
    with pytest.raises(ValueError, match="model_training"):
        incomplete.validate_for_training()

    revoked = AcquisitionAuthorization(
        platform="youtube",
        source_id="AbCdEfGh123",
        basis="creator_permission",
        evidence_ref="consent-record-123",
        media_retrieval=True,
        media_analysis=True,
        temporary_processing=True,
        derived_artifact_retention=True,
        model_training=True,
        revoked=True,
    )
    with pytest.raises(ValueError, match="revoked"):
        revoked.validate_for_training()


def test_ytscrape_duration_text_parsing():
    from shorts_intelligence.discovery.normalization import parse_duration_text

    assert parse_duration_text("0:45") == 45.0
    assert parse_duration_text("12:34") == 754.0
    assert parse_duration_text("1:02:03") == 3723.0
    assert parse_duration_text("not a duration") is None


def test_ytscrape_shorts_result_is_marked_as_confirmed_and_keeps_search_provenance():
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from shorts_intelligence.discovery.normalization import candidate_from_ytscrape_video

    video = SimpleNamespace(
        video_id="AbCdEfGh123",
        title="Cricket finish #Cricket",
        channel="Sports Creator",
        channel_id="UC" + "a" * 22,
        description="Last ball #Shorts",
        duration="0:45",
        views=1_450_000,
        views_text="1.45M views",
        published_text="2 days ago",
        published_at=datetime(2026, 11, 19, tzinfo=UTC),
        thumbnail="https://example.invalid/thumb.jpg",
    )
    candidate = candidate_from_ytscrape_video(
        video,
        query="cricket shorts",
        language="hi",
        region="IN",
    )

    assert candidate is not None
    assert candidate.short_format_status == "confirmed"
    assert candidate.canonical_url == "https://www.youtube.com/shorts/AbCdEfGh123"
    assert candidate.view_count == 1_450_000
    assert candidate.duration_seconds == 45
    assert candidate.metric_source == "ytscrape_shorts_search_views"
    assert candidate.metadata["search_filter"] == "shorts"
    assert candidate.metadata["search_language"] == "hi"
    assert candidate.metadata["search_region"] == "IN"
    assert set(candidate.hashtags) == {"cricket", "shorts"}
