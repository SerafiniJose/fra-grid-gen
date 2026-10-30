from types import SimpleNamespace

import geopandas as gpd
import pytest
import pyogrio
from _fakes import FakeMap
from shapely.geometry import box

from component.scripts import map_layers as ml


def _gpkg(tmp_path, centroids=False):
    path = tmp_path / "g.gpkg"
    frame = gpd.GeoDataFrame({"global_id": [1, 2]}, geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)], crs="EPSG:4326")
    pyogrio.write_dataframe(frame, path, layer="g", driver="GPKG")
    if centroids:
        squares = gpd.GeoDataFrame({"global_id": [1, 2]}, geometry=[box(0.4, 0.4, 0.6, 0.6), box(1.4, 0.4, 1.6, 0.6)],
                                   crs="EPSG:4326")
        pyogrio.write_dataframe(squares, path, layer="g_centroids", driver="GPKG")
    return path


def test_show_grid_replaces_previous_layer_and_zooms(tmp_path):
    m = FakeMap()
    path = _gpkg(tmp_path)
    ml.show_grid(m, path, "g", name="g")
    ml.show_grid(m, path, "g", name="g")
    assert len(m.layers) == 1 and m.layers[0].key == ml.GRID_LAYER_KEY
    assert tuple(m.zoomed) == (0.0, 0.0, 2.0, 1.0)
    assert m.layers[0].style["fillOpacity"] == 0.0


def test_remove_grid_layer_is_idempotent(tmp_path):
    m = FakeMap()
    ml.show_grid(m, _gpkg(tmp_path), "g", name="g")
    assert ml.remove_grid(m) is True
    assert ml.remove_grid(m) is False
    assert ml.remove_grid(None) is False


def test_remove_grid_forgets_layers_the_layers_control_hid(tmp_path):
    m = FakeMap()
    ml.show_grid(m, _gpkg(tmp_path, True), "g", name="g", centroids=(tmp_path / "g.gpkg", "g_centroids"))
    grid = m.find_layer(ml.GRID_LAYER_KEY)
    other = type("Layer", (), {"key": "someone_else"})()  # hashable, like an ipyleaflet layer
    control = SimpleNamespace(hidden={grid: 0, other: 1}, rebuilt=0)
    control.update_table = lambda change: setattr(control, "rebuilt", control.rebuilt + 1)
    m.controls.append(control)
    m.remove_layer(grid)  # what LayersControl does when its row is unchecked
    assert ml.remove_grid(m) is True and m.layers == []
    assert control.hidden == {other: 1} and control.rebuilt == 1
    assert ml.remove_grid(m) is False


def test_draw_control_hidden_off_the_aoi_tab_and_restored():
    m = FakeMap()
    m.controls.append(m.dc)
    hidden = ml.sync_draw_control_visibility(m, aoi_active=False, was_hidden=False)
    assert hidden is True and m.dc not in m.controls
    hidden = ml.sync_draw_control_visibility(m, aoi_active=False, was_hidden=hidden)
    assert hidden is True
    hidden = ml.sync_draw_control_visibility(m, aoi_active=True, was_hidden=hidden)
    assert hidden is False and m.dc in m.controls


def _plan_folder(tmp_path, *, cells=2, preview=True, pmtiles=True, centroids=False):
    _gpkg(tmp_path, centroids)
    if pmtiles:
        (tmp_path / ".preview.pmtiles").write_bytes(b"PMTiles\x03")
    meta = {"run": {"cell_count": cells, "formats": ["gpkg"]},
            "preview": {"file": ".preview.pmtiles", "minzoom": 10, "maxzoom": 13} if preview else None,
            "centroids": {"layer": "g_centroids", "side_m": 100.0} if centroids else None}
    return meta


def test_plan_prefers_pmtiles_and_keeps_the_geojson_fallback(tmp_path):
    plan = ml.plan_preview(tmp_path, "g", _plan_folder(tmp_path))
    assert plan.pmtiles == tmp_path / ".preview.pmtiles" and (plan.minzoom, plan.maxzoom) == (10, 13)
    assert plan.vector == (tmp_path / "g.gpkg", "g") and plan.available and not plan.centroids
    assert ml.plan_preview(tmp_path, "g", _plan_folder(tmp_path, centroids=True)).centroids


def test_plan_large_grid_only_via_pmtiles(tmp_path):
    plan = ml.plan_preview(tmp_path, "g", _plan_folder(tmp_path, cells=5_000_000))
    assert plan.pmtiles is not None and plan.vector is None and plan.available
    plan = ml.plan_preview(tmp_path, "g", _plan_folder(tmp_path, cells=5_000_000, preview=False))
    assert not plan.available


def test_plan_ignores_missing_file_and_foreign_names(tmp_path):
    meta = _plan_folder(tmp_path, pmtiles=False)
    assert ml.plan_preview(tmp_path, "g", meta).pmtiles is None
    (tmp_path / "evil.pmtiles").write_bytes(b"x")
    meta["preview"]["file"] = "evil.pmtiles"
    assert ml.plan_preview(tmp_path, "g", meta).pmtiles is None
    assert ml.plan_preview(tmp_path, "g", {}).available is False  # old/odd metadata


def test_preview_style_draws_one_source_layer_with_scalar_paint():
    url = "http://x/pmtiles?filePath=/a/.preview.pmtiles"
    style = ml.preview_style(url, "#76591e")
    assert style["sources"]["grid"]["url"].endswith(".pmtiles")
    [cells] = style["layers"]
    assert cells["type"] == "line" and cells["source-layer"] == "cells"
    assert cells["paint"] == {"line-color": "#76591e", "line-width": 1}
    [centroids] = ml.preview_style(url, "#76591e", "centroids")["layers"]
    assert centroids["source-layer"] == "centroids" and centroids["paint"] == cells["paint"]


