from __future__ import annotations

from app.coordination.assignment import haversine_m
from app.models import Drone, LatLon

ALTITUDE_BAND_SEP_M = 5.0
DEFAULT_BANDS = [30.0, 40.0, 50.0, 60.0, 70.0]


def _same_altitude_band(a: float, b: float) -> bool:
    return abs(a - b) < ALTITUDE_BAND_SEP_M


def detect_conflicts(
    drones: list[Drone],
    min_sep_m: float = 10.0,
    altitudes: dict[str, float] | None = None,
) -> list[tuple[str, str]]:
    altitudes = altitudes or {}
    conflicts: list[tuple[str, str]] = []
    for i, left in enumerate(drones):
        for right in drones[i + 1 :]:
            if haversine_m(left.pos, right.pos) < min_sep_m and _same_altitude_band(
                altitudes.get(left.drone_id, 30.0),
                altitudes.get(right.drone_id, 30.0),
            ):
                conflicts.append((left.drone_id, right.drone_id))
    return conflicts


def deconflict(drones: list[Drone], altitudes: dict[str, float] | None = None) -> dict[str, float]:
    assigned = dict(altitudes or {})
    for drone in drones:
        for band in DEFAULT_BANDS:
            trial = dict(assigned)
            trial[drone.drone_id] = band
            prior = [d for d in drones if d.drone_id in assigned and d.drone_id != drone.drone_id]
            if not detect_conflicts(prior + [drone], altitudes=trial):
                assigned[drone.drone_id] = band
                break
        else:
            assigned[drone.drone_id] = DEFAULT_BANDS[-1] + len(assigned) * 10.0
    return assigned


def _segment_min_distance_m(
    a_start: Drone, a_end: LatLon, b_start: Drone, b_end: LatLon, samples: int = 10
) -> float:
    """Approximate closest approach between two moving points over one tick
    by sampling `samples` interpolation fractions along each segment. Good
    enough at patrol speeds/tick lengths (~15 m/s, 0.5s ticks -> ~7.5m per
    tick) without needing a closed-form segment-distance solve.
    """
    min_dist = float("inf")
    for i in range(samples + 1):
        frac = i / samples
        a_lat = a_start.pos.lat + (a_end.lat - a_start.pos.lat) * frac
        a_lon = a_start.pos.lon + (a_end.lon - a_start.pos.lon) * frac
        b_lat = b_start.pos.lat + (b_end.lat - b_start.pos.lat) * frac
        b_lon = b_start.pos.lon + (b_end.lon - b_start.pos.lon) * frac
        dist = haversine_m(LatLon(a_lat, a_lon), LatLon(b_lat, b_lon))
        min_dist = min(min_dist, dist)
    return min_dist


def detect_segment_conflicts(
    prev_positions: dict[str, LatLon],
    drones: list[Drone],
    min_sep_m: float = 10.0,
    altitudes: dict[str, float] | None = None,
) -> list[tuple[str, str]]:
    """Like detect_conflicts, but checks the swept path between each drone's
    previous-tick and current-tick position, not just current-tick point
    distance - catches two drones passing near each other mid-tick on
    overlapping patrol circles even if never co-located at a sampled instant.
    """
    altitudes = altitudes or {}
    conflicts: list[tuple[str, str]] = []
    for i, left in enumerate(drones):
        for right in drones[i + 1 :]:
            if left.drone_id not in prev_positions or right.drone_id not in prev_positions:
                continue
            if not _same_altitude_band(
                altitudes.get(left.drone_id, 30.0), altitudes.get(right.drone_id, 30.0)
            ):
                continue
            left_start = Drone(left.drone_id, prev_positions[left.drone_id], 1.0, left.status, None)
            right_start = Drone(right.drone_id, prev_positions[right.drone_id], 1.0, right.status, None)
            if _segment_min_distance_m(left_start, left.pos, right_start, right.pos) < min_sep_m:
                conflicts.append((left.drone_id, right.drone_id))
    return conflicts
