import math

from shapely.geometry import MultiPoint, Point, Polygon
from shapely.ops import nearest_points, polylabel, transform, voronoi_diagram

from app.coordination.assignment import haversine_m
from app.config import LAKE_BBOX
from app.models import LatLon, RiskZone
from app.risk_zones.cluster_strategy import ClusterZone, WeightedPoint, ZoneClusterStrategy
from app.risk_zones.kmeans_strategy import MAX_RADIUS_M, MIN_RADIUS_M
from app.risk_zones.scoring import INCIDENT_PROXY_THRESHOLD, WEIGHTS
from app.risk_zones.shoreline import load_lake_polygon
from app.risk_zones.socrata_client import (
    fetch_access_points,
    fetch_depth_contours,
    fetch_incidents,
)


SEED_DEDUP_EPS_M = 1.0
PATROL_EDGE_BUFFER_M = 10.0
POLYLABEL_TOLERANCE = 1e-4
RESPONSE_RADIUS_M = 1350.0


def project(point: LatLon, mean_lat: float) -> tuple[float, float]:
    """Project latitude/longitude into a locally scaled Cartesian plane."""
    return point.lon * math.cos(math.radians(mean_lat)), point.lat


def unproject(xy: tuple[float, float], mean_lat: float) -> LatLon:
    """Convert a locally scaled Cartesian coordinate back to latitude/longitude."""
    x, y = xy
    return LatLon(y, x / math.cos(math.radians(mean_lat)))


def patrol_center_and_radius(cell: Polygon, mean_lat: float) -> tuple[LatLon, float]:
    """Return a cell's pole-centred, edge-buffered patrol radius.

    The pole of inaccessibility maximizes clearance from the cell boundary, so
    unlike a risk or coverage seed it provides an interior centre for the
    circular patrol route.
    """
    pole = polylabel(cell, tolerance=POLYLABEL_TOLERANCE)
    _, nearest_edge = nearest_points(pole, cell.exterior)
    center = unproject((pole.x, pole.y), mean_lat)
    edge = unproject((nearest_edge.x, nearest_edge.y), mean_lat)
    clearance_m = haversine_m(center, edge)
    radius_m = clearance_m - PATROL_EDGE_BUFFER_M
    if radius_m < MIN_RADIUS_M:
        raise ValueError(
            "cell clearance cannot accommodate the minimum patrol radius "
            f"of {MIN_RADIUS_M:g} m after the {PATROL_EDGE_BUFFER_M:g} m edge buffer"
        )
    return center, min(MAX_RADIUS_M, radius_m)


def voronoi_cells(
    seeds: list[LatLon], boundary: Polygon, mean_lat: float
) -> list[tuple[LatLon, Polygon]]:
    """Return shoreline-clipped Voronoi cells in the input seed order."""
    unique_seeds = _deduplicate_seeds(seeds, mean_lat)
    if not unique_seeds:
        return []
    if len(unique_seeds) == 1:
        return [(unique_seeds[0], boundary)]

    seed_points = [Point(project(seed, mean_lat)) for seed in unique_seeds]
    regions = voronoi_diagram(MultiPoint(seed_points), envelope=boundary).geoms
    cells: list[tuple[LatLon, Polygon]] = []

    for seed, seed_point in zip(unique_seeds, seed_points, strict=True):
        region = next(region for region in regions if region.contains(seed_point))
        clipped = region.intersection(boundary)
        if isinstance(clipped, Polygon):
            cell = clipped
        else:
            cell = next(piece for piece in clipped.geoms if piece.contains(seed_point))
        cells.append((seed, cell))

    return cells


def _deduplicate_seeds(seeds: list[LatLon], mean_lat: float) -> list[LatLon]:
    """Keep the first seed from each group separated by at least one metre."""
    unique_seeds: list[LatLon] = []
    for seed in seeds:
        if all(_seeds_are_distinct(seed, existing, mean_lat) for existing in unique_seeds):
            unique_seeds.append(seed)
    return unique_seeds


def _seeds_are_distinct(first: LatLon, second: LatLon, mean_lat: float) -> bool:
    """Return whether two seeds are more than the deduplication tolerance apart."""
    metres_per_degree = 111_000
    longitude_scale = math.cos(math.radians(mean_lat))
    return (
        math.hypot(
            (first.lon - second.lon) * longitude_scale,
            first.lat - second.lat,
        )
        * metres_per_degree
        > SEED_DEDUP_EPS_M
    )


def _rows_to_weighted_points(
    incidents: list[dict], depths: list[dict], access: list[dict]
) -> list[WeightedPoint]:
    """Convert source rows to weighted clustering inputs without importing hybrid."""
    points: list[WeightedPoint] = []
    for row in incidents:
        points.append(
            WeightedPoint(float(row["lat"]), float(row["lon"]), WEIGHTS["incidents"], "incidents")
        )
    for row in depths:
        points.append(
            WeightedPoint(
                float(row["lat"]),
                float(row["lon"]),
                WEIGHTS["depth"] * float(row.get("severity", 1.0)),
                "depth",
            )
        )
    for row in access:
        points.append(
            WeightedPoint(
                float(row["lat"]),
                float(row["lon"]),
                WEIGHTS["crowding"] * float(row.get("crowding", 1.0)),
                "crowding",
            )
        )
    return points


