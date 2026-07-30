"""Lake-scoped, server-authorized simulated autonomous fleet APIs."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.access.policy import Permission, require_recent_mfa, require_station_access
from app.access.principal import Principal, get_principal
from app.autonomy.inventory_repository import InventoryWorkflowConflict, get_inventory_repository

router = APIRouter(prefix="/api/stations/{station_id}", tags=["simulated-autonomy"])


class SimulatedInventoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    count: int = Field(ge=1, le=100)


class CirculationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    eligible: bool
    reason: str = Field(min_length=1, max_length=500)


def _station_access(principal: Principal, station_id: str, permission: Permission) -> None:
    try:
        require_station_access(principal, station_id, permission)
    except HTTPException as exc:
        if exc.status_code == 403 and not any(item.station_id == station_id for item in principal.memberships):
            raise HTTPException(status_code=404, detail="Station not found") from exc
        raise


@router.post("/inventory/simulated", status_code=status.HTTP_201_CREATED)
def register_simulated_inventory(station_id: str, value: SimulatedInventoryRequest, principal: Principal = Depends(get_principal)) -> dict:
    _station_access(principal, station_id, Permission.MANAGE_INVENTORY)
    try:
        return {"drones": get_inventory_repository().register_simulated_inventory(station_id, value.count)}
    except InventoryWorkflowConflict as exc:
        raise HTTPException(status_code=409, detail="Simulated inventory cannot be registered") from exc


@router.post("/lakes/{lake_id}/circulation/{drone_id}", status_code=status.HTTP_202_ACCEPTED)
def request_simulated_circulation(station_id: str, lake_id: str, drone_id: str, value: CirculationRequest, principal: Principal = Depends(get_principal)) -> dict:
    _station_access(principal, station_id, Permission.CHANGE_SIMULATED_CIRCULATION)
    require_recent_mfa(principal, timedelta(minutes=10))
    reconciliation_id = str(uuid4())
    try:
        return get_inventory_repository().set_simulated_circulation(
            station_id, drone_id, lake_id, value.eligible, value.reason.strip(), principal.user_id, reconciliation_id
        )
    except InventoryWorkflowConflict as exc:
        raise HTTPException(status_code=409, detail="Simulated circulation cannot be changed") from exc


@router.get("/lakes/{lake_id}/fleet")
def lake_fleet(station_id: str, lake_id: str, principal: Principal = Depends(get_principal)) -> dict:
    _station_access(principal, station_id, Permission.READ_OPERATIONS)
    try:
        return {"drones": get_inventory_repository().fleet(station_id, lake_id)}
    except InventoryWorkflowConflict as exc:
        raise HTTPException(status_code=404, detail="Lake not found") from exc
