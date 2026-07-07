from __future__ import annotations

from app.config import LAKE_BBOX
from app.models import LatLon, RiskZone
from app.risk_zones.socrata_client import (
    fetch_access_points,
    fetch_depth_contours,
    fetch_incidents,
)

INCIDENT_PROXY_THRESHOLD = 2
WEIGHTS = {"incidents": 0.5, "depth": 0.3, "crowding": 0.2}


def _cell_bounds(row: int, col: int, grid_n: int) -> tuple[float, float, float, float]:
    min_lat, min_lon, max_lat, max_lon = LAKE_BBOX
    lat_step = (max_lat - min_lat) / grid_n
    lon_step = (max_lon - min_lon) / grid_n
    south = min_lat + row * lat_step
    north = south + lat_step
    west = min_lon + col * lon_step
    east = west + lon_step
    return south, west, north, east


def _contains(row: int, col: int, grid_n: int, lat: float, lon: float) -> bool:
    south, west, north, east = _cell_bounds(row, col, grid_n)
    is_last_row = row == grid_n - 1
    is_last_col = col == grid_n - 1
    lat_ok = south <= lat <= north if is_last_row else south <= lat < north
    lon_ok = west <= lon <= east if is_last_col else west <= lon < east
    return lat_ok and lon_ok


def _sum_rows(rows: list[dict], row: int, col: int, grid_n: int, value_key: str | None) -> float:
    total = 0.0
    for item in rows:
        lat = float(item["lat"])
        lon = float(item["lon"])
        if _contains(row, col, grid_n, lat, lon):
            total += float(item.get(value_key, 1.0)) if value_key else 1.0
    return total


def _normalize(values: list[float]) -> list[float]:
    low = min(values)
    high = max(values)
    if high == low:
        return [0.0 for _ in values]
    return [(v - low) / (high - low) for v in values]


def _polygon(south: float, west: float, north: float, east: float) -> list[LatLon]:
    return [
        LatLon(south, west),
        LatLon(south, east),
        LatLon(north, east),
        LatLon(north, west),
        LatLon(south, west),
    ]


def compute_risk_zones(grid_n: int = 5, use_fixture: bool = False) -> list[RiskZone]:
    """Compute Lake Sammamish risk cells from incidents plus proxy factors.

    Raw score uses weights 0.5 incident density, 0.3 depth-change severity, and
    0.2 access-point crowding. Cells with fewer than 2 incident rows are marked
    `is_proxy=True` because depth/crowding proxy estimates dominate disclosure.
    """
    incidents = fetch_incidents(use_fixture=use_fixture)
    depths = fetch_depth_contours(use_fixture=use_fixture)
    access = fetch_access_points(use_fixture=use_fixture)

    cells: list[dict[str, float | int]] = []
    for row in range(grid_n):
        for col in range(grid_n):
            incident_count = _sum_rows(incidents, row, col, grid_n, None)
            depth = _sum_rows(depths, row, col, grid_n, "severity")
            crowding = _sum_rows(access, row, col, grid_n, "crowding")
            cells.append(
                {
                    "row": row,
                    "col": col,
                    "incident_count": incident_count,
                    "depth_raw": depth,
                    "crowding_raw": crowding,
                }
            )

    incident_norm = _normalize([float(c["incident_count"]) for c in cells])
    depth_norm = _normalize([float(c["depth_raw"]) for c in cells])
    crowding_norm = _normalize([float(c["crowding_raw"]) for c in cells])
    raw_scores = [
        WEIGHTS["incidents"] * incident_norm[i]
        + WEIGHTS["depth"] * depth_norm[i]
        + WEIGHTS["crowding"] * crowding_norm[i]
        for i in range(len(cells))
    ]
    score_norm = _normalize(raw_scores)

    zones: list[RiskZone] = []
    for i, cell in enumerate(cells):
        row = int(cell["row"])
        col = int(cell["col"])
        south, west, north, east = _cell_bounds(row, col, grid_n)
        zones.append(
            RiskZone(
                zone_id=f"z{row}-{col}",
                centroid=LatLon((south + north) / 2, (west + east) / 2),
                polygon=_polygon(south, west, north, east),
                risk_score=round(score_norm[i], 6),
                components={
                    "incidents": round(incident_norm[i], 6),
                    "depth": round(depth_norm[i], 6),
                    "crowding": round(crowding_norm[i], 6),
                },
                is_proxy=float(cell["incident_count"]) < INCIDENT_PROXY_THRESHOLD,
            )
        )
    return zones
