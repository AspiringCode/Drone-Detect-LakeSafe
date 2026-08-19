"""Typed, fail-closed access to the committed reviewed lake catalog."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from app.models import LatLon


CATALOG_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "reviewed_lakes.json"
SUPPORTED_LAKE_IDS = ("lake-sammamish", "lake-pine", "lake-beaver")


@dataclass(frozen=True, slots=True)
class CatalogCoordinate:
    latitude: float
    longitude: float

    def as_lat_lon(self) -> LatLon:
        return LatLon(self.latitude, self.longitude)


@dataclass(frozen=True, slots=True)
class OfficialPriorityCoordinate(CatalogCoordinate):
    locator: str


@dataclass(frozen=True, slots=True)
class ReviewedLake:
    lake_id: str
    name: str
    centroid: CatalogCoordinate
    shore_station: CatalogCoordinate
    locators: tuple[str, ...]
    official_priority_coordinates: tuple[OfficialPriorityCoordinate, ...]


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("invalid reviewed lake catalog mapping")
    return value


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid reviewed lake catalog text")
    return value


def _number(value: Any, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("invalid reviewed lake catalog coordinate")
    numeric = float(value)
    if not minimum <= numeric <= maximum:
        raise ValueError("invalid reviewed lake catalog coordinate")
    return numeric


def _coordinate(value: Any) -> CatalogCoordinate:
    mapping = _mapping(value)
    return CatalogCoordinate(
        _number(mapping.get("latitude"), minimum=-90, maximum=90),
        _number(mapping.get("longitude"), minimum=-180, maximum=180),
    )


def _entry(value: Any) -> ReviewedLake:
    mapping = _mapping(value)
    lake_id = _text(mapping.get("lake_id"))
    raw_locators = mapping.get("locators")
    raw_coordinates = mapping.get("official_monitoring_coordinates")
    if not isinstance(raw_locators, list) or not isinstance(raw_coordinates, list):
        raise ValueError("invalid reviewed lake catalog locators")
    locators = tuple(_text(locator) for locator in raw_locators)
    coordinates = tuple(
        OfficialPriorityCoordinate(
            latitude=_number(_mapping(point).get("latitude"), minimum=-90, maximum=90),
            longitude=_number(_mapping(point).get("longitude"), minimum=-180, maximum=180),
            locator=_text(_mapping(point).get("locator")),
        )
        for point in raw_coordinates
    )
    if not locators or len(set(locators)) != len(locators):
        raise ValueError("invalid reviewed lake catalog locators")
    if tuple(point.locator for point in coordinates) != locators:
        raise ValueError("invalid reviewed lake catalog coordinate mapping")
    return ReviewedLake(
        lake_id=lake_id,
        name=_text(mapping.get("display_name")),
        centroid=_coordinate(mapping.get("centroid")),
        shore_station=_coordinate(mapping.get("shore_station")),
        locators=locators,
        official_priority_coordinates=coordinates,
    )


def _load_entries() -> dict[str, ReviewedLake]:
    try:
        payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        mapping = _mapping(payload)
        if mapping.get("schema_version") != 1:
            raise ValueError("invalid reviewed lake catalog schema version")
        raw_lakes = mapping.get("lakes")
        if not isinstance(raw_lakes, list):
            raise ValueError("invalid reviewed lake catalog lakes")
        entries = tuple(_entry(item) for item in raw_lakes)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError("invalid reviewed lake catalog") from exc
    if tuple(entry.lake_id for entry in entries) != SUPPORTED_LAKE_IDS:
        raise ValueError("invalid reviewed lake catalog lake IDs")
    return {entry.lake_id: entry for entry in entries}


def load_reviewed_lake(lake_id: str) -> ReviewedLake:
    """Return one immutable reviewed entry; unknown IDs never fall back."""
    try:
        return _load_entries()[lake_id]
    except KeyError as exc:
        raise ValueError(f"unknown reviewed lake: {lake_id!r}") from exc


__all__ = [
    "CatalogCoordinate",
    "OfficialPriorityCoordinate",
    "ReviewedLake",
    "SUPPORTED_LAKE_IDS",
    "load_reviewed_lake",
]
