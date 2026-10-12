import threading
from types import SimpleNamespace

import ipyvuetify as v
import reacton

from component.tile import grid_tile as gt

OK = dict(running=False, name_error=None, name_state="free", formats=("gpkg",), verdict="ok", engine_ok=True)


def test_effective_formats_drops_shp_when_not_allowed():
    assert gt.effective_formats(frozenset({"shp", "gpkg"}), True) == ("gpkg", "shp")
    assert gt.effective_formats(frozenset({"shp", "gpkg"}), False) == ("gpkg",)
    assert gt.effective_formats(frozenset({"shp"}), False) == ()


def test_block_reason_order():
    assert gt.block_reason(**OK) is None
    assert gt.block_reason(**{**OK, "engine_ok": False}) == "grid.engine_missing"
    assert gt.block_reason(**{**OK, "running": True}) == "grid.generate"
    assert gt.block_reason(**{**OK, "name_error": "invalid"}) == "grid.name_error.invalid"
    assert gt.block_reason(**{**OK, "name_state": "taken"}) == "grid.name_taken"
    assert gt.block_reason(**{**OK, "formats": ()}) == "grid.formats_empty"
    assert gt.block_reason(**{**OK, "verdict": "blocked"}) == "grid.blocked_hint"
    assert gt.block_reason(**{**OK, "name_state": "grid", "verdict": "warn"}) is None


def test_confirm_steps():
    assert gt.confirm_steps("ok", "free") == []
    assert gt.confirm_steps("warn", "free") == ["warn"]
    assert gt.confirm_steps("ok", "grid") == ["overwrite"]
    assert gt.confirm_steps("warn", "grid") == ["warn", "overwrite"]


def test_file_lines_show_name_and_size_and_skip_missing(tmp_path):
    f = tmp_path / "g.gpkg"
    f.write_bytes(b"x" * 2048)
    lines = gt.file_lines((f, tmp_path / "gone.shp"))
    assert len(lines) == 1
    assert lines[0].startswith("g.gpkg · ") and "KB" in lines[0]


def test_result_card_lists_files_with_sizes(tmp_path):
    f = tmp_path / "g.gpkg"
    f.write_bytes(b"x" * 2048)
    result = SimpleNamespace(name="g", folder=tmp_path, files=(f,), cell_count=10, duration_s=1.5,
                             metadata={"run": {"formats": ["gpkg"]}})
    box_, rc = reacton.render(
        gt.ResultCard(result=result, map_=None, on_show=lambda: None, on_metadata=lambda: None),
        handle_error=False)
    try:
        texts = [w.children[0] for w in rc.find(v.Html).widgets if w.children and isinstance(w.children[0], str)]
        assert any(s.startswith("g.gpkg · ") and "KB" in s for s in texts), texts
        assert str(tmp_path) in texts
    finally:
        rc.close()


def _button_labels(rc):
    return [w.children[0] for w in rc.find(v.Btn).widgets if w.children and isinstance(w.children[0], str)]


def test_cancel_stays_reachable_when_the_aoi_is_cleared_mid_job(results_root):
    from component.model.state_manager import AppState, JobState
    from _notification_host import render_under_notifications

    state = AppState()  # aoi_info is None, e.g. the AOI tab is resolving a new AOI
    state.job.set(JobState(status="running", name="g", level=17, done=1, total=4, cells=50))
    state.cancel_event.set(threading.Event())
    box_, rc = render_under_notifications(lambda: gt.GridTile(state=state, map_=None), handle_error=False)
    try:
        cancel = [w for w in rc.find(v.Btn).widgets if w.children == ["Cancel"]]
        assert len(cancel) == 1, _button_labels(rc)
        cancel[0].fire_event("click", {})
        assert state.cancel_event.value.is_set()
        assert "Generate grid" not in _button_labels(rc)
    finally:
        rc.close()


def test_failed_message_shows_without_an_aoi(results_root):
    from component.model.state_manager import AppState, JobState
    from _notification_host import render_under_notifications

    state = AppState()
    state.job.set(JobState(status="failed", name="g", level=17, message="boom happened"))
    box_, rc = render_under_notifications(lambda: gt.GridTile(state=state, map_=None), handle_error=False)
    try:
        assert any("boom happened" in str(w.children) for w in rc.find(v.Alert).widgets)
    finally:
        rc.close()


def _card_texts(rc):
    return [w.children[0] for w in rc.find(v.Html).widgets if w.children and isinstance(w.children[0], str)]


def _big_result(tmp_path, preview):
    (tmp_path / ".preview.pmtiles").write_bytes(b"PMTiles\x03")
    meta = {"run": {"formats": ["gpkg"], "cell_count": 3_000_000},
            "preview": {"file": ".preview.pmtiles", "minzoom": 10, "maxzoom": 13} if preview else None}
    return SimpleNamespace(name="g", folder=tmp_path, files=(), cell_count=3_000_000, duration_s=1.0, metadata=meta)


def test_result_card_large_grid_with_preview_can_be_shown(tmp_path):
    box_, rc = reacton.render(
        gt.ResultCard(result=_big_result(tmp_path, True), map_=object(), on_show=lambda: None,
                      on_metadata=lambda: None, zoom_hint=True), handle_error=False)
    try:
        show = [w for w in rc.find(v.Btn).widgets if w.children == ["Show on map"]]
        assert show and not show[0].disabled
        texts = _card_texts(rc)
        assert "Zoom in to see the cells." in texts
        assert not any("limited to 50,000" in s for s in texts)
    finally:
        rc.close()


def test_result_card_large_grid_without_preview_is_capped(tmp_path):
    box_, rc = reacton.render(
        gt.ResultCard(result=_big_result(tmp_path, False), map_=object(), on_show=lambda: None,
                      on_metadata=lambda: None), handle_error=False)
    try:
        show = [w for w in rc.find(v.Btn).widgets if w.children == ["Show on map"]]
        assert show[0].disabled
        assert any("limited to 50,000" in s for s in _card_texts(rc))
    finally:
        rc.close()


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
