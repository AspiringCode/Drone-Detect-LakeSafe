from __future__ import annotations

from app.coordination.assignment import assign_zones
from app.models import Drone, DroneStatus, RiskZone


def needs_return(drone: Drone, reserve: float = 0.25) -> bool:
    return drone.battery < reserve


def reassign_on_low_battery(
    drones: list[Drone],
    zones: list[RiskZone],
    assignment: dict[str, str | None],
) -> dict[str, str | None]:
    updated = dict(assignment)
    zones_to_cover: set[str] = set()
    for drone in drones:
        if needs_return(drone):
            if updated.get(drone.drone_id):
                zones_to_cover.add(updated[drone.drone_id])
            updated[drone.drone_id] = None
            drone.assigned_zone = None
            drone.status = DroneStatus.RETURNING

    available = [
        drone
        for drone in drones
        if not needs_return(drone) and updated.get(drone.drone_id) is None
    ]
    target_zones = [zone for zone in zones if zone.zone_id in zones_to_cover]
    reassigned = assign_zones(available, target_zones)
    updated.update(reassigned)
    for drone in drones:
        if drone.drone_id in reassigned:
            drone.assigned_zone = reassigned[drone.drone_id]
    return updated
