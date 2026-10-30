"""Generate one FRA grid: tiles -> DGGRID -> FRA correction -> filter -> files.

Solara-free. Progress goes out as INFO lines on the ``fra_grid`` logger (task
milestones through notify_bridge), through ``on_progress(done, total,
cells)`` and through ``on_step(step, fraction)`` (cells, shp, preview, finish;
fraction 0..1, or None for a step that cannot measure itself).
``cancel.is_set()`` is checked between tiles; a dggrid call already running
finishes first.

Tiling: WGS84 tiles aligned to multiples of ``TILE_DEG[level]``. A tile owns
the cells whose corrected centroid falls in its half-open box, so a cell
returned by two neighbouring clips is written exactly once. Each clip is the
search region (AOI simplified by a quarter cell, buffered by one cell spacing
plus the inverse-correction margin) cut to the buffered tile and moved into
sphere space: DGGRID's GDAL clip misses edge cells without that buffer.

After the GPKG is complete a PMTiles map preview (``g.PREVIEW_FILE``, hidden,
not a deliverable) is built from it; a missing or failing tippecanoe only
skips the preview (WARNING), it never fails the grid.
"""

import asyncio
import logging
import math
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
from pyproj import Geod
from shapely.geometry import box

from component.parameter import grid as g
from component.parameter.directory import results_dir
from component.scripts import dggrid_engine as engine
from component.scripts import metadata as md
from component.scripts import outputs_index as oi
from component.scripts import pmtiles_preview as pp
from component.scripts.fra_correction import correct_geometries, to_sphere_geometry, unwrap_antimeridian
from component.scripts.levels import level_stats
from component.scripts.scratch import local_scratch_dir
from component.scripts.writers import append_cells, gpkg_to_shp, human_size, write_aoi_geojson

logger = logging.getLogger(g.LOGGER_NAME)

_GEOD = Geod(ellps="WGS84")
FORMATS = ("gpkg", "shp")


class BuildCancelled(asyncio.CancelledError):
    """User cancel. A CancelledError so pysepal marks the task cancelled, not failed."""


class EmptyGridError(RuntimeError):
    """The AOI produced no cells."""


@dataclass(frozen=True)
class BuildRequest:
    aoi: object
    level: int
    name: str
    formats: tuple = ("gpkg",)
    overwrite: bool = False
    centroids: bool = False


@dataclass(frozen=True)
class BuildResult:
    name: str
    folder: Path
    files: tuple
    cell_count: int
    n_tiles: int
    duration_s: float
    metadata: dict


def columns(level: int) -> list:
    parent = ["fra_r17_id"] if level > g.FRA_LEVEL else []
    return ["global_id", *parent, "level", "lon", "lat", "area_ha", "geometry"]


def _empty_frame(level: int) -> gpd.GeoDataFrame:
    data = {"global_id": np.array([], dtype="int64")}
    if level > g.FRA_LEVEL:
        data["fra_r17_id"] = np.array([], dtype="int64")
    data["level"] = np.array([], dtype="int16")
    for col in ("lon", "lat", "area_ha"):
        data[col] = np.array([], dtype="float64")
    return gpd.GeoDataFrame(data, geometry=gpd.GeoSeries([], crs="EPSG:4326"), crs="EPSG:4326")


def clip_buffer_deg(level: int, max_abs_lat: float) -> float:
    """One cell spacing in degrees of longitude at ``max_abs_lat``, plus margin."""
    cls_deg = level_stats(level).cls_km / g.KM_PER_DEG
    cos = max(math.cos(math.radians(min(abs(max_abs_lat), 89.0))), 0.05)
    return cls_deg / cos + g.CLIP_EXTRA_DEG


def search_region(aoi, level: int, buffer_deg: float):
    geom = aoi.geometry
    if not aoi.is_points:
        geom = geom.simplify(level_stats(level).cls_km / g.KM_PER_DEG / 4.0)
    region = geom.buffer(buffer_deg)
    shapely.prepare(region)
    return region


def plan_tiles(region, tile_deg: float) -> list:
    minx, miny, maxx, maxy = region.bounds
    miny, maxy = max(miny, -90.0), min(maxy, 90.0)
    x0 = math.floor(minx / tile_deg) * tile_deg
    y0 = math.floor(miny / tile_deg) * tile_deg
    tiles = np.array(
        [
            box(x, y, x + tile_deg, min(y + tile_deg, 90.0))
            for y in np.arange(y0, maxy, tile_deg)
            for x in np.arange(x0, maxx, tile_deg)
        ],
        dtype=object,
    )
    if tiles.size == 0:
        return []
    return list(tiles[shapely.intersects(region, tiles)])


def owned(cx, cy, bounds) -> np.ndarray:
    x0, y0, x1, y1 = bounds
    in_y = (cy >= y0) & ((cy < y1) | ((y1 >= 90.0) & (cy <= y1)))
    return (cx >= x0) & (cx < x1) & in_y


