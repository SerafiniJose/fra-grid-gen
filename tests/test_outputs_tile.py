import json
import re
import threading
import time
from types import SimpleNamespace

import geopandas as gpd
import ipyvuetify as v
import pyogrio
from _fakes import FakeMap
from shapely.geometry import box

from component.model.state_manager import AppState, JobState
from component.scripts import map_layers as ml
from component.scripts.outputs_index import load_output
from component.tile import outputs_tile as ot


class FakeNotifier:
    def __init__(self):
        self.toasts = []

    def success(self, m, *, timeout=None):
        self.toasts.append(("success", m))

    def warning(self, m, *, timeout=None):
        self.toasts.append(("warning", m))

    def error(self, m, *, timeout=None):
        self.toasts.append(("error", m))


def _grid(root, name):
    folder = root / name
    folder.mkdir()
    frame = gpd.GeoDataFrame({"global_id": [1]}, geometry=[box(0, 0, 1, 1)], crs="EPSG:4326")
    pyogrio.write_dataframe(frame, folder / f"{name}.gpkg", layer=name, driver="GPKG")
    record = {"schema": "fra-grid-metadata/1", "name": name, "generated_at": "2026-10-12T00:00:00Z",
              "dggs": {"resolution": 17}, "aoi": {"label": "t"},
              "run": {"cell_count": 1, "formats": ["gpkg"], "files": [f"{name}.gpkg", "metadata.json"]}}
    (folder / "metadata.json").write_text(json.dumps(record))
    return load_output(root, name)


def test_delete_removes_folder_layer_and_last_output(results_root):
    state, m, n = AppState(), FakeMap(), FakeNotifier()
    out = _grid(results_root, "g")
    state.last_output.set(SimpleNamespace(name="g"))
    state.open_output.set("g")
    ot.toggle_preview(state, m, out)
    assert state.preview_name.value == "g" and m.find_layer(ml.GRID_LAYER_KEY) is not None
    assert ot.perform_delete(state, m, results_root, out, n) is True
    assert not (results_root / "g").exists()
    assert m.find_layer(ml.GRID_LAYER_KEY) is None and state.preview_name.value is None
    assert state.last_output.value is None and state.open_output.value is None
    assert state.outputs_signal.value == 1
    assert n.toasts == [("success", "Deleted g.")]


def test_delete_other_grid_keeps_last_output(results_root):
    state, n = AppState(), FakeNotifier()
    a, b = _grid(results_root, "a"), _grid(results_root, "b")
    last = SimpleNamespace(name="a")
    state.last_output.set(last)
    assert ot.perform_delete(state, FakeMap(), results_root, b, n) is True
    assert state.last_output.value is last


def test_delete_refuses_the_running_job(results_root):
    state, n = AppState(), FakeNotifier()
    out = _grid(results_root, "g")
    state.job.set(JobState(status="running", name="g", level=17))
    assert ot.perform_delete(state, None, results_root, out, n) is False
    assert (results_root / "g").exists()
    assert n.toasts == [("warning", "This grid is being generated.")]


def test_delete_keeps_other_preview(results_root):
    state, m, n = AppState(), FakeMap(), FakeNotifier()
    a, b = _grid(results_root, "a"), _grid(results_root, "b")
    ot.toggle_preview(state, m, a)
    ot.perform_delete(state, m, results_root, b, n)
    assert state.preview_name.value == "a" and m.find_layer(ml.GRID_LAYER_KEY) is not None


def test_toggle_preview_hides_on_second_call(results_root):
    state, m = AppState(), FakeMap()
    out = _grid(results_root, "g")
    ot.toggle_preview(state, m, out)
    ot.toggle_preview(state, m, out)
    assert state.preview_name.value is None and m.find_layer(ml.GRID_LAYER_KEY) is None


# ---- the job card ---------------------------------------------------------------

def _render_outputs(state, map_=None):
    from _notification_host import render_under_notifications

    return render_under_notifications(lambda: ot.OutputsTile(state=state, map_=map_), handle_error=False)


def _strings(rc):
    """Text of every Html widget, including those nested in another Html (find() stops at those)."""
    out = []

    def walk(widget):
        for child in widget.children or ():
            if isinstance(child, str):
                out.append(child)
            elif isinstance(child, v.Html):
                walk(child)

    for w in rc.find(v.Html).widgets:
        walk(w)
    return out


def _buttons(rc, label):
    """Buttons with ``label`` outside the (closed) confirm dialogs."""
    in_dialogs = {id(w) for w in rc.find(v.Dialog).find(v.Btn).widgets}
    return [w for w in rc.find(v.Btn).widgets if label in w.children and id(w) not in in_dialogs]


def _running(**changes):
    now = time.monotonic()
    base = dict(status="running", name="chaco_r17", level=17, title="r17 grid · Chaco", formats=("gpkg", "shp"),
                started_at=now - 125, step="preview", step_fraction=0.62, step_started_at=now - 30,
                done=4, total=4, cells=1234)
    return JobState(**{**base, **changes})


