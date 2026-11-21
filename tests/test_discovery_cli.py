from shorts_intelligence.discovery.cli import _should_run_instagram_stage


def test_combined_discovery_runs_instagram_after_youtube_provisional_target():
    # The Instagram stage must not be skipped just because YouTube hit its
    # provisional target; only explicit platform selection/deadline can stop it.
    assert _should_run_instagram_stage("all", now=10.0, deadline=30.0)
    assert _should_run_instagram_stage("instagram", now=10.0, deadline=30.0)
    assert not _should_run_instagram_stage("youtube", now=10.0, deadline=30.0)
    assert not _should_run_instagram_stage("all", now=30.0, deadline=30.0)


def test_combined_stage_deadlines_reserve_time_for_both_platforms():
    from shorts_intelligence.discovery.cli import _stage_deadlines

    youtube, instagram = _stage_deadlines("all", started_at=10.0, budget_seconds=180)
    assert youtube == 121.6
    assert instagram == 181.0
    assert youtube < instagram


def test_single_platform_keeps_full_runtime_budget():
    from shorts_intelligence.discovery.cli import _stage_deadlines

    youtube, instagram = _stage_deadlines("youtube", started_at=10.0, budget_seconds=180)
    assert youtube == 190.0
    assert instagram == 181.0
    youtube, instagram = _stage_deadlines("instagram", started_at=10.0, budget_seconds=180)
    assert youtube == 121.6
    assert instagram == 190.0
