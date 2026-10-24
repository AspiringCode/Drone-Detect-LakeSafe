"""Station-admin real inventory and patrol hand-off; never stick-level flight control."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from app.access.policy import Permission, require_recent_mfa, require_station_access
from app.access.principal import Principal, get_principal
from app.coordination.assignment import haversine_m
from app.devices import live_commands, live_positions
from app.devices.repository import DeviceRepositoryError, get_device_repository
from app.devices.auth import DeviceAuthenticationError, decode_base64url
from app.missions.export import DEFAULT_ALTITUDE_M
from app.missions.qgc_plan import build_patrol_plan, mission_rows, to_waypoints
from app.models import LatLon
from app.rate_limits import require_rate_limit

router = APIRouter(prefix="/api/stations/{station_id}/inventory", tags=["real-device-inventory"])
TEST_POSITION_SECONDS = 300
PATROL_COMMAND_SECONDS = 120

class RealInventoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manufacturer: str = Field(min_length=1, max_length=120)
    serial: str = Field(min_length=1, max_length=160)
    public_key: str = Field(min_length=40, max_length=200)

def _access(principal: Principal, station_id: str) -> None:
    try:
        require_station_access(principal, station_id, Permission.MANAGE_INVENTORY)
        # Pragyan's decision 2026-10-22: the fictional CAC demo admins are password-only; the flag comes from the
        # server-owned allowlist and lapses at its Nov 1 expiry. Every other account still needs the step-up.
        if not principal.judge_demo_access:
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

class LakeAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lake_id: str | None = Field(default=None, min_length=1, max_length=120)

class TestPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)

def _admin(principal: Principal, station_id: str) -> None:
    """Inventory capability without the recent-MFA step-up: reads and display-only test markers."""
    try:
        require_station_access(principal, station_id, Permission.MANAGE_INVENTORY)
    except HTTPException as exc:
        if exc.status_code == 403 and not any(m.station_id == station_id for m in principal.memberships):
            raise HTTPException(404, "Station not found") from exc
        raise

@router.get("/real")
def list_real_inventory(station_id: str, principal: Principal = Depends(get_principal)) -> dict:
    _admin(principal, station_id)
    try:
        return {"drones": get_device_repository().list_real(station_id)}
    except DeviceRepositoryError as exc:
        raise HTTPException(503, "Real inventory is unavailable") from exc

@router.post("/{drone_id}/lake")
def assign_real_inventory_lake(station_id: str, drone_id: str, value: LakeAssignment, request: Request, principal: Principal = Depends(get_principal)) -> dict:
    _access(principal, station_id)
    require_rate_limit("inventory.real.assign", principal, request, station_id=station_id)
    try:
        return get_device_repository().attach_real_to_lake(station_id, drone_id, value.lake_id)
    except DeviceRepositoryError as exc:
        raise HTTPException(409, "Drone cannot be assigned to that lake") from exc

def _assigned_drone(station_id: str, drone_id: str) -> dict:
    try:
        drones = get_device_repository().list_real(station_id)
    except DeviceRepositoryError as exc:
        raise HTTPException(503, "Real inventory is unavailable") from exc
    drone = next((d for d in drones if d.get("inventory_id") == drone_id), None)
    if not drone or not drone.get("lake_id"):
        raise HTTPException(409, "Assign the drone to a lake first")
    return drone

@router.post("/{drone_id}/test-position", status_code=status.HTTP_202_ACCEPTED)
def place_test_position(station_id: str, drone_id: str, value: TestPosition, principal: Principal = Depends(get_principal)) -> dict:
    _admin(principal, station_id)
    lake_id = _assigned_drone(station_id, drone_id)["lake_id"]
    # A hand-placed marker is not hardware telemetry, so it is labeled simulated.
    marker = live_positions.real_drone(f"{drone_id} (test)", value.lat, value.lon, 100, "idle")
    live_positions.record(lake_id, replace(marker, source="simulated"), datetime.now(timezone.utc), ttl_seconds=TEST_POSITION_SECONDS)
    return {"lake_id": lake_id, "expires_in_seconds": TEST_POSITION_SECONDS}

class PatrolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    zone_id: str | None = Field(default=None, min_length=1, max_length=120)

@router.post("/{drone_id}/patrol", status_code=status.HTTP_202_ACCEPTED)
def send_patrol(station_id: str, drone_id: str, value: PatrolRequest, request: Request, principal: Principal = Depends(get_principal)) -> dict:
    """Queue one patrol loop for the drone's Pi to upload; the pilot still arms it, and RC always overrides."""
    from app.main import get_runtime  # lazy: app.main imports this router

    _access(principal, station_id)
    require_rate_limit("inventory.real.patrol", principal, request, station_id=station_id)
    drone = _assigned_drone(station_id, drone_id)
    if drone.get("credential_state") != "active":
        raise HTTPException(409, "The drone's credential is not active")
    zones = get_runtime(drone["lake_id"]).zones
    zone = next((z for z in zones if value.zone_id in (None, z.zone_id) and z.radius_m), None)
    if zone is None:
        raise HTTPException(404, "Patrol zone not found")
    plan = build_patrol_plan(zone.centroid, zone.radius_m, DEFAULT_ALTITUDE_M, home=zone.centroid)
    command_id = str(uuid4())
    live_commands.queue(drone_id, {
        "command_id": command_id, "command_type": "patrol", "zone_id": zone.zone_id,
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=PATROL_COMMAND_SECONDS)).isoformat(),
        "mission": mission_rows(plan), "ack": False,
    })
    return {"command_id": command_id, "zone_id": zone.zone_id, "waypoints": len(plan["mission"]["items"])}

