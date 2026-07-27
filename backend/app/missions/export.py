"""Write a computed risk zone's patrol mission to a QGroundControl .plan file.

This is the only module in `app.missions` that touches the filesystem, so the
plan-building logic in `qgc_plan` stays purely testable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.missions.qgc_plan import build_patrol_plan
from app.models import LatLon
from app.risk_zones.shoreline import load_lake_polygon
from app.risk_zones.tessellation import compute_tessellated_zones

# Default patrol altitude. The resolution math in the project planning file puts
# reliable thermal classification at 8-15 m; 30 m is the *transit/patrol*
# altitude, with descent-to-investigate handled by the coordination layer.
DEFAULT_ALTITUDE_M = 30.0

# Degrees. ~0.0008 deg is roughly 88 m at this latitude - coarse enough to cut a
# 213-vertex shoreline down to a fence ArduPilot will accept, fine enough that
# the fence still hugs the lake.
DEFAULT_FENCE_TOLERANCE = 0.0008


def simplified_fence(lake_id: str, tolerance: float = DEFAULT_FENCE_TOLERANCE) -> list[LatLon]:
    """Return the lake outline reduced to a vertex count a fence can hold."""
    polygon = load_lake_polygon(lake_id).simplify(tolerance, preserve_topology=True)
    return [LatLon(lat, lon) for lon, lat in polygon.exterior.coords]


def export_zone_mission(
    lake_id: str,
    zone_index: int,
    drone_count: int,
    altitude_m: float,
    home: LatLon,
    output_path: Path,
    fence_simplify_tolerance: float = DEFAULT_FENCE_TOLERANCE,
) -> Path:
    """Compute `lake_id`'s zones and write zone `zone_index`'s patrol as a .plan."""
    zones = compute_tessellated_zones(lake_id, drone_count=drone_count, use_fixture=True)
    if not 0 <= zone_index < len(zones):
        raise IndexError(
            f"zone_index {zone_index} out of range; {lake_id} produced {len(zones)} zones"
        )

    zone = zones[zone_index]
    if zone.radius_m is None:
        raise ValueError(f"zone {zone.zone_id} has no patrol radius; cannot build a mission")

    plan = build_patrol_plan(
        center=zone.centroid,
        radius_m=zone.radius_m,
        altitude_m=altitude_m,
        home=home,
        fence_polygon=simplified_fence(lake_id, fence_simplify_tolerance),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(plan, indent=4), encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a risk zone's patrol as a QGC .plan")
    parser.add_argument("--lake-id", default="lake-sammamish")
    parser.add_argument("--zone-index", type=int, default=0)
    parser.add_argument("--drone-count", type=int, default=5)
    parser.add_argument("--altitude", type=float, default=DEFAULT_ALTITUDE_M)
    parser.add_argument("--home-lat", type=float, required=True)
    parser.add_argument("--home-lon", type=float, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    path = export_zone_mission(
        lake_id=args.lake_id,
        zone_index=args.zone_index,
        drone_count=args.drone_count,
        altitude_m=args.altitude,
        home=LatLon(args.home_lat, args.home_lon),
        output_path=args.out,
    )
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