def test_centroids_source_sits_beside_the_cells(tmp_path):
    assert ml.centroids_source((tmp_path / "g.gpkg", "g"), "g") == (tmp_path / "g.gpkg", "g_centroids")
    assert ml.centroids_source((tmp_path / "g.shp", "g"), "g") == (tmp_path / "g_centroids.shp", "g_centroids")


def test_geojson_preview_puts_the_centroids_on_their_own_layer(tmp_path):
    m = FakeMap()
    plan = ml.plan_preview(tmp_path, "g", _plan_folder(tmp_path, centroids=True, pmtiles=False))
    assert ml.show_preview(m, plan, name="g") is None
    assert [lyr.key for lyr in m.layers] == [ml.GRID_LAYER_KEY, ml.CENTROIDS_LAYER_KEY]
    assert m.find_layer(ml.CENTROIDS_LAYER_KEY).name == "g centroids"
    assert ml.remove_grid(m) is True and m.layers == []


def test_pmtiles_layer_sends_data_zoom_options():
    cls = ml._pmtiles_layer_class()
    layer = cls(url="http://x/a.pmtiles", max_data_zoom=13)
    assert {"max_data_zoom", "level_diff"} <= set(layer.options)
    assert layer.level_diff == 0 and layer.max_data_zoom == 13


def test_show_preview_falls_back_to_geojson_when_pmtiles_fails(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no tile server")

    monkeypatch.setattr(ml, "show_grid_pmtiles", boom)
    m = FakeMap()
    plan = ml.plan_preview(tmp_path, "g", _plan_folder(tmp_path))
    assert ml.show_preview(m, plan, name="g") is None
    assert len(m.layers) == 1 and m.layers[0].key == ml.GRID_LAYER_KEY
    big = ml.plan_preview(tmp_path, "g", _plan_folder(tmp_path, cells=5_000_000))
    with pytest.raises(RuntimeError):
        ml.show_preview(m, big, name="g")


def _fake_tile_client(monkeypatch):
    import vectortileserver.client as vc

    class FakeClient:
        def __init__(self, path):
            self.pmtiles_url = f"http://127.0.0.1:1/pmtiles?filePath={path}"

        def enable_jupyter_loopback(self):
            pass

    monkeypatch.setattr(vc, "TileClient", FakeClient)


def test_show_grid_pmtiles_adds_outline_and_aoi_and_zooms(tmp_path, monkeypatch):
    _fake_tile_client(monkeypatch)
    aoi = tmp_path / "aoi.geojson"
    gpd.GeoDataFrame(geometry=[box(0, 0, 1, 1)], crs="EPSG:4326").to_file(aoi, driver="GeoJSON")
    m = FakeMap()
    ml.show_grid(m, _gpkg(tmp_path), "g", name="g")  # a previous GeoJSON preview is replaced
    plan = ml.plan_preview(tmp_path, "g", _plan_folder(tmp_path))
    assert ml.show_preview(m, plan, name="g", bounds=[0, 0, 2, 1], aoi_path=aoi) == 10
    assert sorted(lyr.key for lyr in m.layers) == sorted([ml.GRID_LAYER_KEY, ml.AOI_LAYER_KEY])
    grid = m.find_layer(ml.GRID_LAYER_KEY)
    assert grid.max_data_zoom == 13 and grid.url.endswith(".pmtiles")
    assert m.find_layer(ml.AOI_LAYER_KEY).style["fillOpacity"] == 0.0
    assert m.zoomed == (0.0, 0.0, 2.0, 1.0)
    # Both follow the theme: SepalMap merges theme_style[is_dark] into style.
    light, dark = grid.theme_style[False], grid.theme_style[True]
    assert light["layers"][0]["paint"]["line-color"] != dark["layers"][0]["paint"]["line-color"]
    assert set(m.find_layer(ml.AOI_LAYER_KEY).theme_style) == {True, False}
    assert ml.remove_grid(m) is True and m.layers == []


def test_pmtiles_preview_puts_the_centroids_on_their_own_layer(tmp_path, monkeypatch):
    _fake_tile_client(monkeypatch)
    m = FakeMap()
    plan = ml.plan_preview(tmp_path, "g", _plan_folder(tmp_path, centroids=True))
    ml.show_preview(m, plan, name="g")
    grid, centroids = m.find_layer(ml.GRID_LAYER_KEY), m.find_layer(ml.CENTROIDS_LAYER_KEY)
    assert [lyr["source-layer"] for lyr in grid.style["layers"]] == ["cells"]
    assert [lyr["source-layer"] for lyr in centroids.style["layers"]] == ["centroids"]
    assert centroids.name == "g centroids" and centroids.max_data_zoom == 13
    assert centroids.theme_style[True]["layers"][0]["source-layer"] == "centroids"
    assert ml.remove_grid(m) is True and m.layers == []


def test_zoom_hint_needed():
    assert ml.zoom_hint_needed(9, 10) is True
    assert ml.zoom_hint_needed(10.0, 10) is False
    assert ml.zoom_hint_needed(3, None) is False


def test_preview_source_prefers_gpkg(tmp_path):
    (tmp_path / "g.gpkg").touch()
    (tmp_path / "g.shp").touch()
    assert ml.preview_source(tmp_path, "g", ("gpkg", "shp")) == (tmp_path / "g.gpkg", "g")
    assert ml.preview_source(tmp_path, "g", ("shp",)) == (tmp_path / "g.shp", "g")
    assert ml.preview_source(tmp_path / "nonexistent", "g", ("gpkg",)) is None
