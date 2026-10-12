import geopandas as gpd
import pyogrio
from _fakes import FakeMap
from shapely.geometry import box

from component.scripts import map_layers as ml


def _gpkg(tmp_path):
    path = tmp_path / "g.gpkg"
    frame = gpd.GeoDataFrame({"global_id": [1, 2]}, geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)], crs="EPSG:4326")
    pyogrio.write_dataframe(frame, path, layer="g", driver="GPKG")
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


def test_draw_control_hidden_off_the_aoi_tab_and_restored():
    m = FakeMap()
    m.controls.append(m.dc)
    hidden = ml.sync_draw_control_visibility(m, aoi_active=False, was_hidden=False)
    assert hidden is True and m.dc not in m.controls
    hidden = ml.sync_draw_control_visibility(m, aoi_active=False, was_hidden=hidden)
    assert hidden is True
    hidden = ml.sync_draw_control_visibility(m, aoi_active=True, was_hidden=hidden)
    assert hidden is False and m.dc in m.controls
