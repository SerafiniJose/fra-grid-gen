import errno
import threading
import time
from pathlib import Path

import pytest

from component.model import generate_job as gj
from component.model.state_manager import AppState, JobState
from component.scripts.dggrid_engine import EngineUnavailable
from component.scripts.grid_builder import BuildCancelled, BuildRequest, BuildResult
from component.scripts.outputs_index import NotAGridFolder

TEXTS = gj.JobTexts(
    title="r17 grid · t",
    success="ready: {cells} cells → {file}",
    cancelled="cancelled",
    failed="failed: {error}",
    engine_missing="engine missing",
    disk_full="disk full",
    name_taken="name taken",
    progress="Tile {done}/{total} · {cells} cells",
)


class _Tracker:
    def __init__(self):
        self.steps, self.progress, self.failed = [], [], None

    def step(self, message):
        self.steps.append(message)

    def set_progress(self, value):
        self.progress.append(value)

    def fail(self, message):
        self.failed = message


class FakeNotifier:
    def __init__(self):
        self.tracker = _Tracker()
        self.toasts = []

    def track(self, title, total_steps=None):
        tracker = self.tracker

        class _Ctx:
            def __enter__(self):
                return tracker

            def __exit__(self, *exc):
                return False

        return _Ctx()

    def success(self, message, *, timeout=None):
        self.toasts.append(("success", message))

    def error(self, message, *, timeout=None):
        self.toasts.append(("error", message))

    def cancel(self, message, *, timeout=None):
        self.toasts.append(("cancel", message))


def _request(name="g"):
    return BuildRequest(aoi=object(), level=17, name=name)


def _wait_idle(state, timeout=5.0):
    end = time.monotonic() + timeout
    while state.job.value.running and time.monotonic() < end:
        time.sleep(0.01)
    assert not state.job.value.running, "job did not finish"


def _result(name="g"):
    folder = Path("/tmp/x") / name
    return BuildResult(name, folder, (folder / f"{name}.gpkg",), 330, 2, 1.2, {})


def test_success_publishes_result_and_toast():
    state, notifier = AppState(), FakeNotifier()

    def build(request, *, on_progress, cancel, **_):
        on_progress(1, 2, 100)
        on_progress(2, 2, 330)
        return _result()

    assert gj.start_generation(state, _request(), notifier, TEXTS, build=build)
    _wait_idle(state)
    assert state.job.value.status == "done" and state.job.value.cells == 330
    assert state.last_output.value.cell_count == 330
    assert state.outputs_signal.value == 1
    assert notifier.toasts == [("success", "ready: 330 cells → g.gpkg")]
    assert notifier.tracker.progress == [0.5, 1.0]
    assert state.cancel_event.value is None


def test_start_records_title_formats_and_first_step():
    state, notifier = AppState(), FakeNotifier()
    release = threading.Event()

    def build(request, *, on_progress, cancel, **_):
        release.wait(5)
        return _result()

    request = BuildRequest(aoi=object(), level=17, name="g", formats=("gpkg", "shp"))
    before = time.monotonic()
    gj.start_generation(state, request, notifier, TEXTS, build=build)
    job = state.job.value
    assert (job.title, job.formats, job.step, job.step_fraction) == ("r17 grid · t", ("gpkg", "shp"), "cells", 0.0)
    assert job.started_at >= before and job.step_started_at == job.started_at
    release.set()
    _wait_idle(state)


def test_steps_publish_the_current_step_and_whole_percent_changes(monkeypatch):
    ticks = iter(range(100))
    monkeypatch.setattr(gj, "_clock", lambda: float(next(ticks)))
    state, notifier = AppState(), FakeNotifier()
    seen = []

    def build(request, *, on_progress, cancel, on_step):
        def snap(step, fraction):
            on_step(step, fraction)
            job = state.job.value
            seen.append((job.step, job.step_fraction, job.step_started_at))

        snap("cells", 0.0)
        snap("cells", 0.5)
        snap("preview", 0.0)
        snap("preview", 0.004)  # under a whole percent: not re-published
        snap("preview", 0.62)
        snap("finish", None)
        return _result()

    gj.start_generation(state, _request(), notifier, TEXTS, build=build)
    _wait_idle(state)
    assert [(s, f) for s, f, _ in seen] == [
        ("cells", 0.0), ("cells", 0.5), ("preview", 0.0), ("preview", 0.0), ("preview", 0.62), ("finish", None)]
    starts = [t for _, _, t in seen]
    assert starts[0] == starts[1] < starts[2] == starts[3] == starts[4] < starts[5]


def test_done_records_the_finish_time(monkeypatch):
    ticks = iter(range(100))
    monkeypatch.setattr(gj, "_clock", lambda: float(next(ticks)))
    state = AppState()
    gj.start_generation(state, _request(), FakeNotifier(), TEXTS, build=lambda r, **_: _result())
    _wait_idle(state)
    job = state.job.value
    assert job.status == "done" and job.finished_at > job.started_at


def test_settle_opens_the_new_grid_and_clears_the_job_card():
    state = AppState()
    done = JobState(status="done", name="g", level=17)
    state.job.set(done)
    state.open_output.set("other")
    assert gj.settle_finished_job(state, done) is True
    assert state.open_output.value == "g" and state.job.value == JobState()


def test_settle_leaves_a_newer_job_alone():
    state = AppState()
    done = JobState(status="done", name="g", level=17)
    newer = JobState(status="running", name="h", level=17)
    state.job.set(newer)
    assert gj.settle_finished_job(state, done) is False
    assert state.job.value is newer and state.open_output.value is None


