"""Grid file writers. Callers pass absolute paths only."""

import zipfile
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


def copy_layer(src, dst, layer: str, *, driver: str, chunk: int = 500_000) -> Path:
    """Copy one layer of ``src`` (GPKG or Shapefile) to ``dst`` in chunks (bounded memory)."""
    src, dst = Path(src), Path(dst)
    extra = {"encoding": "UTF-8"} if driver == "ESRI Shapefile" else {"layer": layer}
    total = pyogrio.read_info(src, layer=layer)["features"]
    for start in range(0, total, chunk):
        part = pyogrio.read_dataframe(src, layer=layer, skip_features=start, max_features=chunk)
        pyogrio.write_dataframe(part, dst, driver=driver, append=start > 0, **extra)
    return dst


def gpkg_to_shp(gpkg, shp, layer: str, *, chunk: int = 500_000) -> list:
    return shp_files(copy_layer(gpkg, shp, layer, driver="ESRI Shapefile", chunk=chunk))


def export_zip(folder, layer: str, fmt: str, dest) -> Path:
    """Zip one layer of a grid folder as ``fmt`` ("gpkg" or "shp") into the folder ``dest``.

    The grid's own files are zipped as they are when they match; otherwise the
    layer is converted from whichever of ``<name>.gpkg`` / ``<layer>.shp`` exists.
    """
    folder, dest = Path(folder), Path(dest)
    name = folder.name
    gpkg, shp = folder / f"{name}.gpkg", folder / f"{layer}.shp"
    src = gpkg if gpkg.exists() else shp
    if not src.exists():
        raise FileNotFoundError(f"{layer} is in neither {gpkg.name} nor {shp.name}")
    if fmt == "shp":
        files = shp_files(shp) if shp.exists() else gpkg_to_shp(gpkg, dest / shp.name, layer)
    elif src == gpkg and pyogrio.list_layers(gpkg)[:, 0].tolist() == [layer]:
        files = [gpkg]  # keeps the embedded metadata
    else:
        files = [copy_layer(src, dest / f"{layer}.gpkg", layer, driver="GPKG")]
    out = dest / f"{layer}_{fmt}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, path.name)
    return out


def write_aoi_geojson(geometry, path) -> Path:
    path = Path(path)
    gpd.GeoDataFrame(geometry=[geometry], crs="EPSG:4326").to_file(path, driver="GeoJSON", engine="pyogrio")
    return path


def file_sizes(folder) -> list:
    return sorted((p.name, p.stat().st_size) for p in Path(folder).iterdir() if p.is_file())


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
