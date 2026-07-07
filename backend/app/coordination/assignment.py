from __future__ import annotations

import math

from app.models import Drone, LatLon, RiskZone

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(a: LatLon, b: LatLon) -> float:
    lat1 = math.radians(a.lat)
    lat2 = math.radians(b.lat)
    dlat = lat2 - lat1
    dlon = math.radians(b.lon - a.lon)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def eta_seconds(a: LatLon, b: LatLon, speed_mps: float) -> float:
    if speed_mps <= 0:
        raise ValueError("speed_mps must be positive")
    return haversine_m(a, b) / speed_mps


def assign_zones(
    drones: list[Drone],
    zones: list[RiskZone],
    max_eta_s: float = 90.0,
    speed_mps: float = 15.0,
) -> dict[str, str | None]:
    """Greedy risk-weighted assignment using Subsystem A scores.

    This deliberately small solver covers highest-risk zones first while
    enforcing ETA reachability and one drone per zone. The function boundary is
    the seam for a later PSO/enhanced-A* coverage-path solver.
    """
    assignments: dict[str, str | None] = {drone.drone_id: None for drone in drones}
    free = {drone.drone_id: drone for drone in drones}
    for zone in sorted(zones, key=lambda z: z.risk_score, reverse=True):
        candidates = [
            (eta_seconds(drone.pos, zone.centroid, speed_mps), drone)
            for drone in free.values()
            if eta_seconds(drone.pos, zone.centroid, speed_mps) <= max_eta_s
        ]
        if not candidates:
            continue
        _, chosen = min(candidates, key=lambda item: item[0])
        assignments[chosen.drone_id] = zone.zone_id
        del free[chosen.drone_id]
    return assignments
