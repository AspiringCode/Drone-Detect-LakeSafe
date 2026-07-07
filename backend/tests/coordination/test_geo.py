from app.coordination.assignment import eta_seconds, haversine_m
from app.models import LatLon


def test_haversine_known_lake_sammamish_points():
    a = LatLon(47.5800, -122.0900)
    b = LatLon(47.5900, -122.0900)
    assert 1100 <= haversine_m(a, b) <= 1120


def test_eta_seconds_is_distance_over_speed():
    a = LatLon(47.5800, -122.0900)
    b = LatLon(47.5900, -122.0900)
    distance = haversine_m(a, b)
    assert eta_seconds(a, b, speed_mps=10.0) == distance / 10.0
