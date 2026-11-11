"""Grid, correction and guard constants (spec §3, §6)."""

APP_NAME = "fra_grid_generator"
APP_VERSION = "0.1.0"
LOGGER_NAME = "fra_grid"

DGGS_TYPE = "ISEA3H"
FRA_LEVEL = 17
MIN_LEVEL = 17
MAX_LEVEL = 21
LEVELS = tuple(range(MIN_LEVEL, MAX_LEVEL + 1))

WARN_CELLS = 2_000_000
BLOCK_CELLS = 10_000_000
SHP_MAX_CELLS = 4_000_000
# Optional centroids: a 1 ha square at each cell's centroid (FRA RSS interpretation plot):
# north-up, 100 m sides on the WGS84 ellipsoid, written to the layer/file
# "<name>_centroids". Only levels whose hexagon holds the square: inradius >= the
# square's half-diagonal (70.7 m); r20 (65 m) and r21 are too small.
CENTROID_SIDE_M = 100.0
CENTROID_LEVELS = (17, 18, 19)
CENTROIDS_SUFFIX = "_centroids"
# GeoJSON map preview cap: grids without a PMTiles preview (older folders,
# tippecanoe missing at build time) are drawn cell by cell in the browser.
PREVIEW_MAX_CELLS = 50_000

# PMTiles map preview built with every grid (hidden; not a deliverable).
PREVIEW_FILE = ".preview.pmtiles"
PREVIEW_LAYER = "cells"  # tippecanoe -l name = MapLibre source-layer
# The centroids share the archive as a second source-layer, from zoom 12
# (~2.5 px a centroid): below that tippecanoe would draw them as merged blotches.
PREVIEW_CENTROIDS_LAYER = "centroids"
PREVIEW_CENTROIDS_MINZOOM = 12
# Web-map zoom range per level. Every level starts at zoom 3 (continent scale):
# where a cell is under a pixel, tippecanoe merges cells into stand-in squares
# (r21 shows real hexagons from z9, r17 from z6). Nothing is drawn below the min
# zoom; past the max the browser overzooms.
PREVIEW_MIN_ZOOM = 3
PREVIEW_ZOOMS = {17: (PREVIEW_MIN_ZOOM, 13), 18: (PREVIEW_MIN_ZOOM, 14), 19: (PREVIEW_MIN_ZOOM, 15),
                 20: (PREVIEW_MIN_ZOOM, 15), 21: (PREVIEW_MIN_ZOOM, 16)}

# Tile edge (degrees, WGS84) per level: keeps one dggrid call at <= ~200k cells.
TILE_DEG = {17: 1.0, 18: 1.0, 19: 0.5, 20: 0.5, 21: 0.25}
# Extra clip margin on top of one cell spacing: covers the approximate inverse
# of the latitude correction (error <= 0.00057 deg).
CLIP_EXTRA_DEG = 0.002
# Rough km per degree, for cell-size tolerances in degrees (AOI simplify, clip buffer).
KM_PER_DEG = 111.32

# DGGRID's sphere (WGS84 authalic radius), used for level statistics.
SPHERE_RADIUS_M = 6371007.180918475

# FRA RSS ISEA3H correction, spec v1.2 (ported from the R script).
CORRECTION_SPEC = "FRA RSS ISEA3H v1.2"
R_SPHERE_CORR_M = 6371007.1809
WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
SPHERE_ITERATIONS = 10
CALIB_C1 = 24.26
CALIB_C2 = 53.70
CALIB_R_M = 6371007.0

# ISEA3H as dggridR/DGGRID build it (recorded in metadata).
DGGS_PARAMS = {
    "type": DGGS_TYPE,
    "projection": "ISEA",
    "aperture": 3,
    "topology": "HEXAGON",
    "vert0_lon": 11.25,
    "vert0_lat": 58.28252559,
    "vert0_azimuth": 0.0,
    "sphere_radius_m": SPHERE_RADIUS_M,
    "id_field": "global_id",
    "id_type": "SEQNUM",
}
