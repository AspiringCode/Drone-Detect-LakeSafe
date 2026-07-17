import math

from shapely.geometry import MultiPoint, Point, Polygon
from shapely.ops import nearest_points, voronoi_diagram

from app.coordination.assignment import haversine_m
from app.models import LatLon, RiskZone
from app.risk_zones.cluster_strategy import ClusterZone, WeightedPoint, ZoneClusterStrategy
from app.risk_zones.kmeans_strategy import MAX_RADIUS_M, MIN_RADIUS_M
from app.risk_zones.kmeans_strategy import WeightedKMeansStrategy
from app.risk_zones.scoring import INCIDENT_PROXY_THRESHOLD, WEIGHTS
from app.risk_zones.shoreline import load_lake_polygon
from app.risk_zones.socrata_client import (
    fetch_access_points,
    fetch_depth_contours,
    fetch_incidents,
)


SEED_DEDUP_EPS_M = 1.0
PATROL_EDGE_BUFFER_M = 10.0
PATROL_SPEED_MPS = 15.0
MAX_ETA_S = 90.0
RESPONSE_RADIUS_M = PATROL_SPEED_MPS * MAX_ETA_S


def project(point: LatLon, mean_lat: float) -> tuple[float, float]:
    """Project latitude/longitude into a locally scaled Cartesian plane."""
    return point.lon * math.cos(math.radians(mean_lat)), point.lat


def unproject(xy: tuple[float, float], mean_lat: float) -> LatLon:
    """Convert a locally scaled Cartesian coordinate back to latitude/longitude."""
    x, y = xy
    return LatLon(y, x / math.cos(math.radians(mean_lat)))


def inscribed_radius(cell: Polygon, seed: LatLon, mean_lat: float) -> float:
    """Return a patrol radius that keeps the required buffer inside ``cell``."""
    projected_seed = Point(project(seed, mean_lat))
    _, nearest_edge = nearest_points(projected_seed, cell.boundary)
    edge_distance_m = haversine_m(
        seed,
        unproject((nearest_edge.x, nearest_edge.y), mean_lat),
    )
    return max(
        MIN_RADIUS_M,
        min(MAX_RADIUS_M, edge_distance_m - PATROL_EDGE_BUFFER_M),
    )


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
    metres_per_degree = 111_000
    longitude_scale = math.cos(math.radians(mean_lat))
    unique_seeds: list[LatLon] = []

    for seed in seeds:
        if all(
            math.hypot(
                (seed.lon - existing.lon) * longitude_scale,
                seed.lat - existing.lat,
            )
            * metres_per_degree
            > SEED_DEDUP_EPS_M
            for existing in unique_seeds
        ):
            unique_seeds.append(seed)

    return unique_seeds


def _worst_response_point(
    cell: Polygon, seeds: list[LatLon], mean_lat: float
) -> tuple[LatLon, float]:
    """Return the sampled point in ``cell`` farthest from every seed."""
    representative = cell.representative_point()
    samples = list(cell.exterior.coords) + [(representative.x, representative.y)]
    best_xy = project(seeds[0], mean_lat)
    best_distance = -1.0
    for x, y in samples:
        candidate = unproject((x, y), mean_lat)
        distance = min(haversine_m(candidate, seed) for seed in seeds)
        if distance > best_distance:
            best_xy = (x, y)
            best_distance = distance
    # Exterior samples are commonly on the shoreline, where a strict
    # ``contains`` check correctly excludes the point. Nudge boundary samples
    # toward the cell's guaranteed-interior representative point so a coverage
    # drone is stationed over water rather than exactly on land's edge.
    if not cell.contains(Point(best_xy)):
        best_xy = (
            best_xy[0] + (representative.x - best_xy[0]) * 1e-6,
            best_xy[1] + (representative.y - best_xy[1]) * 1e-6,
        )
    return unproject(best_xy, mean_lat), best_distance


def adaptive_seeds(
    hotspots: list[LatLon],
    boundary_proj: Polygon,
    mean_lat: float,
    drone_count: int,
    response_radius_m: float = RESPONSE_RADIUS_M,
) -> tuple[list[LatLon], list[str]]:
    """Add greedy k-center coverage seeds only where response reach requires it."""
    seeds = list(hotspots)
    kinds = ["hotspot"] * len(hotspots)
    while seeds and len(seeds) < drone_count:
        worst_point: LatLon | None = None
        worst_distance = -1.0
        for _, cell in voronoi_cells(seeds, boundary_proj, mean_lat):
            point, distance = _worst_response_point(cell, seeds, mean_lat)
            if distance > worst_distance:
                worst_point = point
                worst_distance = distance
        if worst_distance <= response_radius_m:
            break
        assert worst_point is not None
        seeds.append(worst_point)
        kinds.append("coverage")
    return seeds, kinds


