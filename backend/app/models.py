from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal

Source = Literal["real", "simulated"]


@dataclass(frozen=True)
class LatLon:
    lat: float
    lon: float


@dataclass
class RiskZone:
    zone_id: str
    centroid: LatLon
    polygon: list[LatLon]
    risk_score: float
    components: dict[str, float]
    is_proxy: bool
    radius_m: float | None = None


@dataclass(frozen=True)
class ZonePlanCell:
    """An immutable, shoreline-clipped cell in a versioned zone plan."""

    cell_id: str
    kind: Literal["hotspot", "coverage", "fallback"]
    seed: LatLon
    centroid: LatLon
    polygon: tuple[LatLon, ...]
    radius_m: float
    risk_score: float
    is_proxy: bool


@dataclass(frozen=True)
class ZonePlanCandidate:
    """A validated candidate kept separate from the lake's active plan pointer."""

    plan_id: str
    lake_id: str
    station_id: str
    snapshot_id: str | None
    prior_plan_id: str | None
    activity_data_unavailable: bool
    cells: tuple[ZonePlanCell, ...]


class DroneStatus(str, Enum):
    IDLE = "idle"
    EN_ROUTE = "en_route"
    PATROLLING = "patrolling"
    INVESTIGATING = "investigating"
    RETURNING = "returning"
    CHARGING = "charging"


@dataclass
class Drone:
    drone_id: str
    pos: LatLon
    battery: float
    status: DroneStatus
    assigned_zone: str | None
    source: Source = "simulated"


@dataclass
class Detection:
    frame_idx: int
    bbox: tuple[float, float, float, float]
    confidence: float
    timestamp: datetime
    source: Source


@dataclass
class Alert:
    alert_id: str
    created_at: datetime
    location: LatLon
    detection_mode: str
    drone_id: str
    thermal_clip_ref: str | None
    confirmed: bool
    source: Source
    latency_ms: int | None
