from shorts_intelligence.discovery.models import AcquisitionAuthorization, DiscoveredCandidate
from shorts_intelligence.discovery.normalization import (
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
