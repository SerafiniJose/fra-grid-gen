import json
import threading
from pathlib import Path
from types import SimpleNamespace

import geopandas as gpd
import ipyvuetify as v
import pyogrio
import pytest
from _fakes import FakeMap
from shapely.geometry import box

from component.model.state_manager import AppState, JobState
from component.scripts import map_layers as ml
from component.scripts.outputs_index import load_output
from component.tile import outputs_tile as ot


@pytest.fixture(autouse=True)
def inline_spawn(monkeypatch):
    """Add grids to the map on the calling thread, so the tests see the result at once."""
    monkeypatch.setattr(ot, "spawn_in_context", lambda target, args=(): target(*args))


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
    ot.toggle_preview(state, m, out)
    assert state.preview_name.value == "g" and m.find_layer(ml.GRID_LAYER_KEY) is not None
    assert ot.perform_delete(state, m, results_root, out, n) is True
    assert not (results_root / "g").exists()
    assert m.find_layer(ml.GRID_LAYER_KEY) is None and state.preview_name.value is None
    assert state.last_output.value is None
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


def test_delete_of_a_grid_removed_elsewhere_explains_and_relists(results_root):
    import shutil

    state, n = AppState(), FakeNotifier()
    out = _grid(results_root, "g")
    shutil.rmtree(results_root / "g")  # another tab or the file manager got there first
    assert ot.perform_delete(state, None, results_root, out, n) is False
    assert n.toasts == [("error", "g is no longer a grid folder made by this app. The list has been refreshed.")]
    assert state.outputs_signal.value == 1


def test_delete_keeps_other_preview(results_root):
    state, m, n = AppState(), FakeMap(), FakeNotifier()
    a, b = _grid(results_root, "a"), _grid(results_root, "b")
    ot.toggle_preview(state, m, a)
    ot.perform_delete(state, m, results_root, b, n)
    assert state.preview_name.value == "a" and m.find_layer(ml.GRID_LAYER_KEY) is not None


def test_delete_runs_on_a_worker_and_blocks_other_deletes_meanwhile(results_root, monkeypatch):
    spawned = []
    monkeypatch.setattr(ot, "spawn_in_context", lambda target, args=(): spawned.append(target))
    state, n = AppState(), FakeNotifier()
    a, b = _grid(results_root, "a"), _grid(results_root, "b")
    assert ot.start_delete(state, None, results_root, a, n) is True
    assert state.deleting.value == "a" and (results_root / "a").exists()  # nothing deleted on the click thread
    assert ot.start_delete(state, None, results_root, b, n) is False
    spawned[0]()
    assert not (results_root / "a").exists() and (results_root / "b").exists()
    assert state.deleting.value is None and n.toasts == [("success", "Deleted a.")]


def test_toggle_preview_hides_on_second_call(results_root):
    state, m = AppState(), FakeMap()
    out = _grid(results_root, "g")
    ot.toggle_preview(state, m, out)
    ot.toggle_preview(state, m, out)
    assert state.preview_name.value is None and m.find_layer(ml.GRID_LAYER_KEY) is None


def test_clicks_while_a_grid_is_being_added_are_ignored(results_root, monkeypatch):
    spawned = []
    monkeypatch.setattr(ot, "spawn_in_context", lambda target, args=(): spawned.append(target))
    state, m = AppState(), FakeMap()
    a, b = _grid(results_root, "a"), _grid(results_root, "b")
    ot.toggle_preview(state, m, a)
    assert state.preview_loading.value == "a" and len(spawned) == 1
    ot.toggle_preview(state, m, a)
    ot.toggle_preview(state, m, b)
    assert len(spawned) == 1 and m.layers == []
    box_, rc = _render_outputs(state, m)
    try:
        add = _icon(rc, "mdi-map-plus")
        assert [b.disabled for b in add] == [True, True] and sorted(b.loading for b in add) == [False, True]
        spawned[0]()
        assert state.preview_loading.value is None and state.preview_name.value == "a"
        assert [lyr.key for lyr in m.layers] == [ml.GRID_LAYER_KEY]
        assert not _icon(rc, "mdi-map-plus")[0].disabled
    finally:
        rc.close()


# ---- the list ---------------------------------------------------------------------

def _render_outputs(state, map_=None):
    from _notification_host import render_under_notifications

    return render_under_notifications(lambda: ot.OutputsTile(state=state, map_=map_), handle_error=False)


def _htmls(rc):
    """Every Html widget, including those nested in another Html (find() stops at those)."""
    out = []

    def walk(widget):
        out.append(widget)
        for child in widget.children or ():
            if isinstance(child, v.Html):
                walk(child)

    for w in rc.find(v.Html).widgets:
        walk(w)
    return out


def _strings(rc):
    return [c for w in _htmls(rc) for c in w.children or () if isinstance(c, str)]


def _buttons(rc, label):
    """Buttons with ``label`` outside the (closed) confirm dialogs."""
    in_dialogs = {id(w) for w in rc.find(v.Dialog).find(v.Btn).widgets}
    return [w for w in rc.find(v.Btn).widgets if label in w.children and id(w) not in in_dialogs]


def _icon(rc, name):
    """The icon buttons showing ``name``, in row order."""
    return [w for w in rc.find(v.Btn).widgets if any(isinstance(c, v.Icon) and name in c.children for c in w.children)]


def _tips(rc):
    return [w.attributes["title"] for w in _htmls(rc) if w.attributes and "aria-label" in w.attributes]


def _job(status, **changes):
    request = SimpleNamespace(aoi=SimpleNamespace(label="Chaco"), level=17, name="chaco_r17")
    base = dict(status=status, name="chaco_r17", level=17,
                request=request)
    return JobState(**{**base, **changes})


