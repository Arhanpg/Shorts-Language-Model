from shorts_intelligence.discovery.cli import _should_run_instagram_stage


def test_combined_discovery_runs_instagram_after_youtube_provisional_target():
    # The Instagram stage must not be skipped just because YouTube hit its
    # provisional target; only explicit platform selection/deadline can stop it.
    assert _should_run_instagram_stage("all", now=10.0, deadline=30.0)
    assert _should_run_instagram_stage("instagram", now=10.0, deadline=30.0)
    assert not _should_run_instagram_stage("youtube", now=10.0, deadline=30.0)
    assert not _should_run_instagram_stage("all", now=30.0, deadline=30.0)