@router.get("/{drone_id}/patrol-zones")
def list_patrol_zones(station_id: str, drone_id: str, principal: Principal = Depends(get_principal)) -> dict:
    """The runtime zones Send patrol flies, so a downloaded mission matches the hand-off."""
    from app.main import get_runtime  # lazy: app.main imports this router

    _admin(principal, station_id)
    lake_id = _assigned_drone(station_id, drone_id)["lake_id"]
    zones = [z for z in get_runtime(lake_id).zones if z.radius_m]
    return {"lake_id": lake_id, "zones": [{"zone_id": z.zone_id, "radius_m": round(z.radius_m), "is_proxy": z.is_proxy} for z in zones]}

class MissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    zone_id: str = Field(min_length=1, max_length=120)
    home_lat: float = Field(ge=-90, le=90)
    home_lon: float = Field(ge=-180, le=180)
    altitude_m: float = Field(ge=5, le=120)  # 120 m stays under the FAA's 400 ft ceiling

MAX_HOME_DISTANCE_M = 5000

@router.post("/{drone_id}/mission")
def download_mission(station_id: str, drone_id: str, value: MissionRequest, principal: Principal = Depends(get_principal)) -> PlainTextResponse:
    """A Mission Planner file for the operator to review and load; nothing is sent to the drone."""
    from app.main import get_runtime  # lazy: app.main imports this router

    _admin(principal, station_id)
    lake_id = _assigned_drone(station_id, drone_id)["lake_id"]
    zone = next((z for z in get_runtime(lake_id).zones if z.zone_id == value.zone_id and z.radius_m), None)
    if zone is None:
        raise HTTPException(404, "Patrol zone not found")
    home = LatLon(value.home_lat, value.home_lon)
    # A swapped sign or typo in home would send takeoff and RTL somewhere else entirely.
    if haversine_m(home, zone.centroid) > MAX_HOME_DISTANCE_M:
        raise HTTPException(422, "Home must be within 5 km of the patrol zone")
    plan = build_patrol_plan(zone.centroid, zone.radius_m, value.altitude_m, home=home)
    return PlainTextResponse(to_waypoints(plan), headers={"Content-Disposition": f'attachment; filename="{zone.zone_id}.waypoints"'})

@router.post("/{drone_id}/retire")
def retire_real_inventory(station_id: str, drone_id: str, request: Request, principal: Principal = Depends(get_principal)) -> dict:
    _access(principal, station_id)
    require_rate_limit("inventory.real.retire", principal, request, station_id=station_id)
    try:
        return get_device_repository().retire_real(station_id, drone_id, principal.user_id)
    except DeviceRepositoryError as exc:
        raise HTTPException(409, "Real inventory cannot be retired") from exc
