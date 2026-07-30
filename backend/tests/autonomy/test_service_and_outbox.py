from __future__ import annotations

import pytest

from app.autonomy.models import FleetPolicy, InventoryDrone, PriorAssignment, ZoneCell, ZonePlan


def _drone(drone_id: str, version: int = 0) -> InventoryDrone:
    return InventoryDrone(drone_id, "station-1", "lake-1", "simulated", "circulating", 90, "healthy", "connected", False, version)


def _plan(plan_id: str = "plan-2") -> ZonePlan:
    return ZonePlan(plan_id, "station-1", "lake-1", (ZoneCell("cell-1", "hotspot", 1.0),))


def test_reconcile_orders_plan_before_publish():
    from app.autonomy.repository import InMemoryAutonomyRepository
    from app.autonomy.service import AutonomyService

    events: list[str] = []
    repository = InMemoryAutonomyRepository(
        station_id="station-1", fleet_policy=FleetPolicy(safety_reserve=0), drones=(_drone("d1"),), active_plan_id="plan-1", events=events,
    )
    service = AutonomyService(
        repository,
        build_plan=lambda *_: events.append("build") or _plan(),
        validate_plan=lambda _: events.append("validate"),
        publish=lambda: events.append("publish"),
    )

    service.reconcile_lake("lake-1", "capacity_enter", "plan-1")

    assert events == ["build", "validate", "commit-plan-assignments-outbox", "publish"]
    assert len(repository.pending()) == 1


def test_duplicate_and_stale_desired_versions_are_rejected():
    from app.autonomy.outbox import CommandEnvelope, StaleDesiredState
    from app.autonomy.repository import InMemoryAutonomyRepository

    repository = InMemoryAutonomyRepository(station_id="station-1")
    command = CommandEnvelope("c5", "d1", "station-1", "lake-1", 5, "apply_assignment", "assignment-1", {"zone_id": "z1"})
    repository.enqueue(command)
    repository.enqueue(command)

    assert len(repository.pending()) == 1
    with pytest.raises(StaleDesiredState):
        repository.enqueue(CommandEnvelope("c4", "d1", "station-1", "lake-1", 4, "apply_assignment", "assignment-2", {"zone_id": "z1"}))


def test_adapter_failure_leaves_command_pending_and_acknowledgement_behind_desired():
    from app.autonomy.outbox import CommandEnvelope, OutboxPublisher
    from app.autonomy.repository import InMemoryAutonomyRepository

    repository = InMemoryAutonomyRepository(station_id="station-1", drones=(_drone("d1"),))
    repository.enqueue(CommandEnvelope("c1", "d1", "station-1", "lake-1", 1, "apply_assignment", "assignment-1", {}))
    publisher = OutboxPublisher(repository, lambda _: (_ for _ in ()).throw(RuntimeError("adapter unavailable")))

    assert publisher.publish_pending() == ()
    assert repository.pending()[0].status == "pending"
    assert repository.acknowledged_version("d1") == 0