def _deduplicate_hotspot_clusters(
    clusters: list[ClusterZone], mean_lat: float
) -> list[ClusterZone]:
    """Keep first hotspot clusters, preserving their cluster-to-seed mapping."""
    surviving: list[ClusterZone] = []
    for cluster in clusters:
        if all(
            _seeds_are_distinct(cluster.centroid, existing.centroid, mean_lat)
            for existing in surviving
        ):
            surviving.append(cluster)
    return surviving


def _farthest_coverage_candidate(
    seeds: list[LatLon], boundary: Polygon, mean_lat: float
) -> tuple[LatLon, float]:
    """Return the sampled shoreline point with the worst nearest-seed response reach."""
    candidates: list[LatLon] = []
    for _, cell in voronoi_cells(seeds, boundary, mean_lat):
        candidates.extend(unproject((x, y), mean_lat) for x, y in cell.exterior.coords[:-1])
        representative = cell.representative_point()
        candidates.append(unproject((representative.x, representative.y), mean_lat))
    return max(
        ((candidate, min(haversine_m(candidate, seed) for seed in seeds)) for candidate in candidates),
        key=lambda item: item[1],
    )


def adaptive_seeds(
    hotspot_seeds: list[LatLon], boundary: Polygon, mean_lat: float, drone_count: int
) -> tuple[list[LatLon], list[str]]:
    """Build bounded hotspot and coverage seeds while reserving one standby drone."""
    if drone_count <= 0:
        raise ValueError("drone_count must be positive")

    capacity = drone_count - 1
    seeds = _deduplicate_seeds(hotspot_seeds, mean_lat)[:capacity]
    kinds = ["hotspot"] * len(seeds)
    while seeds and len(seeds) < capacity:
        candidate, response_reach_m = _farthest_coverage_candidate(seeds, boundary, mean_lat)
        if response_reach_m <= RESPONSE_RADIUS_M:
            break
        seeds.append(candidate)
        kinds.append("coverage")
    return seeds, kinds


def _mean_latitude(boundary: Polygon) -> float:
    return boundary.centroid.y


def _cluster_components(cluster: ClusterZone) -> dict[str, float]:
    total = sum(cluster.category_weights.values()) or 1.0
    return {category: round(weight / total, 6) for category, weight in cluster.category_weights.items()}


def compute_tessellated_zones(
    lake_id: str, drone_count: int, use_fixture: bool = True, strategy: ZoneClusterStrategy | None = None
) -> list[RiskZone]:
    """Tile a lake between hotspot and coverage patrol cells, retaining one standby drone."""
    if drone_count <= 0:
        raise ValueError("drone_count must be positive")

    shoreline = load_lake_polygon(lake_id)
    mean_lat = _mean_latitude(shoreline)
    boundary = transform(
        lambda x, y, z=None: (x * math.cos(math.radians(mean_lat)), y), shoreline
    )
    points = _rows_to_weighted_points(
        fetch_incidents(use_fixture=use_fixture),
        fetch_depth_contours(use_fixture=use_fixture),
        fetch_access_points(use_fixture=use_fixture),
    )
    from app.risk_zones.kmeans_strategy import WeightedKMeansStrategy

    clusters = (strategy or WeightedKMeansStrategy(k=drone_count)).refine(points, bbox=LAKE_BBOX)
    hotspots = _deduplicate_hotspot_clusters(clusters, mean_lat)
    seeds, kinds = adaptive_seeds([cluster.centroid for cluster in hotspots], boundary, mean_lat, drone_count)
    if not seeds:
        return []

    hotspot_by_seed: dict[LatLon, ClusterZone] = {}
    for cluster in hotspots:
        hotspot_by_seed.setdefault(cluster.centroid, cluster)
    max_weight = max((cluster.weight for cluster in hotspots), default=1.0)
    zones: list[RiskZone] = []
    for index, ((seed, cell), kind) in enumerate(zip(voronoi_cells(seeds, boundary, mean_lat), kinds, strict=True)):
        centroid, radius_m = patrol_center_and_radius(cell, mean_lat)
        ring = [unproject((x, y), mean_lat) for x, y in cell.exterior.coords]
        if kind == "coverage":
            risk_score, components, is_proxy = 0.0, {}, True
        else:
            cluster = hotspot_by_seed[seed]
            risk_score = round(cluster.weight / max_weight, 6)
            components = _cluster_components(cluster)
            is_proxy = cluster.member_count < INCIDENT_PROXY_THRESHOLD
        zones.append(
            RiskZone(
                zone_id=f"cell-{index}",
                centroid=centroid,
                polygon=ring,
                risk_score=risk_score,
                components=components,
                is_proxy=is_proxy,
                radius_m=radius_m,
            )
        )
    return zones
