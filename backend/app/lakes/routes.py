from __future__ import annotations

from uuid import uuid4
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.access.policy import Permission, require_station_access, require_recent_mfa
from app.access.principal import Principal, StationRole, get_principal
from app.lakes.schemas import LakeCreateRequest, LakeSetupRequest
from app.onboarding.shoreline_lookup import ShorelineLookupError, normalize_shoreline, resolve_shoreline, search_lakes, selected_lake
from app.stations.models import LakeCreate
from app.stations.repository import WorkflowConflict, get_workflow_repository
from app.rate_limits import require_rate_limit

router = APIRouter(prefix="/api", tags=["lakes"])


def reviewed_connector_for(name: str, latitude: float, longitude: float) -> str | None:
    """Return an approved connector ID when the registry contains this lake.

    The reviewed registry is intentionally empty until a jurisdiction's source
    contract has been approved; absence is a fallback state, not a guessed ID.
    """
    del name, latitude, longitude
    return None


def _shoreline_with_status(value: LakeCreateRequest) -> tuple[dict, str]:
    shoreline = normalize_shoreline(resolve_shoreline(value.name, value.centroid_lat, value.centroid_lon, value.bbox))
    connector = reviewed_connector_for(value.name, value.centroid_lat, value.centroid_lon)
    return shoreline, "reviewed" if connector else "fallback_coverage"


@router.post("/stations/{station_id}/lake-candidates")
def lake_candidates(station_id: str, value: LakeCreateRequest, principal: Principal = Depends(get_principal)) -> dict:
    require_station_access(principal, station_id, Permission.ADD_LAKE)
    try:
        geometry, data_source_status = _shoreline_with_status(value)
    except ShorelineLookupError:
        return {"candidates": [], "data_source_status": "fallback_coverage"}
    return {"candidates": [{"name": value.name, "shoreline": geometry}], "data_source_status": data_source_status}


@router.post("/stations/{station_id}/lakes", status_code=status.HTTP_201_CREATED)
def create_lake(station_id: str, value: LakeCreateRequest, request: Request, principal: Principal = Depends(get_principal)) -> dict:
    require_station_access(principal, station_id, Permission.ADD_LAKE)
    require_rate_limit("lake.create", principal, request, station_id=station_id)
    try:
        shoreline, data_source_status = _shoreline_with_status(value)
    except ShorelineLookupError as exc:
        raise HTTPException(status_code=503, detail="Authoritative shoreline data is unavailable") from exc
    lake_id = f"lake-{uuid4()}"
    try:
        lake = get_workflow_repository().create_lake(LakeCreate(lake_id, station_id, value.name.strip(), value.centroid_lat, value.centroid_lon, shoreline, principal.user_id, data_source_status))
    except WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail="Lake cannot be created") from exc
    # No unreviewed Socrata dataset is implied.  Queue coverage setup explicitly.
    return {"lake_id": lake.lake_id, "station_id": lake.station_id, "name": lake.name, "setup_status": "queued", "data_source_status": data_source_status}


def _admin_station(principal: Principal, station_id: str | None = None) -> str:
    source = station_id or next((item.station_id for item in principal.memberships
        if item.status == "active" and StationRole.STATION_ADMIN in item.roles), None)
    if not source:
        raise HTTPException(403, "An active station administrator is required")
    require_station_access(principal, source, Permission.ADD_LAKE)
    return source


@router.get("/lake-search")
def lake_search(query: str, principal: Principal = Depends(get_principal)) -> dict:
    _admin_station(principal)
    try:
        return {"candidates": search_lakes(query), "region": "King County, Washington"}
    except ShorelineLookupError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/lake-setups", status_code=status.HTTP_201_CREATED)
def create_lake_setup(value: LakeSetupRequest, request: Request, principal: Principal = Depends(get_principal)) -> dict:
    source = _admin_station(principal, str(value.station_id) if value.station_id else None)
    if not principal.judge_demo_access:
        require_recent_mfa(principal, timedelta(minutes=10))
    require_rate_limit("lake.create", principal, request, station_id=source)
    try:
        candidate = selected_lake(value.candidate_id)
    except ShorelineLookupError as exc:
        raise HTTPException(503, str(exc)) from exc
    try:
        result = get_workflow_repository().create_lake_workspace(
            source, str(value.station_id) if value.station_id else None, value.new_station_name,
            LakeCreate(f"lake-{uuid4()}", source, candidate["name"], candidate["centroid_lat"],
                       candidate["centroid_lon"], candidate["shoreline"], principal.user_id))
    except WorkflowConflict as exc:
        raise HTTPException(409, "Lake could not be added. It may already belong to this station; refresh and retry.") from exc
    return {**result, "setup_status": "queued", "data_source_status": "fallback_coverage"}
