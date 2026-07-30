"""Immutable inputs and outputs for simulated-fleet autonomy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Source = Literal["simulated", "real"]
Lifecycle = Literal["available", "circulating", "charging", "maintenance", "retired"]
Health = Literal["healthy", "fault"]
Connectivity = Literal["connected", "disconnected"]
CellKind = Literal["hotspot", "coverage", "fallback"]


@dataclass(frozen=True)
class FleetPolicy:
    safety_reserve: int = 1
    minimum_battery_percent: int = 30

    def __post_init__(self) -> None:
        if self.safety_reserve < 0 or not 0 <= self.minimum_battery_percent <= 100:
            raise ValueError("invalid fleet policy")


@dataclass(frozen=True)
class InventoryDrone:
    inventory_id: str
    station_id: str
    lake_id: str | None
    source: Source
    lifecycle: Lifecycle
    battery_percent: int
    health: Health
    connectivity: Connectivity
    maintenance_due: bool
    desired_state_version: int


@dataclass(frozen=True)
class ZoneCell:
    cell_id: str
    kind: CellKind
    risk_score: float


@dataclass(frozen=True)
class ZonePlan:
    plan_id: str
    station_id: str
    lake_id: str
    cells: tuple[ZoneCell, ...]


@dataclass(frozen=True)
class PriorAssignment:
    inventory_id: str
    zone_id: str
    desired_state_version: int


@dataclass(frozen=True)
class DesiredAssignment:
    inventory_id: str
    zone_id: str
    desired_state_version: int
