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
PREVIEW_MAX_CELLS = 50_000

# Tile edge (degrees, WGS84) per level: keeps one dggrid call at <= ~200k cells.
TILE_DEG = {17: 1.0, 18: 1.0, 19: 0.5, 20: 0.5, 21: 0.25}
# Extra clip margin on top of one cell spacing: covers the approximate inverse
# of the latitude correction (error <= 0.00057 deg).
CLIP_EXTRA_DEG = 0.002

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
