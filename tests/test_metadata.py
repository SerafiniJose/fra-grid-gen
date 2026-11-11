import json
import sqlite3
from datetime import datetime, timezone

import geopandas as gpd
import pyogrio
from shapely.geometry import box

from component.scripts import metadata as md
from _fakes import read_gpkg_metadata


def _record(chaco_aoi, level=17, name="g"):
    return md.build_record(
        name=name, aoi=chaco_aoi, level=level, formats=["gpkg"], files=[f"{name}.gpkg", "metadata.json", "aoi.geojson"],
        cell_count=330, n_tiles=1, tile_deg=1.0, clip_buffer_deg=0.0087, duration_s=1.23,
        versions={"dggrid": "8.44", "dggrid4py": "0.6.0"},
        generated_at=datetime(2026, 10, 12, 14, 3, 22, tzinfo=timezone.utc),
    )


def test_record_shape(chaco_aoi):
    rec = _record(chaco_aoi)
    assert rec["schema"] == md.SCHEMA and rec["generated_at"] == "2026-10-12T14:03:22Z"
    assert rec["dggs"]["resolution"] == 17 and rec["dggs"]["is_fra_rss_level"] is True
    assert rec["dggs"]["type"] == "ISEA3H" and rec["dggs"]["aperture"] == 3
    assert rec["correction"]["calibration"] == {"C1": 24.26, "C2": 53.70, "R_m": 6371007.0}
    assert rec["correction"]["validated_at_levels"] == [17]
    assert rec["aoi"]["method"] == "DRAW" and rec["aoi"]["geometry_file"] == "aoi.geojson"
    assert rec["run"]["cell_count"] == 330 and rec["run"]["duration_s"] == 1.2
    assert rec["generator"]["dggrid"] == "8.44" and rec["generator"]["app"] == "fra_grid_generator"
    assert "fra_r17_id" not in rec["fields"]
    assert "fra_r17_id" in _record(chaco_aoi, level=18)["fields"]
    assert rec["preview"] is None  # no preview built
    json.dumps(rec)  # serialisable


def test_metadata_json_round_trip_and_rejects_garbage(tmp_path, chaco_aoi):
    rec = _record(chaco_aoi)
    path = md.write_metadata_json(rec, tmp_path)
    assert path == tmp_path / "metadata.json"
    assert md.read_metadata_json(tmp_path) == rec
    path.write_text("{not json")
    assert md.read_metadata_json(tmp_path) is None
    path.write_text(json.dumps({"schema": "other"}))
    assert md.read_metadata_json(tmp_path) is None
    assert md.read_metadata_json(tmp_path / "missing") is None


def test_gpkg_embedding_round_trip(tmp_path, chaco_aoi):
    gpkg = tmp_path / "g.gpkg"
    frame = gpd.GeoDataFrame({"global_id": [1, 2]}, geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)], crs="EPSG:4326")
    pyogrio.write_dataframe(frame, gpkg, layer="g", driver="GPKG")
    rec = _record(chaco_aoi)
    md.embed_in_gpkg(gpkg, "g", rec)
    assert read_gpkg_metadata(gpkg, "g") == rec
    with sqlite3.connect(gpkg) as con:
        desc = con.execute("SELECT description FROM gpkg_contents WHERE table_name='g'").fetchone()[0]
        ext = con.execute("SELECT count(*) FROM gpkg_extensions WHERE extension_name='gpkg_metadata'").fetchone()[0]
        ok = con.execute("PRAGMA integrity_check").fetchone()[0]
    assert desc == md.summary_line(rec) and ext == 2 and ok == "ok"
    assert pyogrio.read_info(gpkg, layer="g")["features"] == 2  # GDAL still opens it


def test_area_ha_doc_names_the_wgs84_ellipsoid():
    assert md.FIELD_DOCS["area_ha"] == "geodesic cell area on the WGS84 ellipsoid, hectares"
