"""Test doubles and readers shared by several test modules."""

import json
import sqlite3
from contextlib import closing


def read_gpkg_metadata(gpkg_path, layer: str):
    """The JSON record embedded for ``layer`` by ``metadata.embed_in_gpkg``."""
    with closing(sqlite3.connect(gpkg_path)) as con:
        row = con.execute(
            "SELECT m.metadata FROM gpkg_metadata m JOIN gpkg_metadata_reference r ON r.md_file_id = m.id "
            "WHERE r.reference_scope = 'table' AND r.table_name = ? AND m.mime_type = 'application/json' "
            "ORDER BY m.id DESC LIMIT 1",
            (layer,),
        ).fetchone()
    return json.loads(row[0])


class FakeMap:
    def __init__(self):
        self.layers, self.controls, self.zoomed = [], [], None
        self.dc = object()

    def add_layer(self, layer, hover=False, key=""):
        layer.key = key
        self.layers = [lyr for lyr in self.layers if getattr(lyr, "key", None) != key] + [layer]

    def find_layer(self, key, base=False, none_ok=False):
        return next((lyr for lyr in self.layers if getattr(lyr, "key", None) == key), None)

    def remove_layer(self, key, base=False, none_ok=False):
        self.layers = [lyr for lyr in self.layers if lyr is not key]

    def zoom_bounds(self, bounds, zoom_out=1):
        self.zoomed = bounds

    def add_control(self, c):
        self.controls.append(c)

    def remove_control(self, c):
        self.controls.remove(c)
