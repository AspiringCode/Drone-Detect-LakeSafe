"""Station-admin real inventory registration, never flight control."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.access.policy import Permission, require_recent_mfa, require_station_access
from app.access.principal import Principal, get_principal
from app.devices.repository import DeviceRepositoryError, get_device_repository
from app.devices.auth import DeviceAuthenticationError, decode_base64url
from app.rate_limits import require_rate_limit

router = APIRouter(prefix="/api/stations/{station_id}/inventory", tags=["real-device-inventory"])

class RealInventoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manufacturer: str = Field(min_length=1, max_length=120)
    serial: str = Field(min_length=1, max_length=160)
    public_key: str = Field(min_length=40, max_length=200)

def _access(principal: Principal, station_id: str) -> None:
    try:
        require_station_access(principal, station_id, Permission.MANAGE_INVENTORY)
        require_recent_mfa(principal, timedelta(minutes=10))
    except HTTPException as exc:
        if exc.status_code == 403 and not any(m.station_id == station_id for m in principal.memberships):
            raise HTTPException(404, "Station not found") from exc
        raise

def _valid_key(value: str) -> bool:
    try:
        decode_base64url(value, expected_length=32)
        return True
    except DeviceAuthenticationError:
        return False

@router.post("/real", status_code=status.HTTP_201_CREATED)
def register_real_inventory(station_id: str, value: RealInventoryRequest, request: Request, principal: Principal = Depends(get_principal)) -> dict:
    _access(principal, station_id)
    require_rate_limit("inventory.real.register", principal, request, station_id=station_id)
    if not _valid_key(value.public_key): raise HTTPException(422, "A valid Ed25519 public key is required")
    try:
        return get_device_repository().register_real(station_id, value.manufacturer.strip(), value.serial.strip(), value.public_key, principal.user_id)
    except DeviceRepositoryError as exc:
        raise HTTPException(409, "Real inventory cannot be registered") from exc

@router.post("/{drone_id}/retire")
def retire_real_inventory(station_id: str, drone_id: str, request: Request, principal: Principal = Depends(get_principal)) -> dict:
    _access(principal, station_id)
    require_rate_limit("inventory.real.retire", principal, request, station_id=station_id)
    try:
        return get_device_repository().retire_real(station_id, drone_id, principal.user_id)
    except DeviceRepositoryError as exc:
        raise HTTPException(409, "Real inventory cannot be retired") from exc
