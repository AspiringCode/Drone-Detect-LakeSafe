import math

from app.coordination.assignment import haversine_m
from app.geo import circle_polygon, destination_point
from app.models import LatLon


def test_destination_point_round_trips_through_haversine():
    origin = LatLon(47.58, -122.09)
    for bearing in (0.0, 90.0, 180.0, 270.0):
        dest = destination_point(origin, bearing, 100.0)
        assert math.isclose(haversine_m(origin, dest), 100.0, abs_tol=0.5)


def test_destination_point_bearing_zero_moves_north():
    origin = LatLon(47.58, -122.09)
    dest = destination_point(origin, 0.0, 100.0)
    assert dest.lat > origin.lat
    assert math.isclose(dest.lon, origin.lon, abs_tol=1e-6)


def test_circle_polygon_is_closed_ring_at_radius():
    center = LatLon(47.58, -122.09)
    ring = circle_polygon(center, radius_m=50.0, n_points=24)
    assert len(ring) == 25  # 24 distinct points + repeated first point to close the ring
    assert ring[0] == ring[-1]
    for point in ring[:-1]:
        assert math.isclose(haversine_m(center, point), 50.0, abs_tol=0.5)
