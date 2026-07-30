"""Authorized real-fleet safety policy endpoints (never piloting endpoints)."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from time import monotonic
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.access.policy import Permission, require_recent_mfa, require_station_access
from app.access.principal import Principal, get_principal
from app.autonomy.safety import get_safety_repository, mark_gateway_unavailable
from app.devices.reconciler import RealCapacityReconciler
from app.stations.models import AuditEventCreate


router = APIRouter(prefix="/api/stations/{station_id}/lakes/{lake_id}/safety", tags=["real-fleet-safety"])
_RATE_WINDOW_SECONDS = 60.0
_RATE_LIMIT = 5
_recent_actions: dict[tuple[str, str, str], deque[float]] = defaultdict(deque)


class _ReasonInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def _meaningful_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A reason is required")
        return value.strip()


class AutonomyPolicyInput(_ReasonInput):
    enabled: bool


class SafeReturnInput(_ReasonInput):
    pass


def get_real_capacity_reconciler() -> RealCapacityReconciler:
    from app.main import app
    return RealCapacityReconciler(app)


def _station_access(principal: Principal, station_id: str) -> None:
    try:
        require_station_access(principal, station_id, Permission.CHANGE_FLEET_SAFETY)
    except HTTPException as exc:
        if exc.status_code == 403 and not any(item.station_id == station_id for item in principal.memberships):
            raise HTTPException(status_code=404, detail="Lake not found") from exc
        raise


def _rate_limit(principal: Principal, lake_id: str, action: str) -> None:
    now = monotonic()
    key = (principal.user_id, lake_id, action)
    queue = _recent_actions[key]
    while queue and queue[0] <= now - _RATE_WINDOW_SECONDS:
        queue.popleft()
    if len(queue) >= _RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Safety action rate limit exceeded")
    queue.append(now)


def _audit(repository, principal: Principal, station_id: str, lake_id: str, action: str, reason: str, resulting_state: dict) -> None:
    repository.append_audit(AuditEventCreate(
        actor_user_id=principal.user_id, actor_device_id=None, request_id=str(uuid4()),
        action=action, decision="allowed", reason=reason, station_id=station_id,
        lake_id=lake_id, resulting_state=resulting_state, source_context={"source": "real"},
    ))


def _reconcile(reconciler, lake_id: str, trigger: str, outcome: dict) -> dict:
    try:
        reconciler.reconcile_lake(lake_id, trigger)
    except Exception:
        # Policy is durable even when the transport is down. Do not tell the
        # caller that a desired change is active until a device acknowledges it.
        return {**outcome, **mark_gateway_unavailable(_status_from(outcome)).as_dict()}
    return outcome


def _status_from(value: dict):
    from app.autonomy.safety import RealFleetStatus
    state = value.get("autonomy", "pending_ack")
    if state not in {"paused", "pending_ack", "active", "degraded", "safe_return_requested", "gateway_unavailable"}:
        state = "pending_ack"
    return RealFleetStatus(state, tuple(value.get("active_assignments") or ()), tuple(value.get("pending_assignments") or ()), value.get("last_acknowledged_versions") or {})


@router.post("/autonomy", status_code=status.HTTP_202_ACCEPTED)
def set_real_autonomy(station_id: str, lake_id: str, value: AutonomyPolicyInput, principal: Principal = Depends(get_principal)) -> dict:
    _station_access(principal, station_id)
    require_recent_mfa(principal, timedelta(minutes=10))
    repository = get_safety_repository()
    if not repository.lake_belongs_to_station(station_id, lake_id):
        raise HTTPException(status_code=404, detail="Lake not found")
    _rate_limit(principal, lake_id, "autonomy")
    outcome = repository.set_real_autonomy(station_id, lake_id, value.enabled, value.reason, principal.user_id)
    _audit(repository, principal, station_id, lake_id, "real_fleet.autonomy", value.reason, outcome)
    return _reconcile(get_real_capacity_reconciler(), lake_id, "real_safety_policy_changed", outcome)


@router.post("/safe-return", status_code=status.HTTP_202_ACCEPTED)
def safe_return(station_id: str, lake_id: str, value: SafeReturnInput, principal: Principal = Depends(get_principal)) -> dict:
    _station_access(principal, station_id)
    require_recent_mfa(principal, timedelta(minutes=10))
    repository = get_safety_repository()
    if not repository.lake_belongs_to_station(station_id, lake_id):
        raise HTTPException(status_code=404, detail="Lake not found")
    _rate_limit(principal, lake_id, "safe_return")
    outcome = repository.request_safe_return(station_id, lake_id, value.reason, principal.user_id)
    _audit(repository, principal, station_id, lake_id, "real_fleet.safe_return", value.reason, outcome)
    return _reconcile(get_real_capacity_reconciler(), lake_id, "real_safe_return_requested", outcome)
