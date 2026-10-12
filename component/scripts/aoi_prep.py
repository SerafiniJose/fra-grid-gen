"""AoiResult -> AoiInfo: one valid WGS84 geometry plus what the UI and metadata need.

Solara-free. ``resolve_aoi_gdf``/``aoi_info_from_result`` do network I/O (FAO
WFS, Earth Engine) and use ``asyncio.run``: call them on a worker thread only.
"""

import hashlib
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import shapely
from pyproj import Geod
from shapely.geometry import MultiPoint

from component.parameter import grid as g
from component.scripts.levels import level_stats
from component.scripts.scratch import scratch_dir

ADMIN_METHODS = ("ADMIN0", "ADMIN1", "ADMIN2")
KM_PER_DEG = 111.32
_POINT, _POLYGON = 0, 3  # shapely type ids
_GEOD = Geod(ellps="WGS84")


class AoiError(ValueError):
    """An AOI the app cannot grid. ``key`` selects the UI message."""

    def __init__(self, key: str, detail: str = ""):
        super().__init__(detail or key)
        self.key = key
        self.detail = detail


@dataclass(frozen=True, eq=False)
class AoiInfo:
    geometry: object
    method: str
    label: str
    area_km2: float
    perimeter_km: dict
    bbox: tuple
    wkb_sha256: str
    n_points: int | None = None
    admin_code: str | None = None
    source: str | None = None

    @property
    def is_points(self) -> bool:
        return self.n_points is not None

    @property
    def slug(self) -> str:
        return slugify(self.label)


def slugify(text: str, max_len: int = 24) -> str:
    norm = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", norm.lower()).strip("_")[:max_len].strip("_")
    return slug or "aoi"


def default_grid_name(level: int, aoi_slug: str, when: date) -> str:
    return f"fra_isea3h_r{level}_{aoi_slug}_{when:%Y%m%d}"


def _parts(geoms):
    # make_valid can return collections holding multi-geometries: explode twice.
    return shapely.get_parts(shapely.get_parts(geoms))


def prepare_aoi(gdf, *, method: str, label: str, admin_code=None, source=None) -> AoiInfo:
    if gdf is None or len(gdf) == 0:
        raise AoiError("empty")
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")
    geoms = shapely.force_2d(gdf.geometry.dropna().to_numpy())
    geoms = geoms[~shapely.is_empty(geoms)]
    if geoms.size == 0:
        raise AoiError("empty")
    parts = _parts(shapely.make_valid(geoms))
    types = shapely.get_type_id(parts)

    n_points = None
    if method == "POINTS" and (types == _POINT).any():
        coords = np.unique(shapely.get_coordinates(parts[types == _POINT]), axis=0)
        geom = MultiPoint(coords)
        n_points = len(coords)
    else:
        polys = parts[types == _POLYGON]
        if polys.size == 0:
            raise AoiError("no_polygon")
        geom = shapely.make_valid(shapely.union_all(polys))

    minx, miny, maxx, maxy = geom.bounds
    if maxx - minx > 180.0:
        raise AoiError("antimeridian")

    if n_points is None:
        area_km2 = abs(_GEOD.geometry_area_perimeter(geom)[0]) / 1e6
        perimeter = {}
        for lvl in g.LEVELS:
            tol = level_stats(lvl).cls_km / 2.0 / KM_PER_DEG
            perimeter[lvl] = _GEOD.geometry_area_perimeter(geom.simplify(tol))[1] / 1000.0
    else:
        area_km2 = 0.0
        perimeter = {lvl: 0.0 for lvl in g.LEVELS}

    return AoiInfo(
        geometry=geom,
        method=method,
        label=label,
        area_km2=area_km2,
        perimeter_km=perimeter,
        bbox=(minx, miny, maxx, maxy),
        wkb_sha256=hashlib.sha256(shapely.to_wkb(geom)).hexdigest(),
        n_points=n_points,
        admin_code=admin_code,
        source=source,
    )


def aoi_label(result) -> tuple:
    """(label, source) for an AoiResult; ``source`` is a file path or asset id."""
    spec = getattr(result, "spec", None)
    method = result.method
    if method in ADMIN_METHODS:
        return (result.name or result.admin or method, None)
    if method in ("SHAPE", "POINTS"):
        path = getattr(spec, "pathname", None)
        return (Path(path).stem if path else (result.name or method), path)
    if method == "ASSET":
        asset_id = getattr(spec, "asset_id", None) or result.name
        return (asset_id.rsplit("/", 1)[-1] if asset_id else method, asset_id)
    if method == "DRAW":
        return ("Drawn polygon", None)
    return (result.name or method, None)


def _admin_gdf(method: str, admin_code: str):
    """GAUL boundary through pysepal's non-GEE WFS path (spatial_risk pattern)."""
    import asyncio

    from pysepal.solara.components.aoi import process_admin

    async def fetch():
        result = await process_admin(method, admin_code, gee=False)
        return await result.get_gdf_async()

    gdf = asyncio.run(fetch())
    if gdf is None:
        raise AoiError("fetch", f"no boundary for administrative area {admin_code}")
    return gdf


def _ee_to_geojson(obj, path: Path) -> None:
    """Export an EE object to a local GeoJSON (geometry only)."""
    import ee
    from pysepal.scripts import utils as su

    from component.scripts.vector_export import ee_export_vector

    su.init_ee()
    if isinstance(obj, ee.Geometry):
        obj = ee.FeatureCollection([ee.Feature(obj)])
    elif isinstance(obj, ee.Feature):
        obj = ee.FeatureCollection([obj])
    elif not isinstance(obj, ee.FeatureCollection):
        obj = ee.FeatureCollection(obj)
    ee_export_vector(obj, str(path), selectors=[], verbose=False)


def _feature_collection_gdf(fc):
    import geopandas as gpd

    path = scratch_dir() / f"aoi_export_{uuid.uuid4().hex}.geojson"
    try:
        _ee_to_geojson(fc, path)
        if not path.exists():
            raise AoiError("fetch", "the Earth Engine export produced no file")
        return gpd.read_file(path)
    finally:
        path.unlink(missing_ok=True)


def resolve_aoi_gdf(result):
    if getattr(result, "gdf", None) is not None:
        return result.gdf
    if result.method in ADMIN_METHODS and result.admin:
        return _admin_gdf(result.method, result.admin)
    if getattr(result, "feature_collection", None) is not None:
        return _feature_collection_gdf(result.feature_collection)
    raise AoiError("empty")


def aoi_info_from_result(result) -> AoiInfo:
    label, source = aoi_label(result)
    try:
        gdf = resolve_aoi_gdf(result)
    except AoiError:
        raise
    except Exception as exc:  # network / EE failures become a readable card
        raise AoiError("fetch", str(exc)) from exc
    return prepare_aoi(gdf, method=result.method, label=label, admin_code=result.admin, source=source)
