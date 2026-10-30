"""Download an Earth Engine FeatureCollection's geometries to a local GeoJSON.

Replaces ``geemap.ee_export_vector`` (the only geemap function this project
used), so geemap and its dependency tree stay out of the deployment environment.
"""

from pathlib import Path


def ee_export_vector(ee_object, filename, timeout: int = 300) -> Path:
    """Write ``ee_object``'s geometries (no properties) to ``filename`` as GeoJSON."""
    import requests

    path = Path(filename).absolute()
    url = ee_object.getDownloadURL(filetype="geojson", selectors=[".geo"], filename=path.stem)
    response = requests.get(url, stream=True, timeout=timeout)
    if response.status_code != 200:
        raise RuntimeError(f"Export of {path.name} failed with HTTP {response.status_code}: {response.text[:500]}")
    with open(path, "wb") as fd:
        for chunk in response.iter_content(chunk_size=8192):
            fd.write(chunk)
    return path
