from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx
from shapely.geometry import Point, shape


# King County GIS catalog item 2a4c8808713946d8ac22e9b7b27b284f.
WATERBODY_QUERY_URL = "https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/WTRBDY_AREA_485/FeatureServer/0/query"


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
            if ring[0] != ring[-1]:
                raise ShorelineLookupError("Authoritative shoreline has an unclosed ring")
            for point in ring:
                if not isinstance(point, list) or len(point) < 2:
                    raise ShorelineLookupError("Authoritative shoreline has invalid coordinates")
                lon, lat = point[0], point[1]
                if isinstance(lat, bool) or isinstance(lon, bool) or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) or not -180 <= lon <= 180 or not -90 <= lat <= 90:
                    raise ShorelineLookupError("Authoritative shoreline has invalid coordinates")
    result = {"type": "MultiPolygon", "coordinates": coordinates}
    polygon = shape(result)
    if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
        raise ShorelineLookupError("Authoritative shoreline has invalid topology")
    return result


def resolve_shoreline(name: str, latitude: float, longitude: float, bbox: list[float]) -> dict[str, Any]:
    """Find a named water polygon at the point in King County's public layer.

    This source establishes shoreline geometry only, not reviewed incident or
    risk coverage. Never clip a lake to the search box or substitute fixtures.
    """
    west, south, east, north = bbox
    if not west <= longitude <= east or not south <= latitude <= north:
        raise ShorelineLookupError("Lake location must be within the search area")
    try:
        response = httpx.get(WATERBODY_QUERY_URL, params={
            "f": "geojson", "geometry": f"{longitude},{latitude}",
            "geometryType": "esriGeometryPoint", "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects", "outSR": 4326,
            "outFields": "NAME,FEATURE_ID,FEAT_TYPE,WATER", "returnGeometry": "true",
            "where": "WATER = 'Water'", "resultRecordCount": 10,
        }, timeout=10.0)
        response.raise_for_status()
        payload = response.json()
        if payload.get("error") or payload.get("exceededTransferLimit") or not isinstance(payload.get("features"), list):
            raise ShorelineLookupError("Shoreline publisher returned incomplete data")
        matches = []
        expected_name = " ".join(name.casefold().split())
        for feature in payload["features"]:
            properties = feature.get("properties") or {}
            actual_name = " ".join(str(properties.get("NAME") or "").casefold().split())
            if actual_name != expected_name or properties.get("FEAT_TYPE") not in {"Lake or pond", "Impoundment"} or properties.get("WATER") != "Water":
                continue
            geometry = normalize_shoreline(feature.get("geometry") or {})
            if shape(geometry).covers(Point(longitude, latitude)):
                matches.append(geometry)
        if len(matches) != 1:
            raise ShorelineLookupError("No unique named lake shoreline was found at this location")
        return matches[0]
    except (httpx.HTTPError, ValueError, TypeError, AttributeError, KeyError) as exc:
        raise ShorelineLookupError("Authoritative shoreline data is unavailable") from exc
