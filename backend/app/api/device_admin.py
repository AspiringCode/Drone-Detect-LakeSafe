"""Station-admin real inventory and patrol hand-off; never stick-level flight control."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from app.access.policy import Permission, require_recent_mfa, require_station_access
from app.access.principal import Principal, get_principal
from app.coordination.assignment import haversine_m
from app.devices import live_positions
from app.devices.patrol_repository import get_patrol_repository
from app.devices.repository import DeviceRepositoryError, get_device_repository
from app.devices.auth import DeviceAuthenticationError, decode_base64url
from app.missions.qgc_plan import build_patrol_plan, mission_rows, to_waypoints
from app.models import LatLon
from app.rate_limits import require_rate_limit

router = APIRouter(prefix="/api/stations/{station_id}/inventory", tags=["real-device-inventory"])
TEST_POSITION_SECONDS = 300

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
    if not drone or not drone.get("lake_id") or drone.get("lifecycle") == "retired":
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

def _patrol_layout(station_id: str, drone: dict) -> tuple[list, str | None]:
    """The zones real drones on this drone's lake fly, and the one assigned to this drone."""
    from app.main import get_runtime, real_zone_layout, sync_real_assignments  # lazy: app.main imports this router

    runtime = get_runtime(drone["lake_id"])
    try:
        lake_drones = [d["inventory_id"] for d in get_device_repository().list_real(station_id) if d.get("lake_id") == drone["lake_id"]]
    except DeviceRepositoryError as exc:
        raise HTTPException(503, "Real inventory is unavailable") from exc
    return real_zone_layout(runtime), sync_real_assignments(runtime, lake_drones).get(drone["inventory_id"])

class MissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    zone_id: str | None = Field(default=None, min_length=1, max_length=120)
    home_lat: float = Field(ge=-90, le=90)
    home_lon: float = Field(ge=-180, le=180)
    altitude_m: float = Field(ge=5, le=120)


class PatrolRequest(MissionRequest):
    reviewed_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


MAX_HOME_DISTANCE_M = 5000


def prepare_mission(station_id: str, drone: dict, value: MissionRequest):
    zones, assigned = _patrol_layout(station_id, drone)
    wanted = value.zone_id or assigned
    zone = next((z for z in zones if z.zone_id == wanted and z.radius_m), None)
    if zone is None:
        raise HTTPException(404, "Patrol zone not found")
    home = LatLon(value.home_lat, value.home_lon)
    if haversine_m(home, zone.centroid) > MAX_HOME_DISTANCE_M:
        raise HTTPException(422, "Home must be within 5 km of the patrol zone")
    plan = build_patrol_plan(zone.centroid, zone.radius_m, value.altitude_m, home=home)
    payload = {"lake_id": drone["lake_id"], "drone_id": drone["inventory_id"], "zone_id": zone.zone_id,
               "home": {"lat": home.lat, "lon": home.lon}, "altitude_m": value.altitude_m, "mission": mission_rows(plan)}
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return zone, plan, payload, fingerprint


@router.post("/{drone_id}/mission-preview")
def preview_mission(station_id: str, drone_id: str, value: MissionRequest, principal: Principal = Depends(get_principal)) -> dict:
    _access(principal, station_id)
    zone, plan, payload, fingerprint = prepare_mission(station_id, _assigned_drone(station_id, drone_id), value)
    return {"zone_id": zone.zone_id, "home": payload["home"], "altitude_m": value.altitude_m,
            "waypoint_count": len(plan["mission"]["items"]), "mission_hash": fingerprint,
            "route": [{"lat": row[6], "lon": row[7]} for row in payload["mission"] if row[1] in (16, 22)]}


@router.post("/{drone_id}/patrol", status_code=status.HTTP_202_ACCEPTED)
def send_patrol(station_id: str, drone_id: str, value: PatrolRequest, request: Request, principal: Principal = Depends(get_principal)) -> dict:
    """Queue a reviewed upload only. The pilot controls arming and RC override."""
    _access(principal, station_id)
    require_rate_limit("inventory.real.patrol", principal, request, station_id=station_id)
    drone = _assigned_drone(station_id, drone_id)
    if drone.get("credential_state") != "active":
        raise HTTPException(409, "The drone's credential is not active")
    zone, plan, payload, fingerprint = prepare_mission(station_id, drone, value)
    if fingerprint != value.reviewed_hash:
        raise HTTPException(409, "Mission changed; refresh and review the preview again")
    try:
        result = get_patrol_repository().queue(station_id, drone_id, drone["lake_id"], principal.user_id,
            {**payload, "mission_hash": fingerprint})
    except DeviceRepositoryError as exc:
        raise HTTPException(409, "Patrol could not be queued; refresh the drone and review again") from exc
    return {**result, "zone_id": zone.zone_id, "waypoints": len(plan["mission"]["items"])}


@router.get("/{drone_id}/patrol-commands/latest")
def latest_patrol_command(station_id: str, drone_id: str, principal: Principal = Depends(get_principal)) -> dict:
    _admin(principal, station_id)
    try:
        result = get_patrol_repository().latest(station_id, drone_id)
    except DeviceRepositoryError as exc:
        raise HTTPException(503, "Patrol status is unavailable") from exc
    return result or {"command": None}


@router.get("/{drone_id}/patrol-commands/{command_id}")
def patrol_command_status(station_id: str, drone_id: str, command_id: str, principal: Principal = Depends(get_principal)) -> dict:
    _admin(principal, station_id)
    try:
        result = get_patrol_repository().status(station_id, drone_id, command_id)
    except DeviceRepositoryError as exc:
        raise HTTPException(503, "Patrol status is unavailable") from exc
    if not result:
        raise HTTPException(404, "Patrol command not found")
    return result


@router.get("/{drone_id}/patrol-zones")
def list_patrol_zones(station_id: str, drone_id: str, principal: Principal = Depends(get_principal)) -> dict:
    """The runtime zones Send patrol flies, so a downloaded mission matches the hand-off."""
    _admin(principal, station_id)
    drone = _assigned_drone(station_id, drone_id)
    zones, assigned = _patrol_layout(station_id, drone)
    return {"lake_id": drone["lake_id"], "assigned_zone_id": assigned,
            "zones": [{"zone_id": z.zone_id, "radius_m": round(z.radius_m), "is_proxy": z.is_proxy} for z in zones if z.radius_m]}

@router.post("/{drone_id}/mission")
def download_mission(station_id: str, drone_id: str, value: MissionRequest, principal: Principal = Depends(get_principal)) -> PlainTextResponse:
    """A Mission Planner file for the operator to review and load; nothing is sent to the drone."""
    _admin(principal, station_id)
    zone, plan, _, _ = prepare_mission(station_id, _assigned_drone(station_id, drone_id), value)
    return PlainTextResponse(to_waypoints(plan), headers={"Content-Disposition": f'attachment; filename="{zone.zone_id}.waypoints"'})

@router.post("/{drone_id}/retire")
def retire_real_inventory(station_id: str, drone_id: str, request: Request, principal: Principal = Depends(get_principal)) -> dict:
    _access(principal, station_id)
    require_rate_limit("inventory.real.retire", principal, request, station_id=station_id)
    try:
        return get_device_repository().retire_real(station_id, drone_id, principal.user_id)
    except DeviceRepositoryError as exc:
        raise HTTPException(409, "Real inventory cannot be retired") from exc