def test_dismiss_clears_a_finished_job_but_never_a_running_one():
    state = AppState()
    state.job.set(JobState(status="running", name="g", level=17))
    assert gj.dismiss_job(state) is False and state.job.value.running
    state.job.set(JobState(status="failed", name="g", level=17, message="boom"))
    assert gj.dismiss_job(state) is True and state.job.value == JobState()


def test_second_start_is_refused():
    state, notifier = AppState(), FakeNotifier()
    release = threading.Event()
    calls = []

    def build(request, *, on_progress, cancel, **_):
        calls.append(request.name)
        release.wait(5)
        return _result(request.name)

    assert gj.start_generation(state, _request("a"), notifier, TEXTS, build=build) is True
    assert gj.start_generation(state, _request("b"), notifier, TEXTS, build=build) is False
    assert gj.busy_names(state) == ("a",)
    release.set()
    _wait_idle(state)
    assert calls == ["a"] and gj.busy_names(state) == ()


def test_cancel_marks_cancelled_and_shows_cancel_toast():
    state, notifier = AppState(), FakeNotifier()
    started = threading.Event()

    def build(request, *, on_progress, cancel, **_):
        started.set()
        cancel.wait(5)
        raise BuildCancelled()

    gj.start_generation(state, _request(), notifier, TEXTS, build=build)
    assert started.wait(5)
    assert gj.cancel_generation(state) is True
    _wait_idle(state)
    assert state.job.value.status == "cancelled"
    assert notifier.toasts == [("cancel", "cancelled")]
    assert gj.cancel_generation(state) is False


def test_failure_marks_failed_with_one_error_toast():
    state, notifier = AppState(), FakeNotifier()

    def build(request, *, on_progress, cancel, **_):
        raise EngineUnavailable("dggrid not found")

    gj.start_generation(state, _request(), notifier, TEXTS, build=build)
    _wait_idle(state)
    job = state.job.value
    assert (job.status, job.name, job.level, job.message) == ("failed", "g", 17, "engine missing")
    assert notifier.toasts == [("error", "engine missing")]
    assert state.last_output.value is None


@pytest.mark.parametrize(
    "exc, expected",
    [
        (EngineUnavailable("x"), "engine missing"),
        (NotAGridFolder("/r/g"), "name taken"),
        (OSError(errno.ENOSPC, "No space left on device"), "disk full"),
        (RuntimeError("boom"), "failed: boom"),
        (RuntimeError(), "failed: RuntimeError"),
    ],
)
def test_format_error(exc, expected):
    assert gj.format_error(exc, TEXTS) == expected


def test_job_texts_resolve_placeholders_lazily():
    texts = gj.job_texts(18, "Chaco", "zz_grid")
    assert texts.title == "r18 grid · Chaco"
    assert texts.success.format(cells="935", file="g.gpkg") == "r18 grid ready: 935 cells → g.gpkg"
    assert texts.progress.format(done=1, total=2, cells="10") == "Tile 1/2 · 10 cells"
    assert "zz_grid" in texts.disk_full
    assert "{name}" not in texts.disk_full


def test_finished_job_does_not_clear_next_jobs_cancel_event():
    state, notifier = AppState(), FakeNotifier()
    gj.start_generation(state, _request("a"), notifier, TEXTS, build=lambda r, *, on_progress, cancel, **_: _result("a"))
    _wait_idle(state)
    started, release = threading.Event(), threading.Event()

    def build(request, *, on_progress, cancel, **_):
        started.set()
        cancel.wait(5)
        release.set()
        raise BuildCancelled()

    assert gj.start_generation(state, _request("b"), notifier, TEXTS, build=build)
    time.sleep(0.1)  # give a lingering first worker the chance to clobber the event
    assert state.cancel_event.value is not None
    assert gj.cancel_generation(state) is True
    assert release.wait(5)
    _wait_idle(state)
    assert state.job.value.status == "cancelled"


class _RaisingSuccessNotifier(FakeNotifier):
    def success(self, message, *, timeout=None):
        raise RuntimeError("toast bus gone")


class _RaisingCancelNotifier(FakeNotifier):
    def cancel(self, message, *, timeout=None):
        raise RuntimeError("toast bus gone")


def test_success_side_effect_raising_still_finishes_the_job():
    state, notifier = AppState(), _RaisingSuccessNotifier()
    gj.start_generation(state, _request(), notifier, TEXTS, build=lambda r, *, on_progress, cancel, **_: _result())
    _wait_idle(state)
    assert state.job.value.status == "failed"
    assert state.job.value.message == "failed: toast bus gone"
    assert state.cancel_event.value is None
    assert gj.start_generation(state, _request("b"), FakeNotifier(), TEXTS,
                               build=lambda r, *, on_progress, cancel, **_: _result("b"))
    _wait_idle(state)
    assert state.job.value.status == "done"


def test_cancel_side_effect_raising_still_finishes_the_job():
    state, notifier = AppState(), _RaisingCancelNotifier()

    def build(request, *, on_progress, cancel, **_):
        raise BuildCancelled()

    gj.start_generation(state, _request(), notifier, TEXTS, build=build)
    _wait_idle(state)
    assert state.job.value.status == "failed"
    assert state.cancel_event.value is None


def test_spawn_failure_rolls_the_start_back(monkeypatch):
    state = AppState()

    def broken_spawn(fn, args):
        raise RuntimeError("no thread")

    monkeypatch.setattr(gj, "spawn_in_context", broken_spawn)
    assert gj.start_generation(state, _request(), FakeNotifier(), TEXTS, build=lambda *a, **k: _result()) is False
    assert not state.job.value.running
    assert state.job.value.status == "failed" and state.job.value.message == "failed: no thread"
    assert state.cancel_event.value is None
