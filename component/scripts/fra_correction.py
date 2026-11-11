"""FRA RSS ISEA3H v1.2 latitude correction (port of the R script's functions).

DGGRID returns vertices on its sphere. The official FRA grid moves every
vertex latitude through ``esfera_a_wgs84`` (geocentric point on the sphere ->
WGS84 geodetic latitude, 10 fixed-point iterations) and then ``calibrar``
(empirical sin 2phi / sin 4phi terms). Longitudes never change. This is NOT
an authalic conversion: never use dggrid4py's auxlat helpers instead.
"""

import numpy as np
import shapely

from component.parameter import grid as g

_E2 = g.WGS84_F * (2.0 - g.WGS84_F)


def sphere_to_wgs84_lat(lat):
    """Sphere latitude (deg) -> WGS84 geodetic latitude (deg). R: esfera_a_wgs84."""
    lat = np.asarray(lat, dtype="float64")
    rad = np.radians(lat)
    p = g.R_SPHERE_CORR_M * np.cos(rad)
    z = g.R_SPHERE_CORR_M * np.sin(rad)
    phi = np.arctan2(z, p * (1.0 - _E2))
    for _ in range(g.SPHERE_ITERATIONS):
        n = g.WGS84_A / np.sqrt(1.0 - _E2 * np.sin(phi) ** 2)
        h = p / np.cos(phi) - n
        phi = np.arctan2(z, p * (1.0 - _E2 * n / (n + h)))
    return np.degrees(phi)


def calibrate(lat):
    """Empirical FRA calibration (deg -> deg). R: calibrar."""
    lat = np.asarray(lat, dtype="float64")
    phi = np.radians(lat)
    shift_m = -(g.CALIB_C1 * np.sin(2.0 * phi) + g.CALIB_C2 * np.sin(4.0 * phi))
    return lat + (shift_m / g.CALIB_R_M) * (180.0 / np.pi)


def correct_lat(lat):
    """Full FRA correction of a sphere latitude."""
    return calibrate(sphere_to_wgs84_lat(lat))


def approx_sphere_lat(lat):
    """Approximate inverse (WGS84 -> sphere). R: lat_esfera. Clip windows only."""
    lat = np.asarray(lat, dtype="float64")
    return np.degrees(np.arctan((1.0 - _E2) * np.tan(np.radians(lat))))


def sphere_lat_of(lat):
    """Exact inverse of ``correct_lat`` (WGS84 -> sphere latitude), by Newton steps.

    Starts from ``approx_sphere_lat`` (within 0.00057 deg); four steps reach float precision.
    """
    target = np.asarray(lat, dtype="float64")
    x = approx_sphere_lat(target)
    h = 1e-6
    for _ in range(4):
        slope = (correct_lat(x + h) - correct_lat(x - h)) / (2.0 * h)
        x = x - (correct_lat(x) - target) / slope
    return np.clip(x, -90.0, 90.0)


def _correct_xy(xy):
    out = xy.copy()
    out[:, 1] = correct_lat(xy[:, 1])
    return out


def _sphere_xy(xy):
    out = xy.copy()
    out[:, 1] = approx_sphere_lat(xy[:, 1])
    return out


def _unwrap_xy(xy):
    out = xy.copy()
    neg = out[:, 0] < 0
    out[neg, 0] += 360.0
    return out


def unwrap_antimeridian(geoms):
    """R rule: a cell spanning > 180 deg of longitude gets its negative lons + 360."""
    geoms = np.asarray(geoms, dtype=object).copy()
    if geoms.size == 0:
        return geoms
    bounds = shapely.bounds(geoms)
    wraps = (bounds[:, 2] - bounds[:, 0]) > 180.0
    if wraps.any():
        geoms[wraps] = shapely.transform(geoms[wraps], _unwrap_xy)
    return geoms


def correct_geometries(geoms):
    """Correct every vertex latitude of an array of sphere-space geometries."""
    geoms = np.asarray(geoms, dtype=object)
    if geoms.size == 0:
        return geoms.copy()
    return shapely.transform(geoms, _correct_xy)


def to_sphere_geometry(geom):
    """Move a WGS84 geometry's latitudes into (approximate) sphere space."""
    return shapely.transform(geom, _sphere_xy)
