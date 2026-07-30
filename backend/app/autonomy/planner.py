"""Deterministic desired-state planner for immutable active plan cells."""

from __future__ import annotations

from app.autonomy.models import DesiredAssignment, InventoryDrone, PriorAssignment, ZonePlan


def plan_assignments(
    drones: tuple[InventoryDrone, ...], plan: ZonePlan, prior_assignments: tuple[PriorAssignment, ...]
) -> tuple[DesiredAssignment, ...]:
    """Preserve surviving assignments, then fill hotspots before coverage.

    Inputs are immutable.  A desired state version changes only if a drone's
    assigned plan cell changes.
    """
    allowed_cells = {cell.cell_id for cell in plan.cells}
    drones_by_id = {drone.inventory_id: drone for drone in drones}
    prior_by_drone = {item.inventory_id: item for item in prior_assignments}
    claimed_cells: set[str] = set()
    results: list[DesiredAssignment] = []

    for drone_id in sorted(drones_by_id):
        prior = prior_by_drone.get(drone_id)
        if prior and prior.zone_id in allowed_cells and prior.zone_id not in claimed_cells:
            results.append(DesiredAssignment(drone_id, prior.zone_id, prior.desired_state_version))
            claimed_cells.add(prior.zone_id)

    available_cells = sorted(
        (cell for cell in plan.cells if cell.cell_id not in claimed_cells),
        key=lambda cell: (0 if cell.kind == "hotspot" else 1 if cell.kind == "coverage" else 2, -cell.risk_score, cell.cell_id),
    )
    unassigned_drones = [drone_id for drone_id in sorted(drones_by_id) if drone_id not in {item.inventory_id for item in results}]
    for drone_id, cell in zip(unassigned_drones, available_cells, strict=False):
        drone = drones_by_id[drone_id]
        prior = prior_by_drone.get(drone_id)
        version = drone.desired_state_version if prior and prior.zone_id == cell.cell_id else drone.desired_state_version + 1
        results.append(DesiredAssignment(drone_id, cell.cell_id, version))
    return tuple(sorted(results, key=lambda item: item.inventory_id))
