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

    def build(request, *, on_progress, cancel):
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


def test_second_start_is_refused():
    state, notifier = AppState(), FakeNotifier()
    release = threading.Event()
    calls = []

    def build(request, *, on_progress, cancel):
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

    def build(request, *, on_progress, cancel):
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

    def build(request, *, on_progress, cancel):
        raise EngineUnavailable("dggrid not found")

    gj.start_generation(state, _request(), notifier, TEXTS, build=build)
    _wait_idle(state)
    assert state.job.value == JobState(status="failed", name="g", level=17, message="engine missing")
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
