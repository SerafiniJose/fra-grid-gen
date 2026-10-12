import shutil
import threading

import numpy as np
import pytest
from shapely.geometry import box

from component.scripts import dggrid_engine as engine

pytestmark = pytest.mark.skipif(shutil.which("dggrid") is None, reason="dggrid binary not on PATH")


def test_polygons_for_extent_returns_int64_ids_in_sphere_space():
    gdf = engine.polygons_for_extent(17, box(-60.1, -22.3, -60.0, -22.2))
    assert list(gdf.columns) == ["global_id", "geometry"]
    assert gdf["global_id"].dtype == np.int64
    assert gdf.crs.to_epsg() == 4326
    assert len(gdf) > 200 and gdf["global_id"].is_unique


def test_cells_for_points_keeps_input_order():
    rng = np.random.default_rng(1)
    lon = rng.uniform(-60.1, -60.0, 200)
    lat = rng.uniform(-22.3, -22.2, 200)
    fwd = engine.cells_for_points(17, lon, lat)
    rev = engine.cells_for_points(17, lon[::-1], lat[::-1])
    assert fwd.dtype == np.int64 and len(fwd) == 200
    np.testing.assert_array_equal(fwd, rev[::-1])


def test_versions_reports_both_components():
    v = engine.versions()
    assert v["dggrid4py"] == "0.6.0"
    assert v["dggrid"].startswith("8.")


def test_missing_binary_raises_engine_unavailable(monkeypatch):
    monkeypatch.setenv("FRA_GRID_DGGRID", "/nonexistent/dggrid")
    monkeypatch.setattr(engine, "_ENGINE", None)
    with pytest.raises(engine.EngineUnavailable):
        engine.polygons_for_extent(17, box(0, 0, 0.01, 0.01))


def test_calls_restore_cwd_and_serialise(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    errors = []

    def work():
        try:
            engine.polygons_for_extent(17, box(-60.1, -22.3, -60.05, -22.25))
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(3)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    import os

    assert os.getcwd() == str(tmp_path)
