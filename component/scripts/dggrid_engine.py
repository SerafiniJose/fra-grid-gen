"""The only module that imports dggrid4py (AGPL-3.0; spec §12 open item).

``DGGRIDv8.run()`` calls ``os.chdir`` on the whole process, so every call is
serialised behind ``_LOCK`` and every path handed to it is absolute. Ids come
back as strings in a ``name`` column; they are returned as int64 ``global_id``.
"""

import importlib.metadata
import json
import os
import shutil
import threading
from pathlib import Path

import geopandas as gpd
import numpy as np

from component.parameter.grid import DGGS_TYPE
from component.scripts.scratch import local_scratch_dir

_LOCK = threading.Lock()
_ENGINE = None
_ENGINE_KEY = None  # (executable, workdir) the cached engine was built for


class EngineUnavailable(RuntimeError):
    """The dggrid binary cannot be found or started."""


def dggrid_executable() -> str:
    """Absolute path of the dggrid binary (``$FRA_GRID_DGGRID`` overrides PATH)."""
    candidate = os.environ.get("FRA_GRID_DGGRID") or shutil.which("dggrid")
    if not candidate or not Path(candidate).is_file() or not os.access(candidate, os.X_OK):
        raise EngineUnavailable("DGGRID binary not found")
    return str(Path(candidate).absolute())


def _engine():
    """The dggrid4py engine, rebuilt when the binary or the scratch dir changes.

    Called with ``_LOCK`` held. The work dir is re-created on every call: a
    cleaned ``/var/tmp`` (or a test's tmp_path) must not break the next run.
    """
    global _ENGINE, _ENGINE_KEY
    from dggrid4py import DGGRIDv8

    workdir = local_scratch_dir() / "dggrid"
    workdir.mkdir(parents=True, exist_ok=True)
    key = (dggrid_executable(), str(workdir))
    if _ENGINE is None or _ENGINE_KEY != key:
        _ENGINE = DGGRIDv8(executable=key[0], working_dir=key[1], capture_logs=False, silent=True)
        _ENGINE_KEY = key
    return _ENGINE


def _empty_cells() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"global_id": np.array([], dtype="int64")}, geometry=gpd.GeoSeries([], crs="EPSG:4326"), crs="EPSG:4326"
    )


def polygons_for_extent(level: int, clip_geom) -> gpd.GeoDataFrame:
    """Cells whose polygons DGGRID's GDAL clip returns for ``clip_geom`` (sphere space).

    DGGRID's clip misses edge cells: callers pass a geometry buffered by about
    one cell and apply their own intersects filter.
    """
    with _LOCK:
        gdf = _engine().grid_cell_polygons_for_extent(DGGS_TYPE, int(level), clip_geom=clip_geom)
    if gdf is None or len(gdf) == 0:
        return _empty_cells()
    return gpd.GeoDataFrame(
        {"global_id": gdf["name"].astype("int64").to_numpy()},
        geometry=gdf.geometry.to_numpy(),
        crs="EPSG:4326",
    )


def cells_for_points(level: int, lon, lat) -> np.ndarray:
    """SEQNUM of the cell containing each point, in input order."""
    lon = np.asarray(lon, dtype="float64")
    lat = np.asarray(lat, dtype="float64")
    if lon.size == 0:
        return np.array([], dtype="int64")
    lon = ((lon + 180.0) % 360.0) - 180.0
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(lon, lat), crs="EPSG:4326")
    with _LOCK:
        out = _engine().cells_for_geo_points(pts, True, DGGS_TYPE, int(level))
    return out["name"].astype("int64").to_numpy()


def stats_table(max_level: int):
    with _LOCK:
        return _engine().grid_stats_table(DGGS_TYPE, int(max_level))


def _dggrid_version(executable: str) -> str:
    prefix = Path(executable).resolve().parent.parent
    for meta in sorted((prefix / "conda-meta").glob("dggrid-[0-9]*.json")):
        try:
            return str(json.loads(meta.read_text())["version"])
        except (OSError, ValueError, KeyError):
            continue
    return "unknown"


def versions() -> dict:
    try:
        dggrid = _dggrid_version(dggrid_executable())
    except EngineUnavailable:
        dggrid = "missing"
    return {"dggrid": dggrid, "dggrid4py": importlib.metadata.version("dggrid4py")}
