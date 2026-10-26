"""Authenticated real-device heartbeat ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.devices import live_positions
from app.devices.auth import DevicePrincipal


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    alt_m: float | None = Field(default=None, ge=-100, le=1000)


class HeartbeatPayload(BaseModel):
    """A deliberately bounded liveness report; it has no flight controls."""

    model_config = ConfigDict(extra="forbid")
    battery_percent: int = Field(ge=0, le=100)
    health: Literal["healthy", "fault"]
    connected: bool
    # Optional so position-less drones keep working; only feeds the live map.
    position: Position | None = None
    flight_status: Literal["idle", "en_route", "patrolling", "investigating", "returning", "charging"] = "idle"
    investigation_completed: str | None = Field(default=None, min_length=1, max_length=100)


@dataclass(frozen=True)
class HeartbeatResult:
    eligible: bool
    reconcile_trigger: str | None
    lake_id: str | None = None


class HeartbeatRepository(Protocol):
    def record_heartbeat(self, principal: DevicePrincipal, heartbeat: HeartbeatPayload, received_at: datetime) -> dict: ...


class LakeReconciler(Protocol):
    def reconcile_lake(self, lake_id: str, trigger: str, expected_plan_id: str | None = None) -> object: ...


class HeartbeatService:
    def __init__(self, repository: HeartbeatRepository, autonomy: LakeReconciler | None = None) -> None:
        self._repository = repository
        self._autonomy = autonomy

    def record(self, principal: DevicePrincipal, heartbeat: dict | HeartbeatPayload, *, received_at: datetime | None = None) -> HeartbeatResult:
        value = heartbeat if isinstance(heartbeat, HeartbeatPayload) else HeartbeatPayload.model_validate(heartbeat)
        if principal.sequence is None:
            raise ValueError("heartbeat is missing its authenticated sequence")
        received = received_at or datetime.now(timezone.utc)
        outcome = self._repository.record_heartbeat(principal, value, received)
        if value.investigation_completed:
            from app.devices.investigations import get_investigation_repository
            get_investigation_repository().call('complete_real_investigation', p_drone_id=principal.drone_id,
                p_credential_id=principal.credential_id,p_sequence=principal.sequence,p_alert_id=value.investigation_completed)
        eligible = bool(outcome.get("eligible"))
        lake_id = outcome.get("lake_id")
        transitioned = bool(outcome.get("eligibility_changed"))
        trigger = "heartbeat_recovery" if eligible and transitioned else None
        # The database transaction queues reconciliation together with the
        # capacity transition.  A leased worker invokes autonomy after commit.
        if value.position is not None and isinstance(lake_id, str):
            live_positions.record(lake_id, live_positions.real_drone(
                principal.drone_id, value.position.lat, value.position.lon, value.battery_percent, value.flight_status,
            ), received)
        return HeartbeatResult(eligible=eligible, reconcile_trigger=trigger, lake_id=lake_id if isinstance(lake_id, str) else None)
