from component.scripts import job_progress as jp


def test_plan_steps_skips_shapefile_unless_chosen():
    assert jp.plan_steps(("gpkg",)) == ("cells", "preview", "finish")
    assert jp.plan_steps(("gpkg", "shp")) == ("cells", "shp", "preview", "finish")
    assert jp.plan_steps(("shp",)) == ("cells", "shp", "preview", "finish")


def test_step_states_mark_done_current_pending():
    steps = ("cells", "shp", "preview", "finish")
    assert jp.step_states(steps, "preview") == [
        ("cells", "done"), ("shp", "done"), ("preview", "current"), ("finish", "pending")]
    assert jp.step_states(steps, "cells")[0] == ("cells", "current")
    # A step outside the plan (never expected) leaves everything pending rather than crash.
    assert jp.step_states(("cells",), "other") == [("cells", "pending")]


def test_remaining_seconds_needs_enough_progress_and_time():
    assert jp.remaining_seconds(10.0, 0.25) == 30.0
    assert jp.remaining_seconds(10.0, None) is None  # indeterminate step
    assert jp.remaining_seconds(10.0, 0.01) is None  # too early to project
    assert jp.remaining_seconds(1.0, 0.5) is None  # too few seconds of history
    assert jp.remaining_seconds(10.0, 1.0) is None  # step complete


def test_format_duration():
    assert jp.format_duration(0) == "0:00"
    assert jp.format_duration(5.4) == "0:05"
    assert jp.format_duration(754) == "12:34"
    assert jp.format_duration(3723) == "1:02:03"
    assert jp.format_duration(-3) == "0:00"
