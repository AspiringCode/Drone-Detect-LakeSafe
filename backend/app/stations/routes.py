from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.access.policy import Permission, require_station_access
from app.access.principal import Principal, get_principal
from app.stations.models import InvitationCreate, JoinRequestCreate, JoinReviewCreate, StationRequestCreate
from app.stations.repository import WorkflowConflict, get_workflow_repository
from app.stations.schemas import InvitationAcceptInput, InvitationInput, JoinDecisionInput, StationRequestInput

router = APIRouter(prefix="/api", tags=["stations"])


def _require_verified(principal: Principal) -> None:
    if principal.aal != "aal2" or principal.account_class != "officer" or principal.verification_status != "verified":
        raise HTTPException(status_code=403, detail="Verified officer access is required")


def _capabilities(membership) -> list[str]:
    role_capabilities = {
        "viewer": {"station.read"}, "dispatcher": {"alert.manage"},
        "safety_supervisor": {"autonomy.manage"},
        "station_admin": {"alert.manage", "lake.create", "inventory.manage", "member.manage"},
    }
    values = set()
    for role in membership.roles:
        values |= role_capabilities.get(str(role), set())
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
        "memberships": [{"station_id": item.station_id, "station_name": item.station_name, "status": item.status, "roles": sorted(str(role) for role in item.roles), "capabilities": _capabilities(item)} for item in principal.memberships],
    }


@router.get("/stations")
def search_stations(query: str = "", state: str | None = None) -> dict:
    if state is not None and (len(state) != 2 or not state.isalpha()):
        raise HTTPException(status_code=422, detail="State must be a USPS abbreviation")
    # Station discovery is deliberately metadata-only; memberships remain server-authorized.
    return {"stations": [], "query": query[:160], "state": state.upper() if state else None}


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
    return {"requests": []}


@router.post("/stations/{station_id}/join-requests", status_code=status.HTTP_201_CREATED)
def create_join_request(station_id: str, principal: Principal = Depends(get_principal)) -> dict:
    _require_verified(principal)
    try:
        result = get_workflow_repository().create_join_request(JoinRequestCreate(station_id, principal.user_id))
    except WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail="Join request already exists or cannot be created") from exc
    return {"station_join_request_id": result.station_join_request_id, "status": result.status}


@router.post("/stations/{station_id}/invitations", status_code=status.HTTP_201_CREATED)
def create_invitation(station_id: str, value: InvitationInput, principal: Principal = Depends(get_principal)) -> dict:
    require_station_access(principal, station_id, Permission.MANAGE_MEMBERS)
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
    return {"requests": []}


@router.post("/stations/{station_id}/join-requests/{request_id}/decision")
def decide_join_request(station_id: str, request_id: str, value: JoinDecisionInput, principal: Principal = Depends(get_principal)) -> dict:
    require_station_access(principal, station_id, Permission.MANAGE_MEMBERS)
    try:
        membership = get_workflow_repository().review_join_request(JoinReviewCreate(request_id, principal.user_id, value.decision, value.roles))
    except WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail="Join request cannot be reviewed") from exc
    return {"membership_id": membership.membership_id, "status": membership.status, "roles": membership.roles} if membership else {"status": value.decision}
