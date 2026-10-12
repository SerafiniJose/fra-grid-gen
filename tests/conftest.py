import geopandas as gpd
import pytest
from shapely.geometry import box

from component.scripts.aoi_prep import prepare_aoi

# The R script's example AOI (Chaco, Paraguay).
CHACO_BOX = (-60.10, -22.40, -60.00, -22.30)


@pytest.fixture
def results_root(tmp_path, monkeypatch):
    root = tmp_path / "module_results" / "fra_grid_generator"
    root.mkdir(parents=True)
    monkeypatch.setenv("FRA_GRID_RESULTS_DIR", str(root))
    monkeypatch.setenv("FRA_GRID_SCRATCH", str(tmp_path / "nfs"))
    monkeypatch.setenv("FRA_GRID_LOCAL_SCRATCH", str(tmp_path / "local"))
    return root


@pytest.fixture(scope="session")
def chaco_aoi():
    gdf = gpd.GeoDataFrame(geometry=[box(*CHACO_BOX)], crs="EPSG:4326")
    return prepare_aoi(gdf, method="DRAW", label="Chaco")
