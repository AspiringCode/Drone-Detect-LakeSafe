from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.access.principal import Principal, get_principal
from app.access.repository import get_access_repository
from app.stations.models import StationReviewCreate
from app.stations.repository import WorkflowConflict, get_workflow_repository

router = APIRouter(prefix="/api/internal/reviews", tags=["reviews"])


class StationDecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str
    note: str | None = Field(default=None, max_length=2000)


def is_reviewer(principal: Principal) -> bool:
    """Load reviewer authority from durable platform roles, never email domains."""
    try:
        row = get_access_repository().client.table("platform_staff_roles").select("role").eq(
            "user_id", principal.user_id
        ).eq("active", True).eq("role", "system_admin").execute().data or []
    except RuntimeError:
        return False
    return bool(row)


def _require_reviewer(principal: Principal) -> None:
    if not is_reviewer(principal):
        raise HTTPException(status_code=403, detail="LakeSafe reviewer access is required")


@router.get("/station-requests")
def list_station_requests(principal: Principal = Depends(get_principal)) -> dict:
    _require_reviewer(principal)
    return {"requests": get_workflow_repository().list_station_requests_for_review()}


@router.post("/station-requests/{request_id}/decision")
def decide_station_request(request_id: str, value: StationDecisionInput, principal: Principal = Depends(get_principal)) -> dict:
    _require_reviewer(principal)
    if value.decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=422, detail="Unsupported decision")
    try:
        membership = get_workflow_repository().review_station_request(StationReviewCreate(request_id, principal.user_id, value.decision, value.note))
    except WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail="Station request cannot be reviewed") from exc
    return {"status": value.decision, "membership_id": membership.membership_id if membership else None}
