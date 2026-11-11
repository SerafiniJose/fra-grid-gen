import threading
from types import SimpleNamespace

import ipyvuetify as v

from component.tile import grid_tile as gt

OK = dict(running=False, name_error=None, name_state="free", verdict="ok", engine_ok=True)


def test_block_reason_order():
    assert gt.block_reason(**OK) is None
    assert gt.block_reason(**{**OK, "engine_ok": False}) == "grid.engine_missing"
    assert gt.block_reason(**{**OK, "running": True}) == "grid.generate"
    assert gt.block_reason(**{**OK, "name_error": "invalid"}) == "grid.name_error.invalid"
    assert gt.block_reason(**{**OK, "name_state": "taken"}) == "grid.name_taken"
    assert gt.block_reason(**{**OK, "verdict": "blocked"}) == "grid.blocked_hint"
    assert gt.block_reason(**{**OK, "name_state": "grid", "verdict": "warn"}) is None


def test_confirm_steps():
    assert gt.confirm_steps("ok", "free") == []
    assert gt.confirm_steps("warn", "free") == ["warn"]
    assert gt.confirm_steps("ok", "grid") == ["overwrite"]
    assert gt.confirm_steps("warn", "grid") == ["warn", "overwrite"]




def _button_labels(rc):
    return [w.children[0] for w in rc.find(v.Btn).widgets if w.children and isinstance(w.children[0], str)]





def _texts(rc):
    return [w.children[0] for w in rc.find(v.Html).widgets if w.children and isinstance(w.children[0], str)]


def _render_with_aoi(state, chaco_aoi, monkeypatch):
    from _notification_host import render_under_notifications

    monkeypatch.setattr(gt, "_engine_ok", lambda: True)
    state.aoi_info.set(chaco_aoi)
    return render_under_notifications(lambda: gt.GridTile(state=state, map_=None), handle_error=False)


def test_grid_tab_shows_no_job_progress_folder_or_result(results_root, chaco_aoi, monkeypatch):
    from component.model.state_manager import AppState, JobState

    state = AppState()
    state.job.set(JobState(status="running", name="g", level=17))
    state.cancel_event.set(threading.Event())
    box_, rc = _render_with_aoi(state, chaco_aoi, monkeypatch)
    try:
        in_dialogs = [w.children for w in rc.find(v.Dialog).find(v.Btn).widgets]
        assert _button_labels(rc).count("Cancel") == in_dialogs.count(["Cancel"])  # only the confirm dialogs'
        assert not rc.find(v.ProgressLinear).widgets
        generate = [w for w in rc.find(v.Btn).widgets if w.children == ["Generate grid"]]
        assert generate and generate[0].disabled
        texts = _texts(rc)
        assert "Output folder" not in texts and not any(str(results_root) in s for s in texts)
        state.last_output.set(SimpleNamespace(name="g", folder=results_root / "g", files=(), cell_count=1,
                                              duration_s=1.0, metadata={}))
        state.job.set(JobState(status="failed", name="g", level=17, message="boom happened"))
        assert not any("boom happened" in str(w.children) for w in rc.find(v.Alert).widgets)
        state.job.set(JobState(status="done", name="g", level=17))
        assert "Grid ready" not in _texts(rc) and "Show on map" not in _button_labels(rc)
    finally:
        rc.close()


def test_generate_starts_the_job_and_opens_the_outputs_tab(results_root, chaco_aoi, monkeypatch):
    from component.model.state_manager import AppState

    started = []
    monkeypatch.setattr(gt, "start_generation", lambda state, request, *a, **k: started.append(request) or True)
    state = AppState()
    box_, rc = _render_with_aoi(state, chaco_aoi, monkeypatch)
    try:
        assert state.active_tab.value == 0
        [w for w in rc.find(v.Btn).widgets if w.children == ["Generate grid"]][0].fire_event("click", {})
        assert [r.level for r in started] == [17]
        assert state.active_tab.value == 2
    finally:
        rc.close()


def test_a_refused_start_stays_on_the_grid_tab(results_root, chaco_aoi, monkeypatch):
    from component.model.state_manager import AppState

    monkeypatch.setattr(gt, "start_generation", lambda *a, **k: False)
    state = AppState()
    state.active_tab.set(1)
    box_, rc = _render_with_aoi(state, chaco_aoi, monkeypatch)
    try:
        [w for w in rc.find(v.Btn).widgets if w.children == ["Generate grid"]][0].fire_event("click", {})
        assert state.active_tab.value == 1
    finally:
        rc.close()


def _big_result(tmp_path, preview):
    (tmp_path / ".preview.pmtiles").write_bytes(b"PMTiles\x03")
    meta = {"run": {"formats": ["gpkg"], "cell_count": 3_000_000},
            "preview": {"file": ".preview.pmtiles", "minzoom": 10, "maxzoom": 13} if preview else None}
    return SimpleNamespace(name="g", folder=tmp_path, files=(), cell_count=3_000_000, duration_s=1.0, metadata=meta)




def test_zoom_hint_only_for_the_shown_pmtiles_grid_below_its_min_zoom():
    from component.model.state_manager import AppState

    state = AppState()
    state.preview_name.set("g")
    state.preview_minzoom.set(10)
    state.map_zoom.set(8)
    assert gt.zoom_hint_visible(state, "g") and not gt.zoom_hint_visible(state, "other")
    state.map_zoom.set(11)
    assert not gt.zoom_hint_visible(state, "g")
    state.preview_minzoom.set(None)  # GeoJSON preview: every zoom draws
    state.map_zoom.set(3)
    assert not gt.zoom_hint_visible(state, "g")


def test_show_on_map_failure_notifies_and_keeps_state(tmp_path, monkeypatch):
    from component.model.state_manager import AppState
    from component.scripts import map_layers as ml

    def boom(*a, **k):
        raise RuntimeError("no server")

    monkeypatch.setattr(ml, "show_preview", boom)
    errors = []
    notifier = SimpleNamespace(error=lambda m, timeout=None: errors.append(m))
    state = AppState()
    result = _big_result(tmp_path, True)
    assert gt.show_on_map(state, object(), tmp_path, "g", result.metadata, notifier) is False
    assert state.preview_name.value is None and errors and "no server" in errors[0]


def test_finished_overwrite_removes_the_shown_layer(results_root):
    from _fakes import FakeMap
    from _notification_host import render_under_notifications

    from component.model.state_manager import AppState, JobState
    from component.scripts import map_layers as ml

    state, m = AppState(), FakeMap()
    m.add_layer(SimpleNamespace(), key=ml.GRID_LAYER_KEY)
    state.preview_name.set("g")
    state.preview_minzoom.set(10)
    box_, rc = render_under_notifications(lambda: gt.GridTile(state=state, map_=m), handle_error=False)
    try:
        assert m.find_layer(ml.GRID_LAYER_KEY) is not None  # mounting alone changes nothing
        result = SimpleNamespace(name="g", folder=results_root / "g", files=(), cell_count=1, duration_s=1.0,
                                 metadata={"run": {"formats": ["gpkg"], "cell_count": 1}})
        state.last_output.set(result)
        state.job.set(JobState(status="done", name="g", level=17))
        assert m.find_layer(ml.GRID_LAYER_KEY) is None
        assert state.preview_name.value is None and state.preview_minzoom.value is None
    finally:
        rc.close()
