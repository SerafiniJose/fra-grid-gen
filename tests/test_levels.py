import pytest

from component.parameter import grid
from component.scripts import levels

# DGGRID 8.44 grid_stats_table('ISEA3H', 21), rows 17-21.
DGGRID_TABLE = {
    17: (1_291_401_632, 0.394971, 0.709149),
    18: (3_874_204_892, 0.131657, 0.409427),
    19: (11_622_614_672, 0.043886, 0.236383),
    20: (34_867_844_012, 0.014628, 0.136476),
    21: (104_603_532_032, 0.004876, 0.078794),
}


@pytest.mark.parametrize("level", grid.LEVELS)
def test_closed_form_matches_dggrid_table(level):
    cells, area, cls = DGGRID_TABLE[level]
    s = levels.level_stats(level)
    assert s.cells == cells
    assert s.area_km2 == pytest.approx(area, rel=1e-4)
    assert s.cls_km == pytest.approx(cls, rel=1e-5)


def test_fra_level_flags_and_units():
    s = levels.level_stats(17)
    assert s.is_fra and not levels.level_stats(18).is_fra
    assert s.area_ha == pytest.approx(39.4971, rel=1e-5)
    assert s.spacing_m == pytest.approx(709.149, rel=1e-5)
    assert [x.level for x in levels.all_levels()] == list(grid.LEVELS)


def test_rejects_levels_outside_range():
    with pytest.raises(ValueError):
        levels.level_stats(16)
    with pytest.raises(ValueError):
        levels.level_stats(22)


def test_estimate_matches_chaco_reference():
    # R script's Chaco box: geodesic area 114.0647 km2, perimeter 42.7484 km.
    # Real counts (dggrid4py + correction): r17 = 330, r18 = 935.
    assert levels.estimate_cells(17, 114.0647, 42.7484) == 331
    assert levels.estimate_cells(18, 114.0647, 42.7484) == 938


def test_points_estimate_is_the_point_count():
    assert levels.estimate_cells(21, 0.0, 0.0, n_points=42) == 42


@pytest.mark.parametrize(
    "cells,expected",
    [(0, "ok"), (1_999_999, "ok"), (2_000_000, "warn"), (10_000_000, "warn"), (10_000_001, "blocked")],
)
def test_verdict_thresholds(cells, expected):
    assert levels.verdict(cells) == expected


def test_estimate_levels_rows_and_shp_limit():
    perims = {lvl: 400.0 for lvl in grid.LEVELS}
    rows = levels.estimate_levels(52_410.0, perims, None)
    assert [r.stats.level for r in rows] == list(grid.LEVELS)
    by = {r.stats.level: r for r in rows}
    assert by[17].verdict == "ok" and by[17].shp_allowed
    assert by[20].verdict == "warn" and by[20].shp_allowed  # ~3.6M > 2M warn; <= 4M so SHP allowed
    assert by[21].verdict == "blocked"


def test_estimated_size_is_positive_and_monotonic():
    assert 0 < levels.estimated_size_bytes(1_000) < levels.estimated_size_bytes(1_000_000)
