"""Persistence boundary for atomic autonomous desired-state commits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.autonomy.models import FleetPolicy, InventoryDrone, PriorAssignment
from app.autonomy.outbox import CommandEnvelope, StaleDesiredState


@dataclass(frozen=True)
class LakeFleetState:
    station_id: str
    fleet_policy: FleetPolicy
    drones: tuple[InventoryDrone, ...]
    prior_assignments: tuple[PriorAssignment, ...]


class AutonomyRepository(Protocol):
    def lake_fleet_state(self, lake_id: str) -> LakeFleetState: ...
    def commit_plan_commands(self, expected_plan_id: str | None, candidate_plan_id: str, assignments, commands: tuple[CommandEnvelope, ...]) -> bool: ...
    def active_plan_id(self, lake_id: str) -> str | None: ...
    def claim_pending(self, limit: int) -> tuple[CommandEnvelope, ...]: ...
    def claim_real_pending(self, station_id: str, lake_id: str, limit: int) -> tuple[CommandEnvelope, ...]: ...
    def acknowledge(self, command_id: str) -> bool: ...
    def release(self, command_id: str) -> bool: ...


class InMemoryAutonomyRepository:
    """Deterministic transactional model used only in unit tests/local demos."""

    def __init__(self, *, station_id: str, fleet_policy: FleetPolicy = FleetPolicy(), drones: tuple[InventoryDrone, ...] = (), prior_assignments: tuple[PriorAssignment, ...] = (), active_plan_id: str | None = None, events: list[str] | None = None) -> None:
        self._state = LakeFleetState(station_id, fleet_policy, drones, prior_assignments)
        self._active_plan_id = active_plan_id
        self._commands: dict[str, CommandEnvelope] = {}
        self._events = events

    def lake_fleet_state(self, lake_id: str) -> LakeFleetState:
        if lake_id != "lake-1":
            raise KeyError(lake_id)
        return self._state

    def active_plan_id(self, lake_id: str) -> str | None:
        self.lake_fleet_state(lake_id)
        return self._active_plan_id

    def commit_plan_commands(self, expected_plan_id: str | None, candidate_plan_id: str, assignments, commands: tuple[CommandEnvelope, ...]) -> bool:
        if self._active_plan_id != expected_plan_id:
            return False
        staged = dict(self._commands)
        for command in commands:
            existing = staged.get(command.idempotency_key)
            if existing:
                if existing.desired_state_version != command.desired_state_version:
                    raise StaleDesiredState("idempotency key collision")
                continue
            newest = max((item.desired_state_version for item in staged.values() if item.inventory_id == command.inventory_id), default=0)
            if command.desired_state_version < newest:
                raise StaleDesiredState("desired state version is stale")
            staged[command.idempotency_key] = command
        self._active_plan_id = candidate_plan_id
        self._commands = staged
        if self._events is not None:
            self._events.append("commit-plan-assignments-outbox")
        return True

    def enqueue(self, command: CommandEnvelope) -> None:
        self.commit_plan_commands(self._active_plan_id, self._active_plan_id or "local", (), (command,))

    def pending(self) -> tuple[CommandEnvelope, ...]:
        return tuple(item for item in self._commands.values() if item.status == "pending")

    def claim_pending(self, limit: int) -> tuple[CommandEnvelope, ...]:
        claimed: list[CommandEnvelope] = []
        for key, command in sorted(self._commands.items()):
            if len(claimed) >= limit or command.status != "pending":
                continue
            updated = CommandEnvelope(**{**command.__dict__, "command_id": command.command_id or key, "status": "claimed"})
            self._commands[key] = updated
            claimed.append(updated)
        return tuple(claimed)

    def claim_real_pending(self, station_id: str, lake_id: str, limit: int) -> tuple[CommandEnvelope, ...]:
        claimed: list[CommandEnvelope] = []
        for key, command in sorted(self._commands.items()):
            if (len(claimed) >= limit or command.status != "pending" or command.station_id != station_id
                    or command.lake_id != lake_id or command.payload.get("source") != "real"):
                continue
            updated = CommandEnvelope(**{**command.__dict__, "command_id": command.command_id or key, "status": "claimed"})
            self._commands[key] = updated
            claimed.append(updated)
        return tuple(claimed)

    def acknowledge(self, command_id: str) -> bool:
        for key, command in self._commands.items():
            if (command.command_id or key) == command_id and command.status == "claimed":
                self._commands[key] = CommandEnvelope(**{**command.__dict__, "command_id": command_id, "status": "acknowledged"})
                return True
        return False

    def release(self, command_id: str) -> bool:
        for key, command in self._commands.items():
            if (command.command_id or key) == command_id and command.status == "claimed":
                self._commands[key] = CommandEnvelope(**{**command.__dict__, "command_id": command_id, "status": "pending"})
                return True
        return False

    def acknowledged_version(self, inventory_id: str) -> int:
        return max((item.desired_state_version for item in self._commands.values() if item.inventory_id == inventory_id and item.status == "acknowledged"), default=0)


class SupabaseAutonomyRepository:
    """Production adapter: all multi-row state changes use service-only RPCs."""

    def __init__(self, client) -> None:
        self._client = client

    def commit_plan_commands(self, expected_plan_id: str | None, candidate_plan_id: str, assignments, commands: tuple[CommandEnvelope, ...]) -> bool:
        lake_ids = {command.lake_id for command in commands}
        if len(lake_ids) != 1:
            raise ValueError("a reconciliation may cover exactly one lake")
        normalized_assignments = [
            dict(item) if isinstance(item, dict) else {
                "inventory_id": item.inventory_id,
                "zone_plan_cell_id": item.zone_id,
                "desired_state_version": item.desired_state_version,
            }
            for item in assignments
        ]
        assignment_keys = {
            (str(item.get("inventory_id")), int(item.get("desired_state_version", 0)))
            for item in normalized_assignments
        }
        command_keys = {(item.inventory_id, item.desired_state_version) for item in commands}
        if len(assignment_keys) != len(normalized_assignments) or len(command_keys) != len(commands):
            raise ValueError("assignments and commands must be unique")
        if assignment_keys != command_keys or any(item.command_type != "apply_assignment" for item in commands):
            raise ValueError("every assignment requires exactly one matching apply command")
        assignment_cells = {
            (str(item["inventory_id"]), int(item["desired_state_version"])): str(item["zone_plan_cell_id"])
            for item in normalized_assignments
        }
        if any(item.payload.get("zone_plan_cell_id") != assignment_cells[(item.inventory_id, item.desired_state_version)] for item in commands):
            raise ValueError("commands must match their assignment cell")
        payload = {
            "p_lake_id": lake_ids.pop(), "p_expected_plan_id": expected_plan_id,
            "p_candidate_plan_id": candidate_plan_id,
            "p_assignments": normalized_assignments,
            "p_commands": [{
                "inventory_id": item.inventory_id, "zone_assignment_id": item.assignment_id,
                "desired_state_version": item.desired_state_version, "command_type": item.command_type,
                "payload": item.payload, "idempotency_key": item.idempotency_key,
            } for item in commands],
        }
        return self._client.rpc("commit_autonomy_reconciliation", payload).execute().data is True

    def claim_pending(self, limit: int) -> tuple[CommandEnvelope, ...]:
        rows = self._client.rpc("claim_autonomy_outbox", {"p_limit": limit}).execute().data or []
        return self._commands_from_rows(rows)

    def claim_real_pending(self, station_id: str, lake_id: str, limit: int) -> tuple[CommandEnvelope, ...]:
        rows = self._client.rpc("claim_real_autonomy_outbox", {"p_station_id": station_id, "p_lake_id": lake_id, "p_limit": limit}).execute().data or []
        return self._commands_from_rows(rows)

    @staticmethod
    def _commands_from_rows(rows) -> tuple[CommandEnvelope, ...]:
        return tuple(CommandEnvelope(
            row["idempotency_key"], str(row["inventory_id"]), str(row["station_id"]), row["lake_id"],
            row["desired_state_version"], row["command_type"], str(row["zone_assignment_id"]) if row.get("zone_assignment_id") else None,
            row.get("payload") or {}, str(row["command_id"]), row["status"],
        ) for row in rows)

    def acknowledge(self, command_id: str) -> bool:
        return self._client.rpc("acknowledge_autonomy_command", {"p_command_id": command_id}).execute().data is True

    def release(self, command_id: str) -> bool:
        return self._client.rpc("release_autonomy_command", {"p_command_id": command_id}).execute().data is True


__all__ = ["AutonomyRepository", "InMemoryAutonomyRepository", "LakeFleetState", "SupabaseAutonomyRepository"]
