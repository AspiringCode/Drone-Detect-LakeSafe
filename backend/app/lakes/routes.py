from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.access.policy import Permission, require_station_access
from app.access.principal import Principal, get_principal
from app.lakes.schemas import LakeCreateRequest
from app.onboarding.shoreline_lookup import ShorelineLookupError, normalize_shoreline, resolve_shoreline
from app.stations.models import LakeCreate
from app.stations.repository import WorkflowConflict, get_workflow_repository

router = APIRouter(prefix="/api/stations/{station_id}", tags=["lakes"])


@router.post("/lake-candidates")
def lake_candidates(station_id: str, value: LakeCreateRequest, principal: Principal = Depends(get_principal)) -> dict:
    require_station_access(principal, station_id, Permission.ADD_LAKE)
    try:
        geometry = normalize_shoreline(resolve_shoreline(value.name, value.centroid_lat, value.centroid_lon, value.bbox))
    except ShorelineLookupError:
        return {"candidates": [], "data_source_status": "fallback_coverage"}
    return {"candidates": [{"name": value.name, "shoreline": geometry}], "data_source_status": "reviewed"}


@router.post("/lakes", status_code=status.HTTP_201_CREATED)
def create_lake(station_id: str, value: LakeCreateRequest, principal: Principal = Depends(get_principal)) -> dict:
    require_station_access(principal, station_id, Permission.ADD_LAKE)
    try:
        shoreline = normalize_shoreline(resolve_shoreline(value.name, value.centroid_lat, value.centroid_lon, value.bbox))
    except ShorelineLookupError as exc:
        raise HTTPException(status_code=503, detail="Authoritative shoreline data is unavailable") from exc
    lake_id = f"lake-{uuid4()}"
    try:
        lake = get_workflow_repository().create_lake(LakeCreate(lake_id, station_id, value.name.strip(), value.centroid_lat, value.centroid_lon, shoreline, principal.user_id))
    except WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail="Lake cannot be created") from exc
    # No unreviewed Socrata dataset is implied.  Queue coverage setup explicitly.
    return {"lake_id": lake.lake_id, "station_id": lake.station_id, "name": lake.name, "setup_status": "queued", "data_source_status": "fallback_coverage"}
