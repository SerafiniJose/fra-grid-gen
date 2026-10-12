"""Provenance of one generated grid: ``metadata.json`` and the GPKG metadata tables.

GPKG side follows the GeoPackage metadata extension (spec 1.2, §F.8):
the JSON record goes into ``gpkg_metadata`` (md_scope 'dataset', mime
'application/json') and is linked to the layer through
``gpkg_metadata_reference`` (reference_scope 'table').
"""

import getpass
import json
import os
import platform
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from component.parameter import grid as g

SCHEMA = "fra-grid-metadata/1"
METADATA_FILE = "metadata.json"
AOI_FILE = "aoi.geojson"
_JSON_URI = "https://www.iana.org/assignments/media-types/application/json"
_EXT_DEFINITION = "http://www.geopackage.org/spec120/#extension_metadata"

FIELD_DOCS = {
    "global_id": "DGGRID SEQNUM at this resolution; official FRA RSS id at r17",
    "fra_r17_id": "FRA RSS r17 id containing the cell centroid (levels > 17 only)",
    "level": "ISEA3H resolution",
    "lon": "centroid longitude (WGS84)",
    "lat": "centroid latitude (WGS84)",
    "area_ha": "geodesic cell area on the WGS84 ellipsoid, hectares",
}

_DDL = """
CREATE TABLE IF NOT EXISTS gpkg_metadata (
  id INTEGER CONSTRAINT m_pk PRIMARY KEY ASC NOT NULL,
  md_scope TEXT NOT NULL DEFAULT 'dataset',
  md_standard_uri TEXT NOT NULL,
  mime_type TEXT NOT NULL DEFAULT 'text/xml',
  metadata TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS gpkg_metadata_reference (
  reference_scope TEXT NOT NULL,
  table_name TEXT,
  column_name TEXT,
  row_id_value INTEGER,
  timestamp DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  md_file_id INTEGER NOT NULL,
  md_parent_id INTEGER,
  CONSTRAINT crmr_mfi_fk FOREIGN KEY (md_file_id) REFERENCES gpkg_metadata(id),
  CONSTRAINT crmr_mpi_fk FOREIGN KEY (md_parent_id) REFERENCES gpkg_metadata(id)
);
CREATE TABLE IF NOT EXISTS gpkg_extensions (
  table_name TEXT,
  column_name TEXT,
  extension_name TEXT NOT NULL,
  definition TEXT NOT NULL,
  scope TEXT NOT NULL,
  CONSTRAINT ge_tce UNIQUE (table_name, column_name, extension_name)
);
"""


def _user() -> str:
    for key in ("SEPAL_USER", "USER", "LOGNAME"):
        if os.environ.get(key):
            return os.environ[key]
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def build_record(
    *, name, aoi, level, formats, files, cell_count, n_tiles, tile_deg, clip_buffer_deg,
    duration_s, versions, generated_at=None,
) -> dict:
    when = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    fields = {k: v for k, v in FIELD_DOCS.items() if k != "fra_r17_id" or level > g.FRA_LEVEL}
    return {
        "schema": SCHEMA,
        "name": name,
        "generated_at": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": {
            "app": g.APP_NAME,
            "app_version": g.APP_VERSION,
            "dggrid": versions.get("dggrid", "unknown"),
            "dggrid4py": versions.get("dggrid4py", "unknown"),
            "python": platform.python_version(),
            "sepal_user": _user(),
        },
        "dggs": {**g.DGGS_PARAMS, "resolution": int(level), "is_fra_rss_level": level == g.FRA_LEVEL},
        "correction": {
            "spec": g.CORRECTION_SPEC,
            "sphere_to_wgs84": f"geocentric, {g.SPHERE_ITERATIONS} iterations",
            "sphere_radius_m": g.R_SPHERE_CORR_M,
            "calibration": {"C1": g.CALIB_C1, "C2": g.CALIB_C2, "R_m": g.CALIB_R_M},
            "validated_at_levels": [g.FRA_LEVEL],
        },
        "aoi": {
            "method": aoi.method,
            "label": aoi.label,
            "admin_code": aoi.admin_code,
            "source": aoi.source,
            "area_km2": round(aoi.area_km2, 3),
            "n_points": aoi.n_points,
            "bbox": [round(v, 6) for v in aoi.bbox],
            "wkb_sha256": aoi.wkb_sha256,
            "geometry_file": AOI_FILE,
        },
        "run": {
            "tile_deg": tile_deg,
            "clip_buffer_deg": round(clip_buffer_deg, 6),
            "n_tiles": int(n_tiles),
            "cell_count": int(cell_count),
            "duration_s": round(duration_s, 1),
            "formats": sorted(formats),
            "files": list(files),
        },
        "fields": fields,
    }


def summary_line(record: dict) -> str:
    return (
        f"FRA ISEA3H r{record['dggs']['resolution']} grid, {record['run']['cell_count']:,} cells, "
        f"AOI {record['aoi']['label']}, generated {record['generated_at']} by "
        f"{record['generator']['app']} {record['generator']['app_version']}"
    )


def write_metadata_json(record: dict, folder) -> Path:
    path = Path(folder) / METADATA_FILE
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path


def read_metadata_json(folder):
    try:
        record = json.loads((Path(folder) / METADATA_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        return None
    return record


def embed_in_gpkg(gpkg_path, layer: str, record: dict) -> None:
    payload = json.dumps(record, ensure_ascii=False)
    with closing(sqlite3.connect(gpkg_path)) as con, con:
        con.executescript(_DDL)
        md_id = con.execute(
            "INSERT INTO gpkg_metadata (md_scope, md_standard_uri, mime_type, metadata) "
            "VALUES ('dataset', ?, 'application/json', ?)",
            (_JSON_URI, payload),
        ).lastrowid
        con.execute(
            "INSERT INTO gpkg_metadata_reference (reference_scope, table_name, md_file_id) VALUES ('table', ?, ?)",
            (layer, md_id),
        )
        for table in ("gpkg_metadata", "gpkg_metadata_reference"):
            con.execute(
                "INSERT INTO gpkg_extensions (table_name, column_name, extension_name, definition, scope) "
                "SELECT ?, NULL, 'gpkg_metadata', ?, 'read-write' WHERE NOT EXISTS "
                "(SELECT 1 FROM gpkg_extensions WHERE table_name = ? AND extension_name = 'gpkg_metadata')",
                (table, _EXT_DEFINITION, table),
            )
        con.execute("UPDATE gpkg_contents SET description = ? WHERE table_name = ?", (summary_line(record), layer))


def read_gpkg_metadata(gpkg_path, layer: str):
    try:
        uri = Path(gpkg_path).absolute().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as con:
            row = con.execute(
                "SELECT m.metadata FROM gpkg_metadata m JOIN gpkg_metadata_reference r ON r.md_file_id = m.id "
                "WHERE r.reference_scope = 'table' AND r.table_name = ? AND m.mime_type = 'application/json' "
                "ORDER BY m.id DESC LIMIT 1",
                (layer,),
            ).fetchone()
    except sqlite3.Error:
        return None
    return json.loads(row[0]) if row else None
