from __future__ import annotations

from app.coordination.assignment import haversine_m
from app.models import Drone

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
