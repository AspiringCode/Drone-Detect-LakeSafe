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


@dataclass(frozen=True)
class RiskPointProvenance:
    """Reviewed publisher identity retained from a normalized point to a plan cell."""

    connector_key: str
    source_row_id: str
    locator: str | None
    observed_at: datetime | None
    source_latitude: float | None = None
    source_longitude: float | None = None
    derived_seed_latitude: float | None = None
    derived_seed_longitude: float | None = None
    adjustment_distance_m: float | None = None
    adjustment_reason: str | None = None
    reviewed_at: datetime | None = None
    temporal_basis: Literal["publisher_observation", "catalog_review"] = "publisher_observation"


@dataclass
class RiskZone:
    zone_id: str
    centroid: LatLon
    polygon: list[LatLon]
    risk_score: float
    components: dict[str, float]
    is_proxy: bool
    radius_m: float | None = None
    seed: LatLon | None = None
    provenance: tuple[RiskPointProvenance, ...] = ()
    holes: tuple[tuple[LatLon, ...], ...] = ()


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
    provenance: tuple[RiskPointProvenance, ...] = ()
    holes: tuple[tuple[LatLon, ...], ...] = ()


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
