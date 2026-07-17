import math

from shapely.geometry import MultiPoint, Point, Polygon
from shapely.ops import nearest_points, polylabel, voronoi_diagram

from app.coordination.assignment import haversine_m
from app.models import LatLon
from app.risk_zones.kmeans_strategy import MAX_RADIUS_M, MIN_RADIUS_M


SEED_DEDUP_EPS_M = 1.0
PATROL_EDGE_BUFFER_M = 10.0
POLYLABEL_TOLERANCE = 1e-4


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
    return center, max(MIN_RADIUS_M, min(MAX_RADIUS_M, radius_m))


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
