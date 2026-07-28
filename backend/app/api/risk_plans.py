"""Stored risk-plan status and station-admin refresh requests.

The GET endpoint deliberately reads the active immutable plan only.  Building
plans belongs to the background worker so viewing a lake cannot trigger an
external data fetch or replace an operational plan.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.access.policy import Permission, require_station_access
from app.access.principal import Principal, get_principal
from app.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from app.risk_zones.plan_builder import RiskDataUnavailable
from app.risk_zones.plan_repository import SupabaseRiskPlanRepository
from app.risk_zones.plan_service import PlanConflict
from app.risk_zones.validation import PlanValidationError
from app.risk_zones.setup_worker import RiskPlanSetupService, RiskRefreshWorker

router = APIRouter(prefix="/api/stations/{station_id}/lakes/{lake_id}", tags=["risk-plans"])


def get_risk_plan_repository() -> SupabaseRiskPlanRepository:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("Supabase service credentials are not configured")
    from supabase import create_client
    return SupabaseRiskPlanRepository(create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY))


def get_risk_refresh_worker() -> RiskRefreshWorker | None:
    """Return a worker only when a concrete rebuild service is configured.

    This keeps development/test startup from creating duplicate no-op loops;
    production supplies the reviewed-source rebuild adapter on the repository.
    """
    try:
        repository = get_risk_plan_repository()
    except RuntimeError:
        return None
    required = ("claim_queued_lakes", "claim_due_source_lakes", "complete_refresh", "fail_refresh", "rebuild_context", "persist_snapshot")
    if not all(callable(getattr(repository, name, None)) for name in required):
        # Route-level fakes intentionally expose only read/queue methods.
        return None
    return RiskRefreshWorker(repository, RiskPlanSetupService(repository).rebuild_lake)


def _require_owned_lake(repository, principal: Principal, station_id: str, lake_id: str, permission: Permission) -> None:
    # Resolve ownership before permission handling. A lake at another station
    # is intentionally indistinguishable from a nonexistent lake.
    if repository.lake_station_id(lake_id) != station_id:
        raise HTTPException(status_code=404, detail="Lake not found")
    require_station_access(principal, station_id, permission)


def _translate_plan_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PlanConflict):
        return HTTPException(status_code=409, detail="Risk plan changed; retry the refresh")
    if isinstance(exc, PlanValidationError):
        return HTTPException(status_code=422, detail="Risk plan geometry is invalid")
    if isinstance(exc, RiskDataUnavailable):
        return HTTPException(status_code=503, detail="Risk data is temporarily unavailable")
    return HTTPException(status_code=503, detail="Risk-plan service is unavailable")


@router.get("/zone-plan")
def active_zone_plan(station_id: str, lake_id: str, principal: Principal = Depends(get_principal)) -> dict:
    try:
        repository = get_risk_plan_repository()
        _require_owned_lake(repository, principal, station_id, lake_id, Permission.READ_OPERATIONS)
        plan = repository.active_plan(lake_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise _translate_plan_error(exc) from exc
    if plan is None:
        raise HTTPException(status_code=404, detail="No active risk plan")
    return plan


@router.post("/risk-refresh", status_code=status.HTTP_202_ACCEPTED)
def request_risk_refresh(station_id: str, lake_id: str, principal: Principal = Depends(get_principal)) -> dict:
    try:
        repository = get_risk_plan_repository()
        _require_owned_lake(repository, principal, station_id, lake_id, Permission.MANAGE_INVENTORY)
        repository.queue_lake(lake_id, "manual")
    except HTTPException:
        raise
    except Exception as exc:
        raise _translate_plan_error(exc) from exc
    return {"lake_id": lake_id, "status": "queued"}