def _rows_to_weighted_points(
    incidents: list[dict], depths: list[dict], access: list[dict]
) -> list[WeightedPoint]:
    """Convert raw fixture rows to the weighted k-means input format."""
    points: list[WeightedPoint] = []
    for row in incidents:
        points.append(
            WeightedPoint(
                float(row["lat"]),
                float(row["lon"]),
                WEIGHTS["incidents"],
                "incidents",
            )
        )
    for row in depths:
        severity = float(row.get("severity", 1.0))
        points.append(
            WeightedPoint(
                float(row["lat"]),
                float(row["lon"]),
                WEIGHTS["depth"] * severity,
                "depth",
            )
        )
    for row in access:
        crowding = float(row.get("crowding", 1.0))
        points.append(
            WeightedPoint(
                float(row["lat"]),
                float(row["lon"]),
                WEIGHTS["crowding"] * crowding,
                "crowding",
            )
        )
    return points


def _hotspot_zone(
    seed: LatLon,
    cell_latlon: Polygon,
    cluster: ClusterZone,
    index: int,
    weight_norm: float,
    radius_m: float,
) -> RiskZone:
    ring = [LatLon(lat, lon) for lon, lat in cell_latlon.exterior.coords]
    total = sum(cluster.category_weights.values()) or 1.0
    components = {
        category: round(weight / total, 6)
        for category, weight in cluster.category_weights.items()
    }
    return RiskZone(
        zone_id=f"cell-{index}",
        centroid=seed,
        polygon=ring,
        risk_score=round(weight_norm, 6),
        components=components,
        is_proxy=cluster.member_count < INCIDENT_PROXY_THRESHOLD,
        radius_m=radius_m,
    )


def _coverage_zone(
    seed: LatLon, cell_latlon: Polygon, index: int, radius_m: float
) -> RiskZone:
    ring = [LatLon(lat, lon) for lon, lat in cell_latlon.exterior.coords]
    return RiskZone(
        zone_id=f"cell-{index}",
        centroid=seed,
        polygon=ring,
        risk_score=0.0,
        components={},
        is_proxy=True,
        radius_m=radius_m,
    )


def compute_tessellated_zones(
    lake_id: str,
    drone_count: int,
    use_fixture: bool = True,
    strategy: ZoneClusterStrategy | None = None,
) -> list[RiskZone]:
    """Create shoreline-clipped hotspot and coverage Voronoi zones."""
    lake = load_lake_polygon(lake_id)
    points = _rows_to_weighted_points(
        fetch_incidents(use_fixture=use_fixture),
        fetch_depth_contours(use_fixture=use_fixture),
        fetch_access_points(use_fixture=use_fixture),
    )
    strategy = strategy or WeightedKMeansStrategy(k=drone_count)
    clusters = strategy.refine(points, bbox=lake.bounds)
    if not clusters:
        raise ValueError(f"No risk clusters produced for lake_id={lake_id!r}; cannot tessellate")

    mean_lat = sum(lat for _, lat in lake.exterior.coords) / len(lake.exterior.coords)
    boundary_proj = Polygon(
        [project(LatLon(lat, lon), mean_lat) for lon, lat in lake.exterior.coords]
    )
    hotspot_seeds = [cluster.centroid for cluster in clusters]
    seeds, kinds = adaptive_seeds(hotspot_seeds, boundary_proj, mean_lat, drone_count)
    cells = voronoi_cells(seeds, boundary_proj, mean_lat)
    seed_to_cluster = {id(cluster.centroid): cluster for cluster in clusters}
    kind_by_seed = {id(seed): kind for seed, kind in zip(seeds, kinds, strict=True)}
    max_weight = max(cluster.weight for cluster in clusters)

    zones: list[RiskZone] = []
    for index, (seed, cell_proj) in enumerate(cells):
        radius_m = inscribed_radius(cell_proj, seed, mean_lat)
        cell_latlon = Polygon(
            [
                (unproject((x, y), mean_lat).lon, unproject((x, y), mean_lat).lat)
                for x, y in cell_proj.exterior.coords
            ]
        )
        if kind_by_seed[id(seed)] == "hotspot":
            cluster = seed_to_cluster[id(seed)]
            zones.append(
                _hotspot_zone(
                    seed,
                    cell_latlon,
                    cluster,
                    index,
                    cluster.weight / max_weight,
                    radius_m,
                )
            )
        else:
            zones.append(_coverage_zone(seed, cell_latlon, index, radius_m))
    return zones
