from __future__ import annotations

from app.geo import destination_point
from app.models import LatLon


def circle_waypoints(
    center: LatLon,
    radius_m: float,
    n_points: int = 16,
    phase_offset_deg: float = 0.0,
    clockwise: bool = True,
) -> list[LatLon]:
    """Generate a patrol loop's waypoints around `center` at `radius_m`.

    `phase_offset_deg` and `clockwise` are the two knobs used by the engine's
    overlap-deconfliction rule (adjacent/overlapping patrol zones stagger
    phase and alternate direction so their closest-approach points don't
    coincide in time).
    """
    step_deg = 360.0 / n_points
    direction = 1.0 if clockwise else -1.0
    return [
        destination_point(center, phase_offset_deg + direction * i * step_deg, radius_m)
        for i in range(n_points)
    ]
