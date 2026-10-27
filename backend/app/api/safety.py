"""Authorized real-fleet safety policy endpoints (never piloting endpoints)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.access.policy import Permission, require_recent_mfa, require_station_access
from app.access.principal import Principal, get_principal
from app.autonomy.safety import get_safety_repository, mark_gateway_unavailable
from app.devices.reconciler import RealCapacityReconciler
from app.stations.models import AuditEventCreate
from app.correlation import get_request_id
from app.rate_limits import require_rate_limit


router = APIRouter(prefix="/api/stations/{station_id}/lakes/{lake_id}/safety", tags=["real-fleet-safety"])


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


def _record_failed_action(repository, principal: Principal, station_id: str, lake_id: str, request_id: str, action: str, reason: str) -> None:
    """A failed request never receives a false allowed audit event.

    The successful database RPC writes its own allowed event transactionally.
    A best-effort failure record must not replace the original operation error.
    """
    try:
        repository.append_audit(AuditEventCreate(
            actor_user_id=principal.user_id, actor_device_id=None, request_id=request_id,
            action=action, decision="failed", reason=reason, station_id=station_id,
            lake_id=lake_id, source_context={"source": "real", "phase": "mutation"},
        ))
    except Exception:
        pass


def _apply_high_impact(repository, principal: Principal, station_id: str, lake_id: str, request_id: str, action: str, reason: str, mutation):
    try:
        return mutation(request_id)
    except HTTPException:
        _record_failed_action(repository, principal, station_id, lake_id, request_id, action, reason)
        raise
    except Exception as exc:
        try:
            committed = repository.find_safety_action(request_id, action, principal.user_id, station_id, lake_id)
        except Exception as reconciliation_error:
            raise HTTPException(status_code=503, detail="Real fleet safety result is indeterminate") from reconciliation_error
        if committed is not None:
            return committed
        _record_failed_action(repository, principal, station_id, lake_id, request_id, action, reason)
        raise HTTPException(status_code=503, detail="Real fleet safety change is unavailable") from exc


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
def set_real_autonomy(station_id: str, lake_id: str, value: AutonomyPolicyInput, request: Request, principal: Principal = Depends(get_principal)) -> dict:
    _station_access(principal, station_id)
    require_recent_mfa(principal, timedelta(minutes=10), station_id=station_id)
    repository = get_safety_repository()
    if not repository.lake_belongs_to_station(station_id, lake_id):
        raise HTTPException(status_code=404, detail="Lake not found")
    require_rate_limit("safety.autonomy", principal, request, station_id=station_id, lake_id=lake_id)
    outcome = _apply_high_impact(
        repository, principal, station_id, lake_id, str(get_request_id(request)), "real_fleet.autonomy", value.reason,
        lambda request_id: repository.set_real_autonomy(station_id, lake_id, value.enabled, value.reason, principal.user_id, request_id),
    )
    return _reconcile(get_real_capacity_reconciler(), lake_id, "real_safety_policy_changed", outcome)


@router.post("/safe-return", status_code=status.HTTP_202_ACCEPTED)
def safe_return(station_id: str, lake_id: str, value: SafeReturnInput, request: Request, principal: Principal = Depends(get_principal)) -> dict:
    _station_access(principal, station_id)
    require_recent_mfa(principal, timedelta(minutes=10), station_id=station_id)
    repository = get_safety_repository()
    if not repository.lake_belongs_to_station(station_id, lake_id):
        raise HTTPException(status_code=404, detail="Lake not found")
    require_rate_limit("safety.safe_return", principal, request, station_id=station_id, lake_id=lake_id)
    outcome = _apply_high_impact(
        repository, principal, station_id, lake_id, str(get_request_id(request)), "real_fleet.safe_return", value.reason,
        lambda request_id: repository.request_safe_return(station_id, lake_id, value.reason, principal.user_id, request_id),
    )
    return _reconcile(get_real_capacity_reconciler(), lake_id, "real_safe_return_requested", outcome)
