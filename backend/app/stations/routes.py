from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel,ConfigDict,StrictBool

from app.access.policy import Permission, require_station_access, require_recent_mfa
from app.access.principal import Principal, get_principal
from app.stations.models import InvitationCreate, JoinRequestCreate, JoinReviewCreate, StationRequestCreate
from app.stations.repository import WorkflowConflict, get_workflow_repository
from app.rate_limits import require_rate_limit
from app.stations.schemas import InvitationAcceptInput, InvitationInput, JoinDecisionInput, StationRequestInput, MemberChangeInput

router = APIRouter(prefix="/api", tags=["stations"])


class PublicVisibilityInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    visible: StrictBool


@router.get('/stations/{station_id}/public-visibility')
def get_public_visibility(station_id: str,principal: Principal=Depends(get_principal)):
    require_station_access(principal,station_id,Permission.MANAGE_MEMBERS)
    try:
        return get_workflow_repository().public_visibility(station_id)
    except Exception as exc:
        raise HTTPException(503,'Public visibility is unavailable') from exc


@router.post('/stations/{station_id}/public-visibility')
def set_public_visibility(station_id: str,value: PublicVisibilityInput,principal: Principal=Depends(get_principal)):
    require_station_access(principal,station_id,Permission.MANAGE_MEMBERS)
    require_recent_mfa(principal,timedelta(minutes=10))
    try:
        result=get_workflow_repository().set_public_visibility(station_id,principal.user_id,value.visible)
        if not result: raise ValueError('Station not found')
        return result
    except Exception as exc:
        raise HTTPException(503,'Public visibility could not be saved') from exc


def _require_verified(principal: Principal) -> None:
    if principal.aal != "aal2" or principal.account_class != "officer" or principal.verification_status != "verified":
        raise HTTPException(status_code=403, detail="Verified officer access is required")


def _capabilities(membership) -> list[str]:
    role_capabilities = {
        "viewer": {"station.read"},
        "dispatcher": {"station.read", "alert.manage"},
        "safety_supervisor": {"station.read", "autonomy.manage", "fleet_safety.manage"},
        "station_admin": {"station.read", "alert.manage", "lake.create", "inventory.manage", "autonomy.manage", "member.manage"},
        "demo_operator": {"station.read", "alert.manage", "autonomy.manage"},
    }
    values = set()
    for role in membership.roles:
        values |= role_capabilities.get(str(role), set())
    if "demo_operator" in membership.roles:
        values &= role_capabilities["demo_operator"] if membership.simulation_only else set()
    return sorted(values)


@router.get("/me")
def get_me(principal: Principal = Depends(get_principal)) -> dict:
    # Import lazily to keep the principal endpoint independent from router
    # registration while still deriving this flag from the platform role table.
    from app.review.routes import is_reviewer
    return {
        "user_id": principal.user_id, "email": principal.email, "aal": principal.aal,
        "account_class": principal.account_class, "verification_status": principal.verification_status,
        "reviewer": is_reviewer(principal),
        "judge_demo_access": principal.judge_demo_access,
        "memberships": [{"station_id": item.station_id, "station_name": item.station_name, "status": item.status, "roles": sorted(str(role) for role in item.roles), "capabilities": _capabilities(item)} for item in principal.memberships],
    }


@router.get("/stations")
def search_stations(query: str = "", state: str | None = None) -> dict:
    if state is not None:
        raise HTTPException(status_code=422, detail="State filtering is not available yet")
    # Station discovery is deliberately metadata-only; memberships remain server-authorized.
    return {"stations": get_workflow_repository().search_stations(query[:160]), "query": query[:160]}


@router.post("/station-requests", status_code=status.HTTP_201_CREATED)
def create_station_request(value: StationRequestInput, principal: Principal = Depends(get_principal)) -> dict:
    _require_verified(principal)
    try:
        result = get_workflow_repository().create_station_request(StationRequestCreate(principal.user_id, value.name.strip(), value.address))
    except WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail="Station request already exists or cannot be created") from exc
    return {"station_request_id": result.station_request_id, "status": result.status}


@router.get("/station-requests/mine")
def my_station_requests(principal: Principal = Depends(get_principal)) -> dict:
    _require_verified(principal)
    return {"requests": [item.__dict__ for item in get_workflow_repository().list_station_requests_for_user(principal.user_id)]}


