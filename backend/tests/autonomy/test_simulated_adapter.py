from __future__ import annotations

import pytest

from app.autonomy.models import InventoryDrone
from app.autonomy.outbox import CommandEnvelope
from app.coordination.engine import SimulationEngine
from app.models import Drone, DroneStatus, LatLon, RiskZone


def _zone(zone_id: str, at: LatLon = LatLon(47.58, -122.09)) -> RiskZone:
    return RiskZone(zone_id, at, [at, at, at, at], 1.0, {}, is_proxy=False)


def _engine() -> SimulationEngine:
    return SimulationEngine([Drone("d0", LatLon(47.579, -122.091), 1.0, DroneStatus.IDLE, None)], [_zone("old")], [])


def _inventory(source: str = "simulated") -> InventoryDrone:
    return InventoryDrone("d0", "station-1", "lake-1", source, "circulating", 90, "healthy", "connected", False, 0)  # type: ignore[arg-type]


def _command(zone_id: str = "old", version: int = 1) -> CommandEnvelope:
    return CommandEnvelope("key-" + str(version), "d0", "station-1", "lake-1", version, "apply_assignment", "d0:" + zone_id, {"zone_plan_cell_id": zone_id})


def test_simulated_adapter_rejects_real_inventory_before_mutating_engine():
    from app.autonomy.adapters.simulated import SimulatedFleetAdapter
    from app.autonomy.adapters.base import TransportIsolationError

    engine = _engine()
    adapter = SimulatedFleetAdapter(engine, {"d0": _inventory("real")})

    with pytest.raises(TransportIsolationError):
        adapter.publish(_command())

    assert engine.drones[0].assigned_zone == "old"
    assert engine.acknowledged_desired_versions == {}


def test_apply_plan_swaps_validated_state_atomically_and_acknowledges_after_success():
    engine = _engine()
    engine._patrol_waypoints["d0"] = [LatLon(47.58, -122.09)]
    engine._patrol_index["d0"] = 0

    engine.apply_plan([_zone("new")], {"d0": "new"}, {"d0": 4})

    assert [zone.zone_id for zone in engine.zones] == ["new"]
    assert engine.drones[0].assigned_zone == "new"
    assert engine.targets["d0"] == LatLon(47.58, -122.09)
    assert engine._patrol_waypoints == {}
    assert engine.acknowledged_desired_versions == {"d0": 4}


def test_apply_plan_rejects_bad_assignment_without_partial_mutation():
    engine = _engine()
    before_zones = engine.zones[:]
    before_target = dict(engine.targets)

    with pytest.raises(ValueError, match="unknown zone"):
        engine.apply_plan([_zone("new")], {"d0": "missing"}, {"d0": 2})

    assert engine.zones == before_zones
    assert engine.targets == before_target
    assert engine.drones[0].assigned_zone == "old"
    assert engine.acknowledged_desired_versions == {}


def test_simulated_adapter_applies_command_then_returns_receipt():
    from app.autonomy.adapters.simulated import SimulatedFleetAdapter

    engine = _engine()
    adapter = SimulatedFleetAdapter(engine, {"d0": _inventory()})

    receipt = adapter.publish(_command(version=3))

    assert receipt.inventory_id == "d0"
    assert receipt.desired_state_version == 3
    assert engine.acknowledged_desired_versions["d0"] == 3
