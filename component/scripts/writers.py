"""Grid file writers. Callers pass absolute paths only."""

from pathlib import Path

import geopandas as gpd
import pyogrio

SHP_SIDECARS = (".shp", ".shx", ".dbf", ".prj", ".cpg")


def append_cells(frame, path, layer: str, *, first: bool) -> None:
    """Write (first=True) or append one tile's cells to the GPKG layer."""
    pyogrio.write_dataframe(
        frame, Path(path), layer=layer, driver="GPKG", append=not first, geometry_type="Polygon"
    )


def shp_files(shp) -> list:
    shp = Path(shp)
    return [shp.with_suffix(ext) for ext in SHP_SIDECARS if shp.with_suffix(ext).exists()]


def gpkg_to_shp(gpkg, shp, layer: str, *, chunk: int = 500_000) -> list:
    """Copy the GPKG layer to a Shapefile in chunks (bounded memory)."""
    gpkg, shp = Path(gpkg), Path(shp)
    total = pyogrio.read_info(gpkg, layer=layer)["features"]
    for start in range(0, total, chunk):
        part = pyogrio.read_dataframe(gpkg, layer=layer, skip_features=start, max_features=chunk)
        pyogrio.write_dataframe(part, shp, driver="ESRI Shapefile", append=start > 0, encoding="UTF-8")
    return shp_files(shp)


def write_aoi_geojson(geometry, path) -> Path:
    path = Path(path)
    gpd.GeoDataFrame(geometry=[geometry], crs="EPSG:4326").to_file(path, driver="GeoJSON", engine="pyogrio")
    return path


def file_sizes(folder) -> list:
    return sorted((p.name, p.stat().st_size) for p in Path(folder).iterdir() if p.is_file())


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