def test_running_row_offers_cancel_and_waits_for_the_rest(results_root):
    state = AppState()
    state.job.set(_job("running"))
    state.cancel_event.set(threading.Event())
    box_, rc = _render_outputs(state)
    try:
        texts = _strings(rc)
        assert "chaco_r17" in texts and "Chaco" in texts and "r17" in str([w.children for w in rc.find(v.Chip).widgets])
        assert not rc.find(v.ProgressLinear).widgets  # progress is in the notification pill
        assert "No grids yet. Generate one in the Grid tab." not in str([w.children for w in rc.find(v.Alert).widgets])
        for icon in ("mdi-map-plus", "mdi-information-outline", "mdi-download", "mdi-delete-outline"):
            assert [b.disabled for b in _icon(rc, icon)] == [True], icon
        tips = _tips(rc)
        assert tips.count("Available once the grid is ready") == 3 and "Wait for the grid to finish" in tips
        assert "Stop generating. Nothing is written." in tips
        _buttons(rc, "Cancel")[0].fire_event("click", {})
        assert state.cancel_event.value.is_set()
    finally:
        rc.close()


def test_failed_row_shows_the_reason_retries_and_dismisses(results_root, monkeypatch):
    retried = []
    monkeypatch.setattr(ot, "retry_generation", lambda state, notifier: retried.append(state.job.value.name))
    state = AppState()
    state.job.set(_job("failed", message="Grid generation failed: boom"))
    box_, rc = _render_outputs(state)
    try:
        assert "Grid generation failed: boom" in _strings(rc)
        assert not _buttons(rc, "Cancel")
        tips = _tips(rc)
        assert "Generate again with the same settings: r17 · Chaco" in tips
        _buttons(rc, "Retry")[0].fire_event("click", {})
        assert retried == ["chaco_r17"]
        delete = _icon(rc, "mdi-delete-outline")
        assert len(delete) == 1 and not delete[0].disabled and "Remove from the list" in tips
        delete[0].fire_event("click", {})
        assert state.job.value == JobState()
        assert "chaco_r17" not in _strings(rc)
    finally:
        rc.close()


def test_cancelled_row_offers_generate(results_root):
    state = AppState()
    state.job.set(_job("cancelled", message="cancelled"))
    box_, rc = _render_outputs(state)
    try:
        assert _buttons(rc, "Generate") and not _buttons(rc, "Retry")
    finally:
        rc.close()


def test_done_job_has_no_row_of_its_own(results_root):
    _grid(results_root, "chaco_r17")
    state = AppState()
    state.job.set(_job("done"))
    box_, rc = _render_outputs(state)
    try:
        assert _strings(rc).count("chaco_r17") == 1 and "Ready" in _strings(rc)
        assert not _buttons(rc, "Cancel") and not _buttons(rc, "Retry")
    finally:
        rc.close()


def test_grid_row_actions(results_root):
    out = _grid(results_root, "a")
    geo_json = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [0, 0]}}]}
    (out.folder / "aoi.geojson").write_text(json.dumps(geo_json))
    state, m = AppState(), FakeMap()
    box_, rc = _render_outputs(state, map_=m)
    try:
        tips = _tips(rc)
        for tip in ("Show on map", "Details: files, AOI and run", "Delete this grid…"):
            assert tip in tips, tip
        add = _icon(rc, "mdi-map-plus")
        assert len(add) == 1 and not add[0].disabled
        add[0].fire_event("click", {})
        assert state.preview_name.value == "a" and m.find_layer(ml.GRID_LAYER_KEY) is not None
        assert "Remove from map" in _tips(rc)
        _icon(rc, "mdi-map-minus")[0].fire_event("click", {})
        assert state.preview_name.value is None

        assert "a.gpkg" not in _strings(rc)
        _icon(rc, "mdi-information-outline")[0].fire_event("click", {})
        texts = _strings(rc)
        assert "a.gpkg" in texts and str(results_root / "a") in texts
        assert "Map preview" in texts and "Total, with the map preview" in texts
    finally:
        rc.close()


def test_grid_row_delete_asks_first_and_is_off_while_generating(results_root):
    _grid(results_root, "a")
    state = AppState()
    box_, rc = _render_outputs(state)
    try:
        assert not any(w.v_model for w in rc.find(v.Dialog).widgets)
        _icon(rc, "mdi-delete-outline")[0].fire_event("click", {})
        assert any(w.v_model for w in rc.find(v.Dialog).widgets)
        assert (results_root / "a").exists()
        state.job.set(JobState(status="running", name="a", level=17))
        assert [b.disabled for b in _icon(rc, "mdi-delete-outline")] == [True, True]
        assert "This grid is being generated." in _tips(rc)
    finally:
        rc.close()



def test_grid_row_download_offers_layers_and_formats(results_root, monkeypatch):
    from component.widget import download_dialog as dd

    _grid(results_root, "a")
    calls = []

    def fake_zip(folder, layer, fmt, dest):
        calls.append((layer, fmt))
        (Path(dest) / "x.zip").write_bytes(b"zip")
        return Path(dest) / "x.zip"

    monkeypatch.setattr(dd, "export_zip", fake_zip)
    box_, rc = _render_outputs(AppState())
    try:
        assert "Download…" in _tips(rc)
        _icon(rc, "mdi-download")[0].fire_event("click", {})
        dialog = [w for w in rc.find(v.Dialog).widgets if w.v_model]
        assert len(dialog) == 1
        radios = {r.value: bool(r.disabled) for r in rc.find(v.Radio).widgets}
        assert radios == {"cells": False, "centroids": True, "gpkg": False, "shp": False}  # no centroids layer
        assert dd.zip_bytes(results_root / "a", "a", "shp") == b"zip" and calls == [("a", "shp")]
    finally:
        rc.close()