def _geodesic_area_ha(geoms) -> np.ndarray:
    """Geodesic area (WGS84 ellipsoid) in hectares, rounded to 3 dp, one value per polygon."""
    area = np.fromiter(
        (abs(_GEOD.geometry_area_perimeter(p)[0]) for p in geoms), dtype="float64", count=len(geoms)
    )
    return np.round(area / 1e4, 3)


def centroid_squares(lon, lat) -> np.ndarray:
    """North-up squares of g.CENTROID_SIDE_M sides on the WGS84 ellipsoid, centred on lon/lat."""
    lon, lat = np.asarray(lon, dtype="float64"), np.asarray(lat, dtype="float64")
    half = np.full(lon.shape, g.CENTROID_SIDE_M / 2.0)
    _, north, _ = _GEOD.fwd(lon, lat, np.zeros_like(half), half)
    _, south, _ = _GEOD.fwd(lon, lat, np.full_like(half, 180.0), half)
    east, _, _ = _GEOD.fwd(lon, lat, np.full_like(half, 90.0), half)
    dlon = (east - lon + 180.0) % 360.0 - 180.0  # fwd wraps east past +-180
    return shapely.box(lon - dlon, south, lon + dlon, north)


def centroid_frame(cells: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """The cells' attributes (no area_ha) with their 1 ha centroid square as geometry."""
    squares = centroid_squares(cells["lon"].to_numpy(), cells["lat"].to_numpy())
    return gpd.GeoDataFrame(cells.drop(columns=["area_ha", "geometry"]), geometry=squares, crs="EPSG:4326")


def build_tile(aoi_geom, region, level: int, tile, buffer_deg: float) -> gpd.GeoDataFrame:
    """Cells that touch the AOI and whose corrected centroid lies in ``tile``."""
    x0, y0, x1, y1 = tile.bounds
    clip = shapely.clip_by_rect(region, x0 - buffer_deg, y0 - buffer_deg, x1 + buffer_deg, y1 + buffer_deg)
    if clip.is_empty:
        return _empty_frame(level)
    raw = engine.polygons_for_extent(level, to_sphere_geometry(clip))
    if raw.empty:
        return _empty_frame(level)

    sphere = unwrap_antimeridian(raw.geometry.to_numpy())
    geoms = correct_geometries(sphere)
    centroids = shapely.centroid(geoms)
    cx, cy = shapely.get_x(centroids), shapely.get_y(centroids)
    keep = owned(cx, cy, tile.bounds)
    keep[keep] = shapely.intersects(aoi_geom, geoms[keep])
    if not keep.any():
        return _empty_frame(level)

    n = int(keep.sum())
    data = {"global_id": raw["global_id"].to_numpy()[keep]}
    if level > g.FRA_LEVEL:
        sphere_centroids = shapely.centroid(sphere[keep])
        data["fra_r17_id"] = engine.cells_for_points(
            g.FRA_LEVEL, shapely.get_x(sphere_centroids), shapely.get_y(sphere_centroids)
        )
    data["level"] = np.full(n, level, dtype="int16")
    data["lon"] = np.round(cx[keep], 6)
    data["lat"] = np.round(cy[keep], 6)
    frame = gpd.GeoDataFrame(data, geometry=geoms[keep], crs="EPSG:4326")
    frame["area_ha"] = _geodesic_area_ha(geoms[keep])
    return frame[columns(level)]


def _validate(request: BuildRequest, root: Path) -> None:
    err = oi.validate_grid_name(request.name)
    if err is not None:
        raise ValueError(f"invalid grid name ({err}): {request.name!r}")
    if request.level not in g.LEVELS:
        raise ValueError(f"level must be one of {g.LEVELS}")
    formats = set(request.formats)
    if not formats or not formats <= set(FORMATS):
        raise ValueError(f"formats must be a non-empty subset of {FORMATS}")
    if request.centroids and request.level not in g.CENTROID_LEVELS:
        raise ValueError(f"Centroids need one of the levels {g.CENTROID_LEVELS}")
    status = oi.name_status(root, request.name)
    if status == "taken":
        raise oi.NotAGridFolder(str(root / request.name))
    if status == "grid" and not request.overwrite:
        raise FileExistsError(str(root / request.name))


def _no_step(step, fraction) -> None:
    pass


def _check(cancel) -> None:
    if cancel is not None and cancel.is_set():
        raise BuildCancelled()


def _build_preview(gpkg_tmp, name: str, level: int, part: Path, work: Path, cancel, on_step, centroids_layer=None):
    """Build ``part/g.PREVIEW_FILE``; its metadata entry, or None when skipped."""
    minzoom, maxzoom = g.PREVIEW_ZOOMS[level]
    target = part / g.PREVIEW_FILE
    logger.info("Building map preview")
    on_step("preview", 0.0)
    try:
        built = pp.build_preview(gpkg_tmp, name, work / g.PREVIEW_FILE, minzoom=minzoom, maxzoom=maxzoom,
                                 tmp_dir=work, cancel=cancel,
                                 on_progress=lambda pct: on_step("preview", min(pct / 100.0, 1.0)),
                                 centroids_layer=centroids_layer)
        size = built.stat().st_size
        shutil.move(str(built), str(target))
    except pp.PreviewCancelled:
        raise BuildCancelled() from None
    except Exception as exc:  # the preview is optional: keep the grid
        logger.warning("Map preview skipped: %s", exc)
        target.unlink(missing_ok=True)
        return None
    logger.info("Map preview ready (%s)", human_size(size))
    return {"file": g.PREVIEW_FILE, "minzoom": minzoom, "maxzoom": maxzoom}


def _build_into(request, part: Path, work: Path, t0: float, on_progress, cancel, now, on_step):
    aoi, level, name = request.aoi, request.level, request.name
    on_step("cells", 0.0)
    logger.info("Preparing AOI")
    buf = clip_buffer_deg(level, max(abs(aoi.bbox[1]), abs(aoi.bbox[3])))
    region = search_region(aoi, level, buf)
    aoi_geom = aoi.geometry
    shapely.prepare(aoi_geom)
    tiles = plan_tiles(region, g.TILE_DEG[level])

    gpkg_tmp = work / f"{name}.gpkg"
    centroids_layer = f"{name}{g.CENTROIDS_SUFFIX}"
    total = 0
    for i, tile in enumerate(tiles, start=1):
        _check(cancel)
        cells = build_tile(aoi_geom, region, level, tile, buf)
        if len(cells):
            append_cells(cells, gpkg_tmp, name, first=total == 0)
            if request.centroids:
                append_cells(centroid_frame(cells), gpkg_tmp, centroids_layer, first=total == 0)
            total += len(cells)
        logger.info("Tile %d/%d: %s cells", i, len(tiles), f"{total:,}")
        if on_progress is not None:
            on_progress(i, len(tiles), total)
        on_step("cells", i / len(tiles))
    _check(cancel)
    if total == 0:
        raise EmptyGridError("No cells were generated: check the AOI.")

    files = []
    keep_gpkg = "gpkg" in request.formats
    if keep_gpkg:
        files.append(f"{name}.gpkg")
    if "shp" in request.formats:
        on_step("shp", None)
        logger.info("Converting to Shapefile")
        files += [p.name for p in gpkg_to_shp(gpkg_tmp, part / f"{name}.shp", name)]
        if request.centroids:
            files += [p.name for p in gpkg_to_shp(gpkg_tmp, part / f"{centroids_layer}.shp", centroids_layer)]
    write_aoi_geojson(aoi.geometry, part / md.AOI_FILE)
    files += [md.AOI_FILE, md.METADATA_FILE]
    preview = _build_preview(gpkg_tmp, name, level, part, work, cancel, on_step,
                             centroids_layer if request.centroids else None)
    _check(cancel)
    on_step("finish", None)

    logger.info("Writing metadata")
    record = md.build_record(
        name=name, aoi=aoi, level=level, formats=request.formats, files=files, cell_count=total,
        n_tiles=len(tiles), tile_deg=g.TILE_DEG[level], clip_buffer_deg=buf,
        duration_s=time.monotonic() - t0, versions=engine.versions(), generated_at=now, preview=preview,
        centroids_layer=centroids_layer if request.centroids else None,
    )
    if keep_gpkg:
        md.embed_in_gpkg(gpkg_tmp, name, record)
        logger.info("Writing GeoPackage")
        shutil.move(str(gpkg_tmp), str(part / f"{name}.gpkg"))
    md.write_metadata_json(record, part)
    return record, files, len(tiles), total


def build_grid(request: BuildRequest, *, results_root=None, on_progress=None, on_step=None, cancel=None,
               now=None) -> BuildResult:
    t0 = time.monotonic()
    if on_step is None:
        on_step = _no_step
    root = Path(results_root) if results_root is not None else results_dir()
    _validate(request, root)
    part = oi.new_part_folder(root, request.name)  # this run's own: never shared with another session
    work = None
    try:
        work = Path(tempfile.mkdtemp(prefix=f"{request.name}-", dir=local_scratch_dir()))
        record, files, n_tiles, total = _build_into(request, part, work, t0, on_progress, cancel, now, on_step)
        _check(cancel)
        folder = oi.commit_part(root, request.name, part, overwrite=request.overwrite)
    except BaseException:
        shutil.rmtree(part, ignore_errors=True)
        raise
    finally:
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)
    logger.info("Grid ready: %s cells", f"{total:,}")
    return BuildResult(
        name=request.name, folder=folder, files=tuple(folder / f for f in files), cell_count=total,
        n_tiles=n_tiles, duration_s=record["run"]["duration_s"], metadata=record,
    )
