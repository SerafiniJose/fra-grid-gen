import geopandas as gpd
import numpy as np
import pyogrio
import pytest
from shapely.geometry import box

from component.scripts import writers


def _cells(ids, level=21, with_parent=True):
    data = {"global_id": np.array(ids, dtype="int64")}
    if with_parent:
        data["fra_r17_id"] = np.array([7] * len(ids), dtype="int64")
    data["level"] = np.full(len(ids), level, dtype="int16")
    data["lon"] = np.linspace(0, 1, len(ids))
    data["lat"] = np.linspace(0, 1, len(ids))
    data["area_ha"] = np.full(len(ids), 0.488)
    geoms = [box(i, 0, i + 0.5, 0.5) for i in range(len(ids))]
    return gpd.GeoDataFrame(data, geometry=geoms, crs="EPSG:4326")


def test_append_cells_keeps_schema_and_int64_ids(tmp_path):
    gpkg = tmp_path / "g.gpkg"
    writers.append_cells(_cells([104_603_532_031, 2]), gpkg, "g", first=True)
    writers.append_cells(_cells([3, 4, 5]), gpkg, "g", first=False)
    back = pyogrio.read_dataframe(gpkg, layer="g")
    assert len(back) == 5
    assert back["global_id"].dtype == np.int64 and back["global_id"].iloc[0] == 104_603_532_031
    assert back["level"].dtype == np.int16
    assert list(back.columns) == ["global_id", "fra_r17_id", "level", "lon", "lat", "area_ha", "geometry"]


def test_gpkg_to_shp_in_chunks_writes_all_sidecars(tmp_path):
    gpkg = tmp_path / "g.gpkg"
    writers.append_cells(_cells([104_603_532_031, 2, 3]), gpkg, "g", first=True)
    files = writers.gpkg_to_shp(gpkg, tmp_path / "g.shp", "g", chunk=1)
    assert sorted(f.suffix for f in files) == sorted(writers.SHP_SIDECARS)
    back = pyogrio.read_dataframe(tmp_path / "g.shp")
    assert len(back) == 3 and back["global_id"].iloc[0] == 104_603_532_031
    assert "fra_r17_id" in back.columns  # exactly 10 characters: survives DBF


def test_write_aoi_geojson(tmp_path):
    path = writers.write_aoi_geojson(box(0, 0, 1, 1), tmp_path / "aoi.geojson")
    back = gpd.read_file(path)
    assert len(back) == 1 and back.crs.to_epsg() == 4326


def test_file_sizes_and_human_size(tmp_path):
    (tmp_path / "b.txt").write_bytes(b"x" * 10)
    (tmp_path / "a.txt").write_bytes(b"x" * 2048)
    (tmp_path / "sub").mkdir()
    assert writers.file_sizes(tmp_path) == [("a.txt", 2048), ("b.txt", 10)]
    assert writers.human_size(10) == "10 B"
    assert writers.human_size(2048) == "2.0 KB"
    assert writers.human_size(5 * 1024**3) == "5.0 GB"
