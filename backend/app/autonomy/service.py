"""Lake reconciliation: plan first, then atomically commit desired state and outbox."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.autonomy.eligibility import eligible_simulated_drones
from app.autonomy.models import ZonePlan
from app.autonomy.outbox import CommandEnvelope
from app.autonomy.planner import plan_assignments


class ReconcileConflict(RuntimeError):
    """The active plan changed twice while reconciliation was being built."""


@dataclass(frozen=True)
class ReconcileResult:
    plan_id: str
    assignment_count: int
    command_count: int


def _idempotency_key(plan_id: str, inventory_id: str, version: int) -> str:
    return hashlib.sha256(f"{plan_id}:{inventory_id}:{version}:apply_assignment".encode()).hexdigest()


class AutonomyService:
    def __init__(self, repository, *, build_plan, validate_plan, publish) -> None:
        self._repository = repository
        self._build_plan = build_plan
        self._validate_plan = validate_plan
        self._publish = publish

    def reconcile_lake(self, lake_id: str, trigger: str, expected_plan_id: str | None) -> ReconcileResult:
        del trigger  # Recorded by the caller/audit layer; it does not alter safety policy.
        expected = expected_plan_id
        for _ in range(2):
            state = self._repository.lake_fleet_state(lake_id)
            capacity = len(eligible_simulated_drones(state.drones, state.station_id, lake_id, state.fleet_policy))
            plan: ZonePlan = self._build_plan(lake_id, capacity, state.fleet_policy.safety_reserve, expected)
            if plan.lake_id != lake_id or plan.station_id != state.station_id:
                raise ValueError("candidate plan does not belong to lake fleet")
            self._validate_plan(plan)
            assignments = plan_assignments(state.drones, plan, state.prior_assignments)
            commands = tuple(CommandEnvelope(
                _idempotency_key(plan.plan_id, assignment.inventory_id, assignment.desired_state_version),
                assignment.inventory_id, state.station_id, lake_id, assignment.desired_state_version,
                "apply_assignment", assignment.inventory_id + ":" + assignment.zone_id,
                {"zone_plan_cell_id": assignment.zone_id, "plan_id": plan.plan_id},
            ) for assignment in assignments)
            if self._repository.commit_plan_commands(expected, plan.plan_id, assignments, commands):
                self._publish()
                return ReconcileResult(plan.plan_id, len(assignments), len(commands))
            expected = self._repository.active_plan_id(lake_id)
        raise ReconcileConflict("active plan changed during reconciliation")


__all__ = ["AutonomyService", "ReconcileConflict", "ReconcileResult"]
