"""Authenticated real-device heartbeat ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.devices.auth import DevicePrincipal


class HeartbeatPayload(BaseModel):
    """A deliberately bounded liveness report; it has no flight controls."""

    model_config = ConfigDict(extra="forbid")
    battery_percent: int = Field(ge=0, le=100)
    health: Literal["healthy", "fault"]
    connected: bool


@dataclass(frozen=True)
class HeartbeatResult:
    eligible: bool
    reconcile_trigger: str | None


class HeartbeatRepository(Protocol):
    def record_heartbeat(self, principal: DevicePrincipal, heartbeat: HeartbeatPayload, received_at: datetime) -> dict: ...


class LakeReconciler(Protocol):
    def reconcile_lake(self, lake_id: str, trigger: str, expected_plan_id: str | None = None) -> object: ...


class HeartbeatService:
    def __init__(self, repository: HeartbeatRepository, autonomy: LakeReconciler) -> None:
        self._repository = repository
        self._autonomy = autonomy

    def record(self, principal: DevicePrincipal, heartbeat: dict | HeartbeatPayload, *, received_at: datetime | None = None) -> HeartbeatResult:
        value = heartbeat if isinstance(heartbeat, HeartbeatPayload) else HeartbeatPayload.model_validate(heartbeat)
        if principal.sequence is None:
            raise ValueError("heartbeat is missing its authenticated sequence")
        outcome = self._repository.record_heartbeat(principal, value, received_at or datetime.now(timezone.utc))
        eligible = bool(outcome.get("eligible"))
        lake_id = outcome.get("lake_id")
        transitioned = bool(outcome.get("eligibility_changed"))
        trigger = "heartbeat_recovery" if eligible and transitioned else None
        # The database transaction queues reconciliation together with the
        # capacity transition.  A leased worker invokes autonomy after commit.
        return HeartbeatResult(eligible=eligible, reconcile_trigger=trigger)
