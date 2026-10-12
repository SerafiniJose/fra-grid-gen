"""Golden check against the 2024 DGGRID reference (uncorrected sphere cells)."""

import shutil
from pathlib import Path

import numpy as np
import pyogrio
import pytest
import shapely
from shapely.geometry import box

from component.parameter import grid
from component.scripts import dggrid_engine as engine
from component.scripts import levels

REF = Path(__file__).resolve().parents[1] / "reference_data" / "output" / "isea3hr17_528.shp"
pytestmark = [
    pytest.mark.golden,
    pytest.mark.skipif(not REF.exists(), reason="reference_data not extracted"),
    pytest.mark.skipif(shutil.which("dggrid") is None, reason="dggrid binary not on PATH"),
]
# Boxes inside res-4 coarse cell 528 (verified fully covered by the reference).
BOXES = [(-52.2, -52.2, -52.0, -52.0), (-51.6, -51.4, -51.4, -51.2), (-52.8, -52.8, -52.6, -52.6)]


def _reference(b):
    pad = np.array(b) + [-0.02, -0.02, 0.02, 0.02]
    ref = pyogrio.read_dataframe(REF, bbox=tuple(pad))
    return ref[shapely.intersects(box(*b), ref.geometry.values)]


@pytest.mark.parametrize("b", BOXES)
def test_buffered_clip_reproduces_reference_ids_and_polygons(b):
    ref = _reference(b)
    ours = engine.polygons_for_extent(17, box(*b).buffer(0.01))
    ours = ours[shapely.intersects(box(*b), ours.geometry.values)]
    assert set(ours["global_id"]) == set(ref["global_id"].astype("int64"))
    merged = ours.merge(
        ref.assign(global_id=ref["global_id"].astype("int64")), on="global_id", suffixes=("", "_ref")
    )
    diff = shapely.symmetric_difference(merged.geometry.values, merged["geometry_ref"].values)
    assert shapely.area(diff).max() < 1e-12


def test_point_lookup_matches_reference_ids():
    ref = _reference(BOXES[0]).sample(n=300, random_state=0)
    pts = shapely.point_on_surface(ref.geometry.values)
    got = engine.cells_for_points(17, shapely.get_x(pts), shapely.get_y(pts))
    np.testing.assert_array_equal(got, ref["global_id"].astype("int64").to_numpy())


def test_closed_form_stats_match_engine_table():
    table = engine.stats_table(grid.MAX_LEVEL).set_index("Resolution")
    for lvl in grid.LEVELS:
        s = levels.level_stats(lvl)
        assert int(table.loc[lvl, "Cells"]) == s.cells
        assert float(table.loc[lvl, "Area (km^2)"]) == pytest.approx(s.area_km2, rel=1e-4)
        assert float(table.loc[lvl, "CLS (km)"]) == pytest.approx(s.cls_km, rel=1e-5)
