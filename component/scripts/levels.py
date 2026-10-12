"""ISEA3H level statistics (closed form) and per-AOI cell estimates.

cells(n) = 10*3^n + 2; mean area = 4*pi*R^2 / (10*3^n); characteristic length
scale CLS = 2R*acos(1 - A/(2*pi*R^2)) (the spherical-cap diameter of area A).
These reproduce DGGRID's grid_stats_table to its printed precision.
"""

import math
from dataclasses import dataclass

from component.parameter import grid as g

_R_KM = g.SPHERE_RADIUS_M / 1000.0
# GPKG bytes per cell, measured on r17 output (7 vertices, 6 attributes + rtree).
_BYTES_PER_CELL = 420


@dataclass(frozen=True)
class LevelStats:
    level: int
    cells: int
    area_km2: float
    cls_km: float

    @property
    def area_ha(self) -> float:
        return self.area_km2 * 100.0

    @property
    def spacing_m(self) -> float:
        return self.cls_km * 1000.0

    @property
    def cell_perimeter_km(self) -> float:
        """Perimeter of a regular hexagon with this cell's area."""
        side = math.sqrt(2.0 * self.area_km2 / (3.0 * math.sqrt(3.0)))
        return 6.0 * side

    @property
    def is_fra(self) -> bool:
        return self.level == g.FRA_LEVEL


@dataclass(frozen=True)
class LevelEstimate:
    stats: LevelStats
    cells: int
    verdict: str
    shp_allowed: bool


def level_stats(level: int) -> LevelStats:
    if level not in g.LEVELS:
        raise ValueError(f"level must be one of {g.LEVELS}, got {level}")
    n = 10 * 3**level
    area = 4.0 * math.pi * _R_KM**2 / n
    cls = 2.0 * _R_KM * math.acos(1.0 - area / (2.0 * math.pi * _R_KM**2))
    return LevelStats(level=level, cells=n + 2, area_km2=area, cls_km=cls)


def all_levels() -> list[LevelStats]:
    return [level_stats(lvl) for lvl in g.LEVELS]


def estimate_cells(level: int, area_km2: float, perimeter_km: float, n_points: int | None = None) -> int:
    """Expected number of cells touching the AOI.

    Kinematic (Steiner) formula for a region hit by a lattice of cells:
    (A + P * P_cell / 2pi) / A_cell, plus one. Points: at most one cell each.
    """
    if n_points is not None:
        return int(n_points)
    s = level_stats(level)
    touched = (area_km2 + perimeter_km * s.cell_perimeter_km / (2.0 * math.pi)) / s.area_km2
    return math.ceil(touched) + 1


def verdict(cells: int) -> str:
    if cells > g.BLOCK_CELLS:
        return "blocked"
    if cells >= g.WARN_CELLS:
        return "warn"
    return "ok"


def estimate_levels(area_km2: float, perimeter_km: dict, n_points: int | None) -> list[LevelEstimate]:
    rows = []
    for s in all_levels():
        cells = estimate_cells(s.level, area_km2, perimeter_km.get(s.level, 0.0), n_points)
        rows.append(
            LevelEstimate(stats=s, cells=cells, verdict=verdict(cells), shp_allowed=cells <= g.SHP_MAX_CELLS)
        )
    return rows


def estimated_size_bytes(cells: int) -> int:
    return int(cells) * _BYTES_PER_CELL
