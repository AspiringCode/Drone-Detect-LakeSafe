"""Eligibility policy; this never changes inventory state."""

from __future__ import annotations

from app.autonomy.models import FleetPolicy, InventoryDrone


def eligible_simulated_drones(
    drones: tuple[InventoryDrone, ...], station_id: str, lake_id: str, policy: FleetPolicy
) -> tuple[InventoryDrone, ...]:
    """Return deterministic safe capacity for one lake, retaining a reserve."""
    candidates = sorted(
        (
            drone for drone in drones
            if drone.station_id == station_id
            and drone.lake_id == lake_id
            and drone.source == "simulated"
            and drone.lifecycle in {"available", "circulating"}
            and drone.battery_percent >= policy.minimum_battery_percent
            and drone.health == "healthy"
            and drone.connectivity == "connected"
            and not drone.maintenance_due
        ),
        key=lambda drone: drone.inventory_id,
    )
    usable = max(0, len(candidates) - policy.safety_reserve)
    return tuple(candidates[:usable])