def test_job_card_shows_steps_progress_and_times(results_root):
    state = AppState()
    state.job.set(_running())
    state.cancel_event.set(threading.Event())
    box_, rc = _render_outputs(state)
    try:
        texts = _strings(rc)
        assert "chaco_r17" in texts and "r17 grid · Chaco · GPKG, SHP" in texts
        for label in ("Generating cells", "Converting to Shapefile", "Building map preview (PMTiles)",
                      "Writing files and metadata"):
            assert label in texts, texts
        assert "Tile 4/4 · 1,234 cells" in texts
        assert "tippecanoe is cutting vector tiles · 62%" in texts
        assert any(s.startswith("A hidden PMTiles file") for s in texts)
        assert any(re.fullmatch(r"Elapsed 2:0\d · about 0:\d\d left", s) for s in texts), texts
        assert rc.find(v.ProgressLinear).widget.value == 62
        assert "No grids yet. Generate one in the Grid tab." not in str([w.children for w in rc.find(v.Alert).widgets])
        _buttons(rc, "Cancel")[0].fire_event("click", {})
        assert state.cancel_event.value.is_set()
    finally:
        rc.close()


def test_job_card_early_cells_step_is_estimating_and_skips_shapefile(results_root):
    state = AppState()
    state.job.set(_running(formats=("gpkg",), step="cells", step_fraction=0.01, done=0, total=0, cells=0))
    box_, rc = _render_outputs(state)
    try:
        texts = _strings(rc)
        assert "Converting to Shapefile" not in texts
        assert any(re.fullmatch(r"Elapsed 2:0\d · estimating time left…", s) for s in texts), texts
        assert not any(s.startswith("A hidden PMTiles file") for s in texts)  # preview not started yet
    finally:
        rc.close()


def test_job_card_without_a_measurable_step_shows_only_elapsed(results_root):
    state = AppState()
    state.job.set(_running(step="finish", step_fraction=None))
    box_, rc = _render_outputs(state)
    try:
        assert any(re.fullmatch(r"Elapsed 2:0\d", s) for s in _strings(rc))
        assert rc.find(v.ProgressLinear).widget.indeterminate
    finally:
        rc.close()


def test_failed_job_card_shows_the_reason_until_dismissed(results_root):
    state = AppState()
    state.job.set(_running(status="failed", message="Grid generation failed: boom"))
    box_, rc = _render_outputs(state)
    try:
        assert any("Grid generation failed: boom" in str(w.children) for w in rc.find(v.Alert).widgets)
        assert not _buttons(rc, "Cancel")
        _buttons(rc, "Dismiss")[0].fire_event("click", {})
        assert state.job.value == JobState()
        assert "chaco_r17" not in _strings(rc)
    finally:
        rc.close()


def _wait_for(cond, timeout=3.0):
    end = time.monotonic() + timeout
    while not cond() and time.monotonic() < end:
        time.sleep(0.01)
    return cond()


def _heads(rc):
    return [w for w in rc.find(v.Html).widgets if "output-head" in (w.class_ or "")]


def _eyes(rc):
    return [w for w in rc.find(v.Btn).widgets if "output-eye" in (w.class_ or "")]


def test_finished_job_shows_ready_then_opens_the_new_grid(results_root, monkeypatch):
    from component.widget import job_card

    monkeypatch.setattr(job_card, "READY_SECONDS", 0.05)
    _grid(results_root, "chaco_r17")
    state = AppState()
    now = time.monotonic()
    state.job.set(_running(status="done", step="finish", step_fraction=None, started_at=now - 125, finished_at=now))
    box_, rc = _render_outputs(state)
    try:
        texts = _strings(rc)
        assert any("Ready" in w.children for w in rc.find(v.Chip).widgets)
        assert "Finished in 2:05" in texts
        assert texts.count("chaco_r17") == 1  # the job card; its list entry waits for the hand-over
        assert not _buttons(rc, "Cancel")
        assert _wait_for(lambda: state.open_output.value == "chaco_r17")
        assert state.job.value == JobState()
        assert _wait_for(lambda: not any("Ready" in w.children for w in rc.find(v.Chip).widgets))
        texts = _strings(rc)
        assert texts.count("chaco_r17") == 1 and "chaco_r17.gpkg" in texts  # now the open list card
        assert _buttons(rc, "Metadata")
    finally:
        rc.close()


def test_cards_start_closed_and_one_opens_at_a_time(results_root):
    _grid(results_root, "a")
    _grid(results_root, "b")
    state = AppState()
    box_, rc = _render_outputs(state)
    try:
        assert len(_heads(rc)) == 2
        assert not _buttons(rc, "Metadata") and not _buttons(rc, "Delete")
        assert "a.gpkg" not in _strings(rc)
        _heads(rc)[0].fire_event("click", {})
        first = state.open_output.value
        assert first in ("a", "b")
        texts = _strings(rc)
        assert f"{first}.gpkg" in texts and str(results_root / first) in texts
        assert len(_buttons(rc, "Metadata")) == 1 and len(_buttons(rc, "Delete")) == 1
        _heads(rc)[1].fire_event("click", {})
        second = state.open_output.value
        assert second != first and second in ("a", "b")
        assert len(_buttons(rc, "Metadata")) == 1 and f"{first}.gpkg" not in _strings(rc)
        _heads(rc)[1].fire_event("click", {})
        assert state.open_output.value is None and not _buttons(rc, "Metadata")
    finally:
        rc.close()


def test_eye_shows_the_grid_on_the_map_without_opening_its_card(results_root):
    _grid(results_root, "a")
    state, m = AppState(), FakeMap()
    box_, rc = _render_outputs(state, map_=m)
    try:
        eyes = _eyes(rc)
        assert len(eyes) == 1 and not eyes[0].disabled
        eyes[0].fire_event("click", {})
        assert state.preview_name.value == "a" and m.find_layer(ml.GRID_LAYER_KEY) is not None
        assert state.open_output.value is None
        _eyes(rc)[0].fire_event("click", {})
        assert state.preview_name.value is None
    finally:
        rc.close()