@router.get("/station-join-requests/mine")
def my_join_requests(principal: Principal = Depends(get_principal)) -> dict:
    _require_verified(principal)
    return {"requests": get_workflow_repository().list_my_join_requests(principal.user_id)}


@router.get("/stations/{station_id}/members")
def list_members(station_id: str, principal: Principal = Depends(get_principal)) -> dict:
    require_station_access(principal, station_id, Permission.MANAGE_MEMBERS)
    return {"members": get_workflow_repository().list_members(station_id)}


@router.patch("/stations/{station_id}/members/{membership_id}")
def change_member(station_id: str, membership_id: str, value: MemberChangeInput, request: Request, principal: Principal = Depends(get_principal)) -> dict:
    require_station_access(principal, station_id, Permission.MANAGE_MEMBERS)
    if not principal.judge_demo_access:
        require_recent_mfa(principal, timedelta(minutes=10))
    require_rate_limit("station.member.change", principal, request, station_id=station_id)
    try:
        return get_workflow_repository().change_member(station_id, membership_id, principal.user_id, value.roles, value.status)
    except WorkflowConflict as exc:
        raise HTTPException(409, "Membership could not be changed. Keep an active station administrator and retry.") from exc


@router.post("/stations/{station_id}/join-requests", status_code=status.HTTP_201_CREATED)
def create_join_request(station_id: str, principal: Principal = Depends(get_principal)) -> dict:
    _require_verified(principal)
    try:
        result = get_workflow_repository().create_join_request(JoinRequestCreate(station_id, principal.user_id))
    except WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail="Join request already exists or cannot be created") from exc
    return {"station_join_request_id": result.station_join_request_id, "status": result.status}


@router.post("/stations/{station_id}/invitations", status_code=status.HTTP_201_CREATED)
def create_invitation(station_id: str, value: InvitationInput, request: Request, principal: Principal = Depends(get_principal)) -> dict:
    require_station_access(principal, station_id, Permission.MANAGE_MEMBERS)
    require_rate_limit("station.invitation.create", principal, request, station_id=station_id)
    plaintext = secrets.token_urlsafe(32)
    expires_at = value.expires_at or datetime.now(timezone.utc) + timedelta(days=7)
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Invitation expiry must be in the future")
    try:
        get_workflow_repository().create_invitation(InvitationCreate(station_id, principal.user_id, hashlib.sha256(plaintext.encode()).hexdigest(), value.email, expires_at))
    except WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail="Invitation cannot be created") from exc
    return {"token": plaintext, "expires_at": expires_at.isoformat()}


@router.post("/invitations/accept")
def accept_invitation(value: InvitationAcceptInput, principal: Principal = Depends(get_principal)) -> dict:
    _require_verified(principal)
    if not principal.email:
        raise HTTPException(status_code=403, detail="A verified email is required")
    try:
        membership = get_workflow_repository().accept_invitation(hashlib.sha256(value.token.encode()).hexdigest(), principal.user_id, principal.email)
    except WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail="Invitation is invalid, expired, or already used") from exc
    return {"membership_id": membership.membership_id, "station_id": membership.station_id, "status": membership.status, "roles": membership.roles}


@router.get("/stations/{station_id}/join-requests")
def list_join_requests(station_id: str, principal: Principal = Depends(get_principal)) -> dict:
    require_station_access(principal, station_id, Permission.MANAGE_MEMBERS)
    return {"requests": [item.__dict__ for item in get_workflow_repository().list_join_requests_for_station(station_id)]}


@router.post("/stations/{station_id}/join-requests/{request_id}/decision")
def decide_join_request(station_id: str, request_id: str, value: JoinDecisionInput, request: Request, principal: Principal = Depends(get_principal)) -> dict:
    require_station_access(principal, station_id, Permission.MANAGE_MEMBERS)
    require_rate_limit("station.join.review", principal, request, station_id=station_id)
    try:
        membership = get_workflow_repository().review_join_request(JoinReviewCreate(request_id, principal.user_id, value.decision, value.roles))
    except WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail="Join request cannot be reviewed") from exc
    return {"membership_id": membership.membership_id, "status": membership.status, "roles": membership.roles} if membership else {"status": value.decision}
