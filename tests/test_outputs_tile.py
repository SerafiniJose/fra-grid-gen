import json
from types import SimpleNamespace

import geopandas as gpd
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
