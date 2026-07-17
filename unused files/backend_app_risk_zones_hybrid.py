from __future__ import annotations

from app.config import LAKE_BBOX
from app.coordination.assignment import haversine_m
from app.geo import circle_polygon
from app.models import LatLon, RiskZone
from app.risk_zones.cluster_strategy import WeightedPoint, ZoneClusterStrategy
from app.risk_zones.kmeans_strategy import WeightedKMeansStrategy
from app.risk_zones.scoring import (
    INCIDENT_PROXY_THRESHOLD,
    WEIGHTS,
    compute_risk_zones,
)
from app.risk_zones.socrata_client import (
    fetch_access_points,
    fetch_depth_contours,
    fetch_incidents,
)


def _rows_to_weighted_points(
    incidents: list[dict], depths: list[dict], access: list[dict]
) -> list[WeightedPoint]:
    points: list[WeightedPoint] = []
    for row in incidents:
        points.append(
            WeightedPoint(float(row["lat"]), float(row["lon"]), WEIGHTS["incidents"], "incidents")
        )
    for row in depths:
        severity = float(row.get("severity", 1.0))
        points.append(
            WeightedPoint(
                float(row["lat"]), float(row["lon"]), WEIGHTS["depth"] * severity, "depth"
            )
        )
    for row in access:
        crowding = float(row.get("crowding", 1.0))
        points.append(
            WeightedPoint(
                float(row["lat"]), float(row["lon"]), WEIGHTS["crowding"] * crowding, "crowding"
            )
        )
    return points


def _zone_bounds(zone: RiskZone) -> tuple[float, float, float, float]:
    lats = [p.lat for p in zone.polygon]
    lons = [p.lon for p in zone.polygon]
    return min(lats), min(lons), max(lats), max(lons)


def _contains_point(zone: RiskZone, point: LatLon) -> bool:
    south, west, north, east = _zone_bounds(zone)
    return south <= point.lat <= north and west <= point.lon <= east


def _grid_zone_containing(grid_zones: list[RiskZone], point: LatLon) -> RiskZone | None:
    """The grid cell a cluster centroid geographically falls inside.

    Distance-to-cell-centroid is not a usable test here: grid cells are far
    larger than a cluster's clamped radius (MAX_RADIUS_M=150m vs multi-km grid
    cells), so a cluster can sit squarely inside a cell without its radius
    ever reaching that cell's own centroid. Containment must be checked
    against the cell's bounds, not its centroid. Ties (a point exactly on a
    shared cell boundary/corner) are broken by nearest centroid so exactly
    one cell is suppressed, not every cell touching that boundary.
    """
    containing = [zone for zone in grid_zones if _contains_point(zone, point)]
    if not containing:
        return None
    return min(containing, key=lambda zone: haversine_m(zone.centroid, point))


def _cluster_zone_to_risk_zone(cluster, index: int, weight_norm: float) -> RiskZone:
    total = sum(cluster.category_weights.values()) or 1.0
    components = {cat: round(w / total, 6) for cat, w in cluster.category_weights.items()}
    return RiskZone(
        zone_id=f"cluster-{index}",
        centroid=cluster.centroid,
        polygon=circle_polygon(cluster.centroid, cluster.radius_m),
        risk_score=round(weight_norm, 6),
        components=components,
        is_proxy=cluster.member_count < INCIDENT_PROXY_THRESHOLD,
        radius_m=cluster.radius_m,
    )


def compute_hybrid_zones(
    grid_n: int = 3,
    use_fixture: bool = True,
    strategy: ZoneClusterStrategy | None = None,
    k: int | None = None,
) -> list[RiskZone]:
    """Grid coverage floor plus cluster-strategy refinement."""
    grid_zones = compute_risk_zones(grid_n=grid_n, use_fixture=use_fixture)

    incidents = fetch_incidents(use_fixture=use_fixture)
    depths = fetch_depth_contours(use_fixture=use_fixture)
    access = fetch_access_points(use_fixture=use_fixture)
    points = _rows_to_weighted_points(incidents, depths, access)

    strategy = strategy or WeightedKMeansStrategy(k=k)
    clusters = strategy.refine(points, bbox=LAKE_BBOX)
    if not clusters:
        return grid_zones

    max_weight = max(cluster.weight for cluster in clusters)
    suppressed_ids = {
        containing.zone_id
        for cluster in clusters
        for containing in [_grid_zone_containing(grid_zones, cluster.centroid)]
        if containing is not None
    }
    surviving_grid = [zone for zone in grid_zones if zone.zone_id not in suppressed_ids]
    cluster_zones = [
        _cluster_zone_to_risk_zone(cluster, index, cluster.weight / max_weight)
        for index, cluster in enumerate(clusters)
    ]
    return surviving_grid + cluster_zones
