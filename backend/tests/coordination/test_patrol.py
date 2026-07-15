import math

from app.coordination.assignment import haversine_m
from app.coordination.patrol import circle_waypoints
from app.models import LatLon


def test_waypoints_all_at_radius_from_center():
    center = LatLon(47.58, -122.09)
    waypoints = circle_waypoints(center, radius_m=60.0, n_points=16)
    assert len(waypoints) == 16
    for wp in waypoints:
        assert math.isclose(haversine_m(center, wp), 60.0, abs_tol=0.5)


def test_phase_offset_rotates_starting_point():
    center = LatLon(47.58, -122.09)
    base = circle_waypoints(center, radius_m=60.0, n_points=16, phase_offset_deg=0.0)
    offset = circle_waypoints(center, radius_m=60.0, n_points=16, phase_offset_deg=90.0)
    assert base[0] != offset[0]


def test_counterclockwise_reverses_traversal_order():
    center = LatLon(47.58, -122.09)
    cw = circle_waypoints(center, radius_m=60.0, n_points=16, clockwise=True)
    ccw = circle_waypoints(center, radius_m=60.0, n_points=16, clockwise=False)
    assert cw[1] != ccw[1]
    assert cw[0] == ccw[0]  # same starting point, opposite direction from there
