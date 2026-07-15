from __future__ import annotations

import math

from app.models import LatLon

EARTH_RADIUS_M = 6_371_000.0


def destination_point(origin: LatLon, bearing_deg: float, distance_m: float) -> LatLon:
    """Forward geodesic: the point `distance_m` from `origin` along `bearing_deg`.

    Companion to the haversine distance formula (app.coordination.assignment);
    same spherical-earth model, opposite direction (bearing+distance -> point,
    rather than two points -> distance).
    """
    lat1 = math.radians(origin.lat)
    lon1 = math.radians(origin.lon)
    bearing = math.radians(bearing_deg)
    angular_dist = distance_m / EARTH_RADIUS_M

    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_dist)
        + math.cos(lat1) * math.sin(angular_dist) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular_dist) * math.cos(lat1),
        math.cos(angular_dist) - math.sin(lat1) * math.sin(lat2),
    )
    return LatLon(math.degrees(lat2), math.degrees(lon2))


def circle_polygon(center: LatLon, radius_m: float, n_points: int = 24) -> list[LatLon]:
    """Closed-ring polygon approximating a circle, for GeoJSON rendering."""
    step_deg = 360.0 / n_points
    ring = [destination_point(center, i * step_deg, radius_m) for i in range(n_points)]
    ring.append(ring[0])
    return ring
