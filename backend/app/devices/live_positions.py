"""Latest authenticated real-drone positions, merged into the operations feed.

shortcut: in-process memory, so it assumes one uvicorn worker and forgets
positions on restart; persist to drone_telemetry if the backend is scaled out.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.config import REAL_HEARTBEAT_TTL_SECONDS
from app.models import Drone, DroneStatus, LatLon

_latest: dict[str, dict[str, tuple[Drone, datetime]]] = {}


def record(lake_id: str, drone: Drone, received_at: datetime, *, ttl_seconds: int = REAL_HEARTBEAT_TTL_SECONDS) -> None:
    _latest.setdefault(lake_id, {})[drone.drone_id] = (drone, received_at + timedelta(seconds=ttl_seconds))


def snapshot(lake_id: str, now: datetime | None = None) -> list[Drone]:
    """Fresh drones for one lake; a drone that stops beating drops off the map."""
    now = now or datetime.now(timezone.utc)
    drones = _latest.get(lake_id, {})
    for drone_id in [d for d, (_, expires_at) in drones.items() if expires_at < now]:
        del drones[drone_id]
    return [drone for drone, _ in drones.values()]


def with_real_drones(lake_id: str, state: dict) -> dict:
    return {**state, "drones": [*state.get("drones", []), *snapshot(lake_id)]}


def real_drone(drone_id: str, lat: float, lon: float, battery_percent: int, status: str) -> Drone:
    return Drone(drone_id, LatLon(lat, lon), battery_percent / 100, DroneStatus(status), None, source="real")
