"""Release-gate failure drills for the LakeSafe security boundary.

These tests deliberately exercise the production-facing seams instead of
duplicating unit-test internals.  A failed drill blocks release: each case
documents the safe state that must remain true when a dependency fails.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from shapely.geometry import Polygon

from app.access.policy import Permission, require_station_access
from app.access.principal import Principal, StationMembership, StationRole
from app.autonomy.outbox import CommandEnvelope, OutboxPublisher
from app.autonomy.repository import InMemoryAutonomyRepository
from app.autonomy.safety import RealFleetStatus, classify_real_fleet_status, real_heartbeat_status
from app.devices.monitor import HeartbeatMonitor
from app.risk_zones.plan_builder import RiskDataUnavailable
from app.risk_zones.plan_repository import InMemoryRiskPlanRepository
from app.risk_zones.plan_service import PlanBuildRequest, RiskPlanService
from app.risk_zones.snapshots import build_snapshot


NOW = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)
SHORELINE = Polygon([(-122.10, 47.57), (-122.08, 47.57), (-122.08, 47.59), (-122.10, 47.59)])


def _command(version: int, command_id: str) -> CommandEnvelope:
    return CommandEnvelope(
        f"key-{version}", "drone-1", "station-1", "lake-1", version,
        "apply_assignment", f"assignment-{version}",
        {"source": "simulated", "zone_plan_cell_id": f"cell-{version}"}, command_id,
    )


def test_stale_socrata_snapshot_keeps_the_last_active_plan() -> None:
    """A fetch failure is quarantined and cannot replace the active plan."""
    repository = InMemoryRiskPlanRepository(active_id="last-known-good")
    stale = build_snapshot("lake-1", "station-1", (ConnectionError("Socrata unavailable"),), SHORELINE, NOW, NOW)
    service = RiskPlanService(repository, lambda _: stale, lambda _: SHORELINE)

    assert stale.status == "quarantined"
    assert stale.failure_reason == "connector_fetch_failure"
    with pytest.raises(RiskDataUnavailable, match="connector_fetch_failure"):
        service.rebuild(PlanBuildRequest("lake-1", "stale-snapshot", 2, 0, "last-known-good"))
    assert repository.active_id == "last-known-good"


def test_schema_drift_quarantines_only_the_new_snapshot() -> None:
    """Bad incoming schemas cannot invalidate an already active plan."""
    repository = InMemoryRiskPlanRepository(active_id="last-known-good")
    drifted = build_snapshot("lake-1", "station-1", (ValueError("schema drift"),), SHORELINE, NOW, NOW)
    service = RiskPlanService(repository, lambda _: drifted, lambda _: SHORELINE)

    assert drifted.status == "quarantined"
    assert drifted.failure_reason == "connector_schema_failure"
    with pytest.raises(RiskDataUnavailable, match="connector_schema_failure"):
        service.rebuild(PlanBuildRequest("lake-1", "drifted-snapshot", 2, 0, "last-known-good"))
    assert repository.active_id == "last-known-good"


def test_heartbeat_loss_removes_pending_capacity_and_marks_coverage_degraded() -> None:
    class CapacityRepository:
        def __init__(self) -> None:
            self.inventory = [
                {"inventory_id": "drone-1", "health": "healthy", "connectivity": "connected", "maintenance_due": False, "battery_percent": 90},
                {"inventory_id": "drone-2", "health": "healthy", "connectivity": "connected", "maintenance_due": False, "battery_percent": 90},
            ]
            self.heartbeats = {"drone-1": NOW - timedelta(seconds=2), "drone-2": NOW - timedelta(seconds=2)}
            self.jobs: list[dict[str, str]] = []
            self.expired_drone_ids: tuple[str, ...] = ()

        def expire_stale_eligible_real(self, now: datetime, ttl_seconds: int) -> tuple[str, ...]:
            expired = tuple(
                row["inventory_id"] for row in self.inventory
                if (now - self.heartbeats[row["inventory_id"]]).total_seconds() > ttl_seconds
            )
            if expired:
                self.expired_drone_ids = expired
                self.inventory = [row for row in self.inventory if row["inventory_id"] not in expired]
                self.jobs.append({"lake_id": "lake-1", "trigger": "heartbeat_expired"})
            return ("lake-1",) if expired else ()

        def claim_real_capacity_reconciliations(self) -> list[dict[str, str]]:
            jobs, self.jobs = self.jobs, []
            return jobs

        def complete_real_capacity_reconciliation(self, item: dict[str, str]) -> bool:
            return item["trigger"] == "heartbeat_expired"

        def release_real_capacity_reconciliation(self, item: dict[str, str]) -> bool:
            return False

    class CapacityReconciler:
        def __init__(self, repository: CapacityRepository) -> None:
            self.repository, self.status = repository, None

        def reconcile_lake(self, lake_id: str, trigger: str, expected_plan_id=None) -> None:
            del lake_id, expected_plan_id
            eligible, _ = real_heartbeat_status(self.repository.inventory, self.repository.heartbeats, now=NOW, minimum_battery=30)
            self.status = classify_real_fleet_status(
                RealFleetStatus("pending_ack", active_assignments=("drone-1",), pending_assignments=("drone-2",)),
                expired_drone_ids=self.repository.expired_drone_ids if trigger == "heartbeat_expired" and eligible is True else (),
                safe_return_required=False,
            )

    repository = CapacityRepository()
    repository.heartbeats["drone-2"] = NOW - timedelta(seconds=16)
    reconciler = CapacityReconciler(repository)

    assert HeartbeatMonitor(repository, reconciler, ttl_seconds=15).scan(NOW) == ("lake-1",)
    assert repository.expired_drone_ids == ("drone-2",)
    assert [row["inventory_id"] for row in repository.inventory] == ["drone-1"]
    assert reconciler.status is not None
    assert reconciler.status.autonomy == "degraded"
    assert reconciler.status.active_assignments == ("drone-1",)
    assert reconciler.status.pending_assignments == ()


def test_gateway_failure_releases_new_work_without_losing_acknowledged_state() -> None:
    class FailingAdapter:
        def publish(self, command: CommandEnvelope) -> object:
            raise RuntimeError("gateway unavailable")

    repository = InMemoryAutonomyRepository(station_id="station-1")
    acknowledged, pending = _command(3, "ack-3"), _command(4, "pending-4")
    repository.enqueue(acknowledged)
    assert repository.claim_pending(1)[0].command_id == "ack-3"
    assert repository.acknowledge("ack-3") is True
    repository.enqueue(pending)

    assert OutboxPublisher(repository, FailingAdapter()).publish_pending() == ()
    assert repository.acknowledged_version("drone-1") == 3
    assert [command.command_id for command in repository.pending()] == ["pending-4"]
    assert repository.claim_pending(1)[0].command_id == "pending-4"


def test_partial_acknowledgement_is_degraded_coverage_not_active() -> None:
    result = classify_real_fleet_status(
        RealFleetStatus("active", active_assignments=("drone-1",), pending_assignments=("drone-2",), last_acknowledged_versions={"drone-1": 4}),
        expired_drone_ids=("drone-2",), safe_return_required=False,
    )

    assert result.autonomy == "degraded"
    assert result.active_assignments == ("drone-1",)
    assert result.last_acknowledged_versions == {"drone-1": 4}


def test_verification_revocation_closes_operational_access() -> None:
    revoked = Principal(
        "officer-1", "officer@example.gov", "aal2", "officer", "revoked",
        (StationMembership("station-1", "Station", "active", frozenset({StationRole.VIEWER})),),
    )

    with pytest.raises(HTTPException, match="Verified station access"):
        require_station_access(revoked, "station-1", Permission.READ_OPERATIONS)


def test_public_sanitization_failure_prevents_publication() -> None:
    from app.main import public_patrol_payload

    with pytest.raises(Exception):
        public_patrol_payload({
            "lake_id": "lake-sammamish", "generalized_zone": "north basin",
            "public_state": "patrolling", "observed_bucket": "2026-07-30T12:00:00Z",
            "published_at": "2026-07-30T12:05:00Z", "latitude": 47.6,
        })
