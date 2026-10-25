from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx
from shapely.geometry import Point, Polygon, shape


# King County GIS catalog item 2a4c8808713946d8ac22e9b7b27b284f.
WATERBODY_QUERY_URL = "https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/WTRBDY_AREA_485/FeatureServer/0/query"


class ShorelineLookupError(ValueError):
    """An authoritative shoreline was unavailable or geometrically invalid."""


def esri_shoreline(geometry: Mapping[str, Any]) -> dict[str, Any]:
    if geometry.get("type") in {"Polygon", "MultiPolygon"}:
        return normalize_shoreline(geometry)
    rings = geometry.get("rings")
    if not isinstance(rings, list) or not rings:
        raise ShorelineLookupError("Source shoreline has no rings")
    shells, holes = [], []
    for ring in rings:
        normalize_shoreline({"type": "Polygon", "coordinates": [ring]})
        polygon = Polygon(ring)
        (holes if polygon.exterior.is_ccw else shells).append(polygon)
    if not shells:
        raise ShorelineLookupError("Source shoreline has no exterior")
    assigned = [[] for _ in shells]
    for hole in holes:
        owners = [(shell.area, index) for index, shell in enumerate(shells) if shell.covers(hole)]
        if not owners:
            raise ShorelineLookupError("Source island is outside its shoreline")
        assigned[min(owners)[1]].append(list(hole.exterior.coords))
    coordinates = [[list(shell.exterior.coords), *assigned[index]] for index, shell in enumerate(shells)]
    # ArcGIS exteriors are clockwise; its GeoJSON conversion can misclassify islands.
    return normalize_shoreline({"type": "MultiPolygon", "coordinates": _lists(coordinates)})


def _lists(value):
    return [_lists(item) for item in value] if isinstance(value, (list, tuple)) else value


def _official_features(where: str, **parameters) -> list[dict]:
    response = httpx.get(WATERBODY_QUERY_URL, params={
        "f": "json", "where": where, "outSR": 4326,
        "outFields": "OBJECTID,NAME,FEATURE_ID,FEAT_TYPE,WATER", "returnGeometry": "true",
        "resultRecordCount": 9, **parameters,
    }, timeout=15.0)
    response.raise_for_status()
    payload = response.json()
    if payload.get("error") or not isinstance(payload.get("features"), list):
        raise ShorelineLookupError("Shoreline source is unavailable")
    return payload["features"]


def _candidate(feature: dict, component_index: int = 0) -> dict:
    properties = feature.get("attributes") or feature.get("properties") or {}
    if properties.get("FEAT_TYPE") not in {"Lake or pond", "Impoundment"} or properties.get("WATER") != "Water":
        raise ShorelineLookupError("Source feature is not a lake")
    geometry = esri_shoreline(feature.get("geometry") or {})
    parts = sorted(shape(geometry).geoms, key=lambda part: (-part.area, part.bounds))
    if not 0 <= component_index < len(parts):
        raise ShorelineLookupError("This shoreline area is no longer available")
    polygon = parts[component_index]
    geometry = {"type": "MultiPolygon", "coordinates": [geometry_part(polygon)]}
    point = polygon.representative_point()
    return {"candidate_id": int(properties["OBJECTID"]), "component_index": component_index,
            "component_count": len(parts), "area_label": ("Lake shoreline" if len(parts) == 1 else "Main waterbody" if component_index == 0 else f"Separate waterbody {component_index + 1}"), "name": properties["NAME"],
            "shoreline": geometry, "centroid_lat": point.y, "centroid_lon": point.x,
            "bounds": list(polygon.bounds), "source": "King County GIS"}


def geometry_part(polygon):
    return _lists([list(polygon.exterior.coords), *[list(ring.coords) for ring in polygon.interiors]])


def search_lakes(query: str) -> list[dict]:
    query = " ".join(query.split())
    if len(query) < 2 or len(query) > 100 or any(not (char.isalnum() or char in " '-.") for char in query):
        raise ShorelineLookupError("Enter at least two letters of the lake name")
    escaped = query.lower().replace("'", "''")
    try:
        features = _official_features(f"WATER = 'Water' AND FEAT_TYPE IN ('Lake or pond', 'Impoundment') AND LOWER(NAME) LIKE '%{escaped}%'", orderByFields="NAME,OBJECTID")
        candidates = []
        for feature in features[:8]:
            try:
                first = _candidate(feature)
                candidates.append(first)
                candidates.extend(_candidate(feature, index) for index in range(1, min(first["component_count"], 4)))
            except (ValueError, KeyError, TypeError):
                continue
        return candidates[:8]
    except (httpx.HTTPError, ValueError, TypeError, AttributeError, KeyError) as exc:
        raise ShorelineLookupError("Lake search is unavailable. Try again shortly.") from exc


def selected_lake(candidate_id: int, component_index: int = 0) -> dict:
    try:
        features = _official_features(f"OBJECTID = {int(candidate_id)} AND WATER = 'Water'")
        if len(features) != 1:
            raise ShorelineLookupError("Lake selection is no longer available. Search again.")
        return _candidate(features[0], component_index)
    except (httpx.HTTPError, ValueError, TypeError, AttributeError, KeyError) as exc:
        raise ShorelineLookupError("Lake selection could not be verified. Search again.") from exc


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
            "f": "json", "geometry": f"{longitude},{latitude}",
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
            properties = feature.get("attributes") or feature.get("properties") or {}
            actual_name = " ".join(str(properties.get("NAME") or "").casefold().split())
            if actual_name != expected_name or properties.get("FEAT_TYPE") not in {"Lake or pond", "Impoundment"} or properties.get("WATER") != "Water":
                continue
            geometry = esri_shoreline(feature.get("geometry") or {})
            if shape(geometry).covers(Point(longitude, latitude)):
                matches.append(geometry)
        if len(matches) != 1:
            raise ShorelineLookupError("No unique named lake shoreline was found at this location")
        return matches[0]
    except (httpx.HTTPError, ValueError, TypeError, AttributeError, KeyError) as exc:
        raise ShorelineLookupError("Authoritative shoreline data is unavailable") from exc
