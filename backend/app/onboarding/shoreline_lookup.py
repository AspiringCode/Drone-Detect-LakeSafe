from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class ShorelineLookupError(ValueError):
    """An authoritative shoreline was unavailable or geometrically invalid."""


def normalize_shoreline(geometry: Mapping[str, Any]) -> dict[str, Any]:
    """Return a non-empty GeoJSON SRID-4326 MultiPolygon suitable for PostGIS."""
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon":
        coordinates = [coordinates]
    if geometry_type != "MultiPolygon" and geometry_type != "Polygon":
        raise ShorelineLookupError("Authoritative shoreline must be a polygon")
    if not isinstance(coordinates, list) or not coordinates:
        raise ShorelineLookupError("Authoritative shoreline is empty")
    for polygon in coordinates:
        if not isinstance(polygon, list) or not polygon:
            raise ShorelineLookupError("Authoritative shoreline is empty")
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4:
                raise ShorelineLookupError("Authoritative shoreline has an invalid ring")
            for point in ring:
                if not isinstance(point, list) or len(point) < 2:
                    raise ShorelineLookupError("Authoritative shoreline has invalid coordinates")
                lon, lat = point[0], point[1]
                if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) or not -180 <= lon <= 180 or not -90 <= lat <= 90:
                    raise ShorelineLookupError("Authoritative shoreline has invalid coordinates")
    return {"type": "MultiPolygon", "coordinates": coordinates}


def resolve_shoreline(name: str, latitude: float, longitude: float, bbox: list[float]) -> dict[str, Any]:
    """Resolve a reviewed-source shoreline.

    Phase 2 intentionally has no reviewed shoreline connector registry.  It
    therefore fails closed rather than guessing a public dataset or geometry.
    Deployments add approved connectors here before enabling live lookup.
    """
    del name, latitude, longitude, bbox
    raise ShorelineLookupError("No reviewed shoreline connector is available")
