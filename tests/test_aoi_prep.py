import time
from datetime import date
from types import SimpleNamespace

import geopandas as gpd
import pytest
from shapely.geometry import LineString, MultiPoint, Point, Polygon, box

from component.parameter import grid
from component.scripts import aoi_prep
from component.scripts.aoi_prep import AoiError, prepare_aoi

CHACO = (-60.10, -22.40, -60.00, -22.30)


def _gdf(*geoms, crs="EPSG:4326"):
    return gpd.GeoDataFrame(geometry=list(geoms), crs=crs)


def test_chaco_box_area_perimeter_bbox_and_hash():
    info = prepare_aoi(_gdf(box(*CHACO)), method="DRAW", label="Drawn polygon")
    assert info.area_km2 == pytest.approx(114.0647, rel=1e-5)
    assert set(info.perimeter_km) == set(grid.LEVELS)
    assert info.perimeter_km[17] == pytest.approx(42.7484, rel=1e-4)
    assert info.bbox == pytest.approx(CHACO)
    assert not info.is_points and info.n_points is None
    again = prepare_aoi(_gdf(box(*CHACO)), method="DRAW", label="x")
    assert info.wkb_sha256 == again.wkb_sha256 and len(info.wkb_sha256) == 64


def test_reprojects_to_wgs84():
    projected = _gdf(box(*CHACO)).to_crs("EPSG:3857")
    info = prepare_aoi(projected, method="SHAPE", label="f")
    assert info.bbox == pytest.approx(CHACO, abs=1e-6)


def test_invalid_polygon_is_repaired():
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    info = prepare_aoi(_gdf(bowtie), method="SHAPE", label="f")
    assert info.area_km2 > 0 and info.geometry.is_valid


@pytest.mark.parametrize(
    "geoms,key",
    [
        ((), "empty"),
        ((LineString([(0, 0), (1, 1)]),), "no_polygon"),
        ((box(-179.5, 0, 179.5, 1),), "antimeridian"),
    ],
)
def test_rejections(geoms, key):
    with pytest.raises(AoiError) as err:
        prepare_aoi(_gdf(*geoms), method="SHAPE", label="f")
    assert err.value.key == key


def test_points_are_deduplicated_and_have_no_area():
    info = prepare_aoi(_gdf(Point(0, 0), Point(0, 0), Point(1, 1)), method="POINTS", label="pts")
    assert info.is_points and info.n_points == 2
    assert isinstance(info.geometry, MultiPoint)
    assert info.area_km2 == 0 and all(v == 0 for v in info.perimeter_km.values())


def test_points_wider_than_180_degrees_are_accepted():
    info = prepare_aoi(_gdf(Point(-50, -10), Point(140, 35)), method="POINTS", label="pts")
    assert info.n_points == 2 and info.bbox == (-50, -10, 140, 35)


def test_complex_aoi_prepares_quickly():
    ring = Point(-60.0, -22.0).buffer(2.0, quad_segs=15_000)  # 60k vertices
    t0 = time.perf_counter()
    info = prepare_aoi(_gdf(ring), method="ADMIN1", label="big")
    assert time.perf_counter() - t0 < 5.0
    assert info.area_km2 > 40_000


def test_slugify_and_default_name():
    assert aoi_prep.slugify("Boquerón > Mariscal Estigarribia") == "boqueron_mariscal_estiga"
    assert aoi_prep.slugify("***") == "aoi"
    assert aoi_prep.default_grid_name(17, "chaco", date(2026, 10, 12)) == "fra_isea3h_r17_chaco_20261012"


@pytest.mark.parametrize(
    "result,expected",
    [
        (SimpleNamespace(method="ADMIN2", name="PRY_Boqueron", admin="123", spec=None), ("PRY_Boqueron", None)),
        (SimpleNamespace(method="SHAPE", name="x", admin=None, spec=SimpleNamespace(pathname="/h/u/chaco.gpkg")), ("chaco", "/h/u/chaco.gpkg")),
        (SimpleNamespace(method="ASSET", name="x", admin=None, spec=SimpleNamespace(asset_id="users/a/zone")), ("zone", "users/a/zone")),
        (SimpleNamespace(method="DRAW", name="x", admin=None, spec=None), ("Drawn polygon", None)),
    ],
)
def test_aoi_label(result, expected):
    assert aoi_prep.aoi_label(result) == expected


def test_resolve_prefers_gdf_then_admin_then_feature_collection(monkeypatch):
    gdf = _gdf(box(*CHACO))
    assert aoi_prep.resolve_aoi_gdf(SimpleNamespace(gdf=gdf, method="DRAW", admin=None, feature_collection=None)) is gdf

    calls = []
    monkeypatch.setattr(aoi_prep, "_admin_gdf", lambda m, c: calls.append((m, c)) or gdf)
    res = SimpleNamespace(gdf=None, method="ADMIN1", admin="77", feature_collection=None)
    assert aoi_prep.resolve_aoi_gdf(res) is gdf and calls == [("ADMIN1", "77")]

    monkeypatch.setattr(aoi_prep, "_feature_collection_gdf", lambda fc: gdf)
    res = SimpleNamespace(gdf=None, method="ASSET", admin=None, feature_collection=object())
    assert aoi_prep.resolve_aoi_gdf(res) is gdf

    with pytest.raises(AoiError):
        aoi_prep.resolve_aoi_gdf(SimpleNamespace(gdf=None, method="DRAW", admin=None, feature_collection=None))


def test_feature_collection_export_reads_and_removes_temp_file(tmp_path, monkeypatch):
    monkeypatch.setenv("FRA_GRID_SCRATCH", str(tmp_path))
    written = []

    def fake_export(fc, path):
        _gdf(box(*CHACO)).to_file(path, driver="GeoJSON")
        written.append(path)

    monkeypatch.setattr(aoi_prep, "_ee_to_geojson", fake_export)
    gdf = aoi_prep._feature_collection_gdf(object())
    assert len(gdf) == 1 and written and not written[0].exists()


def test_the_aoi_spec_reaches_the_metadata():
    from pysepal.solara.components.aoi import AoiSpec

    from component.scripts import metadata as md

    spec = AoiSpec(method="ADMIN1", admin_codes=("1", "2"))
    result = SimpleNamespace(method="ADMIN1", name="PRY_Chaco", admin="2", gdf=_gdf(box(*CHACO)), spec=spec)
    info = aoi_prep.aoi_info_from_result(result)
    record = md.build_record(name="g", aoi=info, level=17, formats=["gpkg"], files=[], cell_count=0, n_tiles=0,
                             tile_deg=1.0, clip_buffer_deg=0.0, duration_s=0.0, versions={})
    assert AoiSpec.from_dict(record["aoi"]["spec"]) == spec
