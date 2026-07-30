"""In-process adapter for simulated inventory only."""

from __future__ import annotations

from collections.abc import Mapping

from app.autonomy.adapters.base import AdapterReceipt, TransportIsolationError
from app.autonomy.models import InventoryDrone
from app.autonomy.outbox import CommandEnvelope
from app.coordination.engine import SimulationEngine


class SimulatedFleetAdapter:
    """Apply durable desired state to a ``SimulationEngine`` without hardware I/O."""

    def __init__(self, engine: SimulationEngine, inventory: Mapping[str, InventoryDrone]) -> None:
        self._engine = engine
        self._inventory = dict(inventory)

    def publish(self, command: CommandEnvelope) -> AdapterReceipt:
        inventory = self._inventory.get(command.inventory_id)
        if inventory is None or inventory.source != "simulated":
            raise TransportIsolationError("simulated adapter accepts simulated inventory only")
        # ``SimulationEngine.apply_plan`` owns its complete runtime list.  It
        # cannot safely operate on a mixed runtime without overwriting real
        # drones' assignments, targets, or status, so fail closed before even
        # deriving a proposed assignment map.
        if any(drone.source != "simulated" for drone in self._engine.drones):
            raise TransportIsolationError("mixed runtime requires a separate real transport")
        if command.command_type == "return_to_reserve":
            # The durable transition releases lake ownership before this
            # command is published, so a reserve return is station-bound only.
            if inventory.station_id != command.station_id:
                raise TransportIsolationError("command does not belong to simulated inventory")
            self._engine.return_to_reserve(command.inventory_id, command.desired_state_version)
            return AdapterReceipt(command.inventory_id, command.desired_state_version, command.command_id)
        if command.command_type != "apply_assignment":
            raise TransportIsolationError("simulated adapter only applies autonomous assignments or safe return")
        if inventory.station_id != command.station_id or inventory.lake_id != command.lake_id:
            raise TransportIsolationError("command does not belong to simulated inventory")
        zone_id = command.payload.get("zone_plan_cell_id")
        if not isinstance(zone_id, str) or not zone_id:
            raise ValueError("apply assignment command needs a zone_plan_cell_id")

        assignments = {drone.drone_id: drone.assigned_zone for drone in self._engine.drones if drone.assigned_zone}
        assignments[command.inventory_id] = zone_id
        self._engine.apply_plan(
            self._engine.zones,
            assignments,
            {command.inventory_id: command.desired_state_version},
        )
        return AdapterReceipt(command.inventory_id, command.desired_state_version, command.command_id)


__all__ = ["SimulatedFleetAdapter"]
