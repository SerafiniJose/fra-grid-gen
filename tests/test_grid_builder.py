import json
import shutil
import threading
import time
from datetime import datetime, timezone

import geopandas as gpd
import numpy as np
import pyogrio
import pytest
import shapely
from shapely.geometry import MultiPoint, Point, box

from component.parameter import grid
from component.scripts import dggrid_engine as engine
from component.scripts import grid_builder as gb
from component.scripts import metadata as md
from component.scripts import outputs_index as oi
from component.scripts import pmtiles_preview as pp
from component.scripts.aoi_prep import prepare_aoi
from component.scripts.fra_correction import correct_geometries, to_sphere_geometry, unwrap_antimeridian
from _fakes import read_gpkg_metadata

needs_engine = pytest.mark.skipif(shutil.which("dggrid") is None, reason="dggrid binary not on PATH")
needs_tippecanoe = pytest.mark.skipif(pp.resolve_tippecanoe() is None, reason="tippecanoe not available")
PREVIEW = [".preview.pmtiles"] if pp.resolve_tippecanoe() else []
CHACO = (-60.10, -22.40, -60.00, -22.30)


def _aoi(geom, method="DRAW"):
    return prepare_aoi(gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326"), method=method, label="t")


def _direct_ids(aoi_geom, level, pad=0.05):
    """Independent reference: one wide clip, no tiling, same correction + intersects."""
    raw = engine.polygons_for_extent(level, to_sphere_geometry(aoi_geom.buffer(pad)))
    geoms = correct_geometries(unwrap_antimeridian(raw.geometry.to_numpy()))
    return set(raw["global_id"].to_numpy()[shapely.intersects(aoi_geom, geoms)])


# ---- pure helpers (no engine) -------------------------------------------------


def test_clip_buffer_grows_with_latitude_and_shrinks_with_level():
    assert gb.clip_buffer_deg(17, 60) > gb.clip_buffer_deg(17, 0)
    assert gb.clip_buffer_deg(21, 0) < gb.clip_buffer_deg(17, 0)
    assert gb.clip_buffer_deg(17, 90) < 1.0  # capped, finite at the pole


def test_plan_tiles_are_aligned_and_intersect_region():
    region = box(-60.13, -22.43, -59.97, -22.27)
    tiles = gb.plan_tiles(region, 1.0)
    assert [t.bounds for t in tiles] == [(-61.0, -23.0, -60.0, -22.0), (-60.0, -23.0, -59.0, -22.0)]
    quarter = gb.plan_tiles(region, 0.25)
    assert all(b % 0.25 == 0 for t in quarter for b in t.bounds)


def test_owned_is_half_open_so_each_point_has_one_owner():
    cx = np.array([-60.0, -60.0, -59.5])
    cy = np.array([-22.5, -22.0, -23.0])
    west = gb.owned(cx, cy, (-61.0, -23.0, -60.0, -22.0))
    east = gb.owned(cx, cy, (-60.0, -23.0, -59.0, -22.0))
    assert list(west) == [False, False, False]
    assert list(east) == [True, False, True]
    assert gb.owned(np.array([0.0]), np.array([90.0]), (0.0, 89.0, 1.0, 90.0))[0]  # top row closed


def test_columns_by_level():
    assert gb.columns(17) == ["global_id", "level", "lon", "lat", "area_ha", "geometry"]
    assert gb.columns(18)[:2] == ["global_id", "fra_r17_id"]


def test_complex_aoi_plans_quickly():
    aoi = _aoi(Point(-60.0, -22.0).buffer(2.0, quad_segs=15_000), method="ADMIN1")  # 60k vertices
    t0 = time.perf_counter()
    buf = gb.clip_buffer_deg(17, 24.0)
    region = gb.search_region(aoi, 17, buf)
    tiles = gb.plan_tiles(region, 1.0)
    clips = [shapely.clip_by_rect(region, *t.buffer(buf, join_style="mitre").bounds) for t in tiles]
    assert time.perf_counter() - t0 < 3.0
    assert 16 <= len(tiles) <= 25
    assert max(shapely.get_num_coordinates(c) for c in clips) < 5_000


def test_invalid_requests_fail_before_any_work(results_root, chaco_aoi):
    with pytest.raises(ValueError):
        gb.build_grid(gb.BuildRequest(chaco_aoi, 17, "../evil"))
    with pytest.raises(ValueError):
        gb.build_grid(gb.BuildRequest(chaco_aoi, 16, "ok"))
    with pytest.raises(ValueError):
        gb.build_grid(gb.BuildRequest(chaco_aoi, 17, "ok", formats=()))
    assert list(results_root.iterdir()) == []


def test_existing_non_grid_folder_is_never_replaced(results_root, chaco_aoi):
    (results_root / "g").mkdir()
    (results_root / "g" / "precious.txt").write_text("keep")
    with pytest.raises(oi.NotAGridFolder):
        gb.build_grid(gb.BuildRequest(chaco_aoi, 17, "g", overwrite=True))
    assert (results_root / "g" / "precious.txt").read_text() == "keep"
    assert sorted(p.name for p in results_root.iterdir()) == ["g"]


def test_tile_log_lines_are_capped_at_about_twenty(results_root, chaco_aoi, monkeypatch, caplog):
    # Each line becomes a notification milestone that is re-sent in full: never one per tile.
    monkeypatch.setattr(gb, "plan_tiles", lambda region, tile_deg: [box(0, 0, 1, 1)] * 1000)
    monkeypatch.setattr(gb, "build_tile", lambda *a: gb._empty_frame(17))
    seen = []
    with caplog.at_level("INFO", logger="fra_grid"), pytest.raises(gb.EmptyGridError):
        gb.build_grid(gb.BuildRequest(chaco_aoi, 17, "many"), on_progress=lambda d, t, c: seen.append(d))
    tile_lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Tile ")]
    assert len(tile_lines) == 20 and tile_lines[-1].startswith("Tile 1000/1000")
    assert seen == list(range(1, 1001))  # the progress bar still moves on every tile


def test_concurrent_same_name_builds_stage_in_their_own_part_folders(results_root, chaco_aoi, monkeypatch):
    both_staging = threading.Barrier(2, timeout=5)
    parts, errors = [], []

    class Stop(RuntimeError):
        pass

    def fake_build_into(request, part, work, t0, on_progress, cancel, now):
        parts.append(part)
        both_staging.wait()  # both runs are staging at the same time
        assert all(p.is_dir() for p in parts)
        both_staging.wait()  # neither cleans up before the other has checked
        raise Stop()

    def run():
        try:
            gb.build_grid(gb.BuildRequest(chaco_aoi, 17, "same"))
        except Stop:
            pass
        except BaseException as exc:  # surfaced below
            errors.append(exc)

    monkeypatch.setattr(gb, "_build_into", fake_build_into)
    threads = [threading.Thread(target=run) for _ in range(2)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(10)
    assert errors == []
    assert len(set(parts)) == 2
    assert all(p.parent == results_root and p.name.startswith(".same.") for p in parts)
    assert list(results_root.iterdir()) == []


# ---- engine-backed -------------------------------------------------------------


@needs_engine
def test_chaco_r17_end_to_end(results_root, chaco_aoi, tmp_path):
    progress = []
    res = gb.build_grid(
        gb.BuildRequest(chaco_aoi, 17, "chaco17", formats=("gpkg", "shp")),
        on_progress=lambda d, t, c: progress.append((d, t, c)),
    )
    folder = results_root / "chaco17"
    assert res.folder == folder and res.n_tiles == 2
    assert res.cell_count == 330  # verified while planning (R-equivalent pipeline)
    assert progress[-1] == (2, 2, 330)
    assert sorted(p.name for p in folder.iterdir()) == sorted(
        ["chaco17.gpkg", "chaco17.shp", "chaco17.shx", "chaco17.dbf", "chaco17.prj", "chaco17.cpg",
         "metadata.json", "aoi.geojson", *PREVIEW]
    )
    assert [p.name for p in results_root.iterdir()] == ["chaco17"]  # no .part left
    assert [p.name for p in (tmp_path / "local").iterdir()] == ["dggrid"]  # work dir removed

    cells = pyogrio.read_dataframe(folder / "chaco17.gpkg", layer="chaco17")
    assert list(cells.columns) == gb.columns(17)
    assert cells["global_id"].dtype == np.int64 and cells["global_id"].is_unique
    assert (cells["level"] == 17).all()
    assert shapely.intersects(box(*CHACO), cells.geometry.values).all()
    assert shapely.contains(cells.geometry.values, shapely.points(cells["lon"], cells["lat"])).all()
    assert cells["area_ha"].between(38.5, 40.5).all()
    assert set(cells["global_id"]) == _direct_ids(box(*CHACO), 17)

    record = md.read_metadata_json(folder)
    assert record["run"]["cell_count"] == 330 and record["dggs"]["resolution"] == 17
    assert read_gpkg_metadata(folder / "chaco17.gpkg", "chaco17") == record
    shp = pyogrio.read_dataframe(folder / "chaco17.shp")
    assert len(shp) == 330
    assert record["centroids"] is None


@needs_engine
def test_centroids_layer_holds_one_ha_square_per_cell(results_root, chaco_aoi):
    res = gb.build_grid(gb.BuildRequest(chaco_aoi, 17, "c17", formats=("gpkg", "shp"), centroids=True))
    cells = pyogrio.read_dataframe(res.folder / "c17.gpkg", layer="c17")
    centroids = pyogrio.read_dataframe(res.folder / "c17.gpkg", layer="c17_centroids")
    assert list(centroids["global_id"]) == list(cells["global_id"]) and "area_ha" not in centroids
    assert shapely.contains(cells.geometry.values, centroids.geometry.values).all()
    assert np.allclose(gb._geodesic_area_ha(centroids.geometry.values), 1.0, atol=0.001)
    assert len(pyogrio.read_dataframe(res.folder / "c17_centroids.shp")) == 330
    assert md.read_metadata_json(res.folder)["centroids"] == {"layer": "c17_centroids", "side_m": 100.0}


@needs_engine
def test_centroids_are_fed_to_the_map_preview(results_root, chaco_aoi, monkeypatch):
    seen = {}

    def fake(gpkg, layer, out, **k):
        seen.update(layer=layer, centroids_layer=k.get("centroids_layer"))
        raise pp.PreviewFailed("stop here")

    monkeypatch.setattr(pp, "build_preview", fake)
    gb.build_grid(gb.BuildRequest(chaco_aoi, 17, "pl", centroids=True))
    assert seen == {"layer": "pl", "centroids_layer": "pl_centroids"}
    gb.build_grid(gb.BuildRequest(chaco_aoi, 17, "np"))
    assert seen["centroids_layer"] is None


def test_centroid_squares_are_one_ha_and_cross_the_antimeridian():
    squares = gb.centroid_squares([0.0, 179.9999, -60.0], [0.0, 70.0, -22.3])
    assert np.allclose(gb._geodesic_area_ha(squares), 1.0, atol=0.001)
    assert shapely.bounds(squares[1])[2] > 180.0  # one square, not one spanning the globe


def test_centroids_rejected_on_levels_too_fine(results_root, chaco_aoi):
    with pytest.raises(ValueError, match="Centroids need"):
        gb.build_grid(gb.BuildRequest(chaco_aoi, 20, "fine", centroids=True))


@needs_engine
def test_r18_links_cells_to_fra_r17(results_root, chaco_aoi):
    res = gb.build_grid(gb.BuildRequest(chaco_aoi, 18, "chaco18"))
    cells = pyogrio.read_dataframe(res.folder / "chaco18.gpkg", layer="chaco18")
    assert res.cell_count == len(cells) == 935
    assert cells["fra_r17_id"].dtype == np.int64
    assert set(cells["fra_r17_id"]) <= _direct_ids(box(*CHACO).buffer(0.02), 17)
    assert sorted(p.name for p in res.folder.iterdir()) == sorted(
        ["aoi.geojson", "chaco18.gpkg", "metadata.json", *PREVIEW]
    )


@needs_engine
def test_points_aoi_keeps_cells_containing_points(results_root):
    pts = MultiPoint([(-60.05, -22.35), (-60.0501, -22.3501), (-60.02, -22.31), (-60.09, -22.39)])
    aoi = prepare_aoi(gpd.GeoDataFrame(geometry=[pts], crs="EPSG:4326"), method="POINTS", label="pts")
    res = gb.build_grid(gb.BuildRequest(aoi, 17, "pts"))
    cells = pyogrio.read_dataframe(res.folder / "pts.gpkg", layer="pts")
    assert cells["global_id"].is_unique and 1 <= len(cells) <= 4
    for p in pts.geoms:
        assert shapely.intersects(cells.geometry.values, p).sum() >= 1


@needs_engine
@pytest.mark.parametrize("level", [17, 21])
def test_points_lookup_matches_the_tile_clip_even_on_edges_and_corners(results_root, monkeypatch, level):
    # The tile path (one clip per tile) is the reference; points on a corrected cell's
    # corners and edge midpoints are the cases the 1 m ring exists for.
    rng = np.random.default_rng(3)
    edge = correct_geometries(engine.polygons_for_extent(level, box(-50, 10, -49.98, 10.02)).geometry.to_numpy()[:3])
    xy = shapely.get_coordinates(edge)
    pts = np.r_[np.c_[rng.uniform(-60, -40, 40), rng.uniform(-70, 70, 40)], xy, (xy[:-1] + xy[1:]) / 2]
    aoi = prepare_aoi(gpd.GeoDataFrame(geometry=gpd.points_from_xy(*pts.T), crs="EPSG:4326"),
                      method="POINTS", label="p")
    shapely.prepare(aoi.geometry)
    buf = gb.clip_buffer_deg(level, 70.0)
    region = gb.search_region(aoi, level, buf)
    tiled = {i for t in gb.plan_tiles(region, grid.TILE_DEG[level])
             for i in gb.build_tile(aoi.geometry, region, level, t, buf)["global_id"]}
    monkeypatch.setattr(gb, "POINT_BATCH", 7)  # many batches: a cell is still written once
    res = gb.build_grid(gb.BuildRequest(aoi, level, "pts"))
    cells = pyogrio.read_dataframe(res.folder / "pts.gpkg", layer="pts")
    assert cells["global_id"].is_unique and set(cells["global_id"]) == tiled
    assert res.metadata["run"]["n_tiles"] == -(-aoi.n_points // 7) and res.metadata["run"]["tile_deg"] is None


@needs_engine
def test_high_latitude_matches_wide_clip(results_root):
    aoi = _aoi(box(15.0, 78.0, 15.2, 78.05))  # Svalbard
    res = gb.build_grid(gb.BuildRequest(aoi, 17, "svalbard"))
    cells = pyogrio.read_dataframe(res.folder / "svalbard.gpkg", layer="svalbard")
    assert cells["global_id"].is_unique
    assert shapely.intersects(aoi.geometry, cells.geometry.values).all()
    assert set(cells["global_id"]) == _direct_ids(aoi.geometry, 17, pad=0.2)


@needs_engine
def test_cancel_before_start_leaves_nothing(results_root, chaco_aoi, tmp_path):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(gb.BuildCancelled):
        gb.build_grid(gb.BuildRequest(chaco_aoi, 17, "c"), cancel=cancel)
    assert list(results_root.iterdir()) == []
    assert [p.name for p in (tmp_path / "local").iterdir()] in ([], ["dggrid"])


@needs_engine
def test_cancel_mid_run_leaves_nothing(results_root):
    aoi = _aoi(box(-60.5, -22.4, -58.5, -22.3))  # 3 tiles at r17
    cancel = threading.Event()

    def stop_after_first(done, total, cells):
        if done == 1:
            cancel.set()

    with pytest.raises(gb.BuildCancelled):
        gb.build_grid(gb.BuildRequest(aoi, 17, "c"), on_progress=stop_after_first, cancel=cancel)
    assert list(results_root.iterdir()) == []


@needs_engine
def test_overwrite_requires_flag_and_replaces_atomically(results_root, chaco_aoi):
    first = datetime(2026, 1, 1, tzinfo=timezone.utc)
    gb.build_grid(gb.BuildRequest(chaco_aoi, 17, "g"), now=first)
    with pytest.raises(FileExistsError):
        gb.build_grid(gb.BuildRequest(chaco_aoi, 17, "g"))
    gb.build_grid(gb.BuildRequest(chaco_aoi, 17, "g", overwrite=True))
    record = json.loads((results_root / "g" / "metadata.json").read_text())
    assert record["generated_at"] != "2026-01-01T00:00:00Z"
    assert sorted(p.name for p in results_root.iterdir()) == ["g"]


@needs_engine
def test_write_failure_cleans_part_folder(results_root, chaco_aoi, monkeypatch):
    def boom(*a, **k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(gb, "write_aoi_geojson", boom)
    with pytest.raises(OSError):
        gb.build_grid(gb.BuildRequest(chaco_aoi, 17, "full"))
    assert list(results_root.iterdir()) == []


@needs_engine
def test_gpkg_unticked_keeps_only_shapefile(results_root, chaco_aoi):
    res = gb.build_grid(gb.BuildRequest(chaco_aoi, 17, "s", formats=("shp",)))
    names = sorted(p.name for p in res.folder.iterdir())
    assert "s.gpkg" not in names and "s.shp" in names
    assert md.read_metadata_json(res.folder)["run"]["formats"] == ["shp"]


@needs_engine
def test_area_ha_is_geodesic_wgs84(results_root, chaco_aoi):
    from pyproj import Geod

    res = gb.build_grid(gb.BuildRequest(chaco_aoi, 17, "geo"))
    cells = pyogrio.read_dataframe(res.folder / "geo.gpkg", layer="geo")
    poly = cells.geometry.iloc[0]
    expected = abs(Geod(ellps="WGS84").geometry_area_perimeter(poly)[0]) / 1e4
    assert cells["area_ha"].iloc[0] == pytest.approx(expected, abs=1e-3)


@needs_engine
@needs_tippecanoe
def test_preview_is_built_but_not_a_deliverable(results_root, chaco_aoi, caplog):
    with caplog.at_level("INFO", logger="fra_grid"):
        res = gb.build_grid(gb.BuildRequest(chaco_aoi, 18, "pv", formats=("shp",)))  # shp-only still previews
    preview = res.folder / ".preview.pmtiles"
    assert preview.read_bytes()[:7] == b"PMTiles"
    assert res.metadata["preview"] == {"file": ".preview.pmtiles", "minzoom": 6, "maxzoom": 14}
    assert md.read_metadata_json(res.folder)["preview"] == res.metadata["preview"]
    assert ".preview.pmtiles" not in res.metadata["run"]["files"]
    assert preview not in res.files
    messages = [r.getMessage() for r in caplog.records]
    assert "Building map preview" in messages
    assert any(m.startswith("Map preview ready (") for m in messages)


@needs_engine
def test_missing_tippecanoe_keeps_the_grid(results_root, chaco_aoi, monkeypatch, caplog):
    monkeypatch.setattr(pp, "resolve_tippecanoe", lambda: None)
    with caplog.at_level("WARNING", logger="fra_grid"):
        res = gb.build_grid(gb.BuildRequest(chaco_aoi, 17, "nop"))
    assert res.cell_count == 330 and res.metadata["preview"] is None
    assert not (res.folder / ".preview.pmtiles").exists()
    assert any(r.levelname == "WARNING" and "Map preview skipped" in r.getMessage() for r in caplog.records)


@needs_engine
def test_failing_preview_keeps_the_grid(results_root, chaco_aoi, monkeypatch):
    def boom(*a, **k):
        raise pp.PreviewFailed("tippecanoe exited with 1")

    monkeypatch.setattr(pp, "build_preview", boom)
    res = gb.build_grid(gb.BuildRequest(chaco_aoi, 17, "f"))
    assert res.metadata["preview"] is None and (res.folder / "f.gpkg").exists()


@needs_engine
def test_cancel_during_preview_cancels_the_run(results_root, chaco_aoi, monkeypatch, tmp_path):
    def cancelled(*a, **k):
        raise pp.PreviewCancelled()

    monkeypatch.setattr(pp, "build_preview", cancelled)
    with pytest.raises(gb.BuildCancelled):
        gb.build_grid(gb.BuildRequest(chaco_aoi, 17, "c"))
    assert list(results_root.iterdir()) == []
    assert [p.name for p in (tmp_path / "local").iterdir()] == ["dggrid"]


def test_geodesic_area_helper_speed_per_100k():
    polys = np.array([box(-60 + i * 1e-4, -22, -59.99 + i * 1e-4, -21.99) for i in range(2000)], dtype=object)
    t0 = time.perf_counter()
    gb._geodesic_area_ha(polys)
    per_100k = (time.perf_counter() - t0) * 100_000 / len(polys)
    print(f"geodesic area: {per_100k:.2f} s per 100k cells")
    assert per_100k < 10.0
