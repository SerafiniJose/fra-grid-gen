import numpy as np
import pytest
import shapely
from pyproj import Transformer
from shapely.geometry import Polygon, box

from component.parameter import grid
from component.scripts import fra_correction as fc

LATS = np.array([0.0, 15.0, -15.0, 22.35, -22.35, 45.0, -45.0, 60.0, -60.0, 85.0, -85.0])


def _oracle_sphere_to_wgs84(lat):
    """Independent oracle: a point on the sphere, as ECEF, to WGS84 geodetic (PROJ)."""
    t = Transformer.from_crs("EPSG:4978", "EPSG:4979", always_xy=True)
    r = grid.R_SPHERE_CORR_M
    x = r * np.cos(np.radians(lat))
    z = r * np.sin(np.radians(lat))
    _, lat_out, _ = t.transform(x, np.zeros_like(x), z)
    return np.asarray(lat_out)


def test_sphere_to_wgs84_matches_proj_oracle():
    assert np.abs(fc.sphere_to_wgs84_lat(LATS) - _oracle_sphere_to_wgs84(LATS)).max() < 1e-9


@pytest.mark.parametrize(
    "lat,expected",
    [(15.0, 15.09657922), (-22.35, -22.48575971), (45.0, 45.19231481),
     (60.0, 60.16613182), (-85.0, -85.03323073)],
)
def test_sphere_to_wgs84_reference_values(lat, expected):
    assert fc.sphere_to_wgs84_lat(lat) == pytest.approx(expected, abs=1e-8)


@pytest.mark.parametrize(
    "lat,expected",
    [(15.0, 15.09604964), (-22.35, -22.48512258), (45.0, 45.19210312),
     (60.0, 60.16636452), (-85.0, -85.03335721)],
)
def test_correct_lat_reference_values(lat, expected):
    assert fc.correct_lat(lat) == pytest.approx(expected, abs=1e-8)


def test_correction_properties():
    out = fc.correct_lat(LATS)
    assert fc.correct_lat(0.0) == pytest.approx(0.0, abs=1e-12)
    np.testing.assert_allclose(fc.correct_lat(-LATS), -out, atol=1e-12)  # odd function
    assert np.abs(out - LATS).max() < 0.2  # bounded shift
    dense = np.linspace(-89.9, 89.9, 5001)
    assert np.all(np.diff(fc.correct_lat(dense)) > 0)  # monotonic
    np.testing.assert_allclose(fc.correct_lat(np.array([90.0, -90.0])), [90.0, -90.0], atol=1e-9)


def test_approx_inverse_is_within_clip_margin():
    dense = np.linspace(-89.0, 89.0, 3561)
    err = np.abs(fc.approx_sphere_lat(fc.correct_lat(dense)) - dense)
    assert err.max() < grid.CLIP_EXTRA_DEG / 2


def test_correct_geometries_moves_latitudes_only():
    poly = box(-60.1, -22.4, -60.0, -22.3)
    (out,) = fc.correct_geometries(np.array([poly]))
    before = shapely.get_coordinates(poly)
    after = shapely.get_coordinates(out)
    np.testing.assert_array_equal(after[:, 0], before[:, 0])
    np.testing.assert_allclose(after[:, 1], fc.correct_lat(before[:, 1]))


def test_unwrap_antimeridian_shifts_negative_longitudes_of_wrapping_cells():
    wrapping = Polygon([(179.9, 0), (-179.9, 0), (-179.9, 0.1), (179.9, 0.1)])
    normal = box(10, 0, 10.1, 0.1)
    out = fc.unwrap_antimeridian(np.array([wrapping, normal]))
    xs = shapely.get_coordinates(out[0])[:, 0]
    assert xs.min() >= 179.9 and xs.max() <= 180.1
    assert out[1].equals(normal)


def test_to_sphere_geometry_inverts_the_correction_approximately():
    poly = box(-60.1, -22.4, -60.0, -22.3)
    sphere = fc.to_sphere_geometry(poly)
    ys = shapely.get_coordinates(sphere)[:, 1]
    np.testing.assert_allclose(fc.correct_lat(ys), shapely.get_coordinates(poly)[:, 1], atol=6e-4)
