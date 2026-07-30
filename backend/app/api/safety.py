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
from app.audit import AuditEvent, AuditUnavailable, record_high_impact
from app.autonomy.safety import get_safety_repository, mark_gateway_unavailable
from app.devices.reconciler import RealCapacityReconciler


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


def _station_access(principal: Principal, station_id: str, permission: Permission = Permission.CHANGE_FLEET_SAFETY) -> None:
    try:
        require_station_access(principal, station_id, permission)
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


class _RepositoryAuditSink:
    """Adapts the service-only repository to the typed audit writer boundary."""

    def __init__(self, repository) -> None:
        self._repository = repository

    def record(self, event: AuditEvent) -> None:
        from app.stations.models import AuditEventCreate

        try:
            self._repository.append_audit(AuditEventCreate(
                actor_user_id=str(event.actor_user_id) if event.actor_user_id else None,
                actor_device_id=str(event.actor_device_id) if event.actor_device_id else None,
                request_id=str(event.request_id), action=event.action, decision=event.decision,
                reason=event.reason, station_id=str(event.station_id) if event.station_id else None,
                lake_id=event.lake_id, session_reference=event.session_reference,
                prior_state=event.prior_state, resulting_state=event.resulting_state,
                source_context=event.source_context,
            ))
        except Exception as exc:
            raise AuditUnavailable("Security audit persistence is unavailable") from exc


def _high_impact_event(principal: Principal, station_id: str, lake_id: str, action: str, reason: str, request: dict) -> AuditEvent:
    return AuditEvent(
        actor_user_id=principal.user_id, request_id=uuid4(), action=action,
        decision="allowed", reason=reason, station_id=station_id, lake_id=lake_id,
        resulting_state={"requested": request}, source_context={"source": "real", "phase": "pre-mutation"},
    )


def _record_before_high_impact(repository, event: AuditEvent, mutation):
    try:
        return record_high_impact(_RepositoryAuditSink(repository), event, mutation)
    except AuditUnavailable as exc:
        raise HTTPException(status_code=503, detail="Security audit service is unavailable") from exc


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


@router.get("/status")
def real_fleet_status(station_id: str, lake_id: str, principal: Principal = Depends(get_principal)) -> dict:
    """Read-only status for station members; this exposes no device controls or secrets."""
    _station_access(principal, station_id, Permission.READ_OPERATIONS)
    repository = get_safety_repository()
    if not repository.lake_belongs_to_station(station_id, lake_id):
        raise HTTPException(status_code=404, detail="Lake not found")
    try:
        return repository.real_fleet_status(station_id, lake_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Real fleet status is unavailable") from exc


@router.post("/autonomy", status_code=status.HTTP_202_ACCEPTED)
def set_real_autonomy(station_id: str, lake_id: str, value: AutonomyPolicyInput, principal: Principal = Depends(get_principal)) -> dict:
    _station_access(principal, station_id)
    require_recent_mfa(principal, timedelta(minutes=10))
    repository = get_safety_repository()
    if not repository.lake_belongs_to_station(station_id, lake_id):
        raise HTTPException(status_code=404, detail="Lake not found")
    _rate_limit(principal, lake_id, "autonomy")
    outcome = _record_before_high_impact(
        repository,
        _high_impact_event(principal, station_id, lake_id, "real_fleet.autonomy", value.reason, {"enabled": value.enabled}),
        lambda: repository.set_real_autonomy(station_id, lake_id, value.enabled, value.reason, principal.user_id),
    )
    return _reconcile(get_real_capacity_reconciler(), lake_id, "real_safety_policy_changed", outcome)


@router.post("/safe-return", status_code=status.HTTP_202_ACCEPTED)
def safe_return(station_id: str, lake_id: str, value: SafeReturnInput, principal: Principal = Depends(get_principal)) -> dict:
    _station_access(principal, station_id)
    require_recent_mfa(principal, timedelta(minutes=10))
    repository = get_safety_repository()
    if not repository.lake_belongs_to_station(station_id, lake_id):
        raise HTTPException(status_code=404, detail="Lake not found")
    _rate_limit(principal, lake_id, "safe_return")
    outcome = _record_before_high_impact(
        repository,
        _high_impact_event(principal, station_id, lake_id, "real_fleet.safe_return", value.reason, {}),
        lambda: repository.request_safe_return(station_id, lake_id, value.reason, principal.user_id),
    )
    return _reconcile(get_real_capacity_reconciler(), lake_id, "real_safe_return_requested", outcome)
