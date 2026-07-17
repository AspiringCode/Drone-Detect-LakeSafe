import math

import pytest
from shapely.geometry import Point, Polygon
from shapely.ops import transform, unary_union

from app.models import LatLon
from app.risk_zones.shoreline import load_lake_polygon
from app.risk_zones.tessellation import project, unproject, voronoi_cells


def test_project_scales_longitude_by_mean_latitude_cosine() -> None:
    point = LatLon(47.595, -122.084)

    x, y = project(point, mean_lat=47.581)

    assert x == pytest.approx(point.lon * math.cos(math.radians(47.581)))
    assert y == point.lat


def test_unproject_round_trips_projected_point() -> None:
    point = LatLon(47.595, -122.084)

    round_tripped = unproject(project(point, mean_lat=47.581), mean_lat=47.581)

    assert round_tripped.lat == pytest.approx(point.lat, abs=1e-9)
    assert round_tripped.lon == pytest.approx(point.lon, abs=1e-9)


MEAN_LAT = 47.581


def _projected_sammamish_boundary() -> Polygon:
    scale = math.cos(math.radians(MEAN_LAT))
    boundary = load_lake_polygon("lake-sammamish")
    return transform(lambda x, y, z=None: (x * scale, y), boundary)


def test_voronoi_cells_tile_shoreline_and_assign_each_seed_once() -> None:
    boundary = _projected_sammamish_boundary()
    seeds = [
        LatLon(47.570, -122.090),
        LatLon(47.582, -122.090),
        LatLon(47.595, -122.090),
    ]

    cells = voronoi_cells(seeds, boundary, MEAN_LAT)

    assert [seed for seed, _ in cells] == seeds
    assert all(isinstance(cell, Polygon) for _, cell in cells)
    assert all(cell.difference(boundary).area == pytest.approx(0, abs=1e-12) for _, cell in cells)

    projected_seeds = [Point(project(seed, MEAN_LAT)) for seed in seeds]
    for index, (_, cell) in enumerate(cells):
        assert cell.contains(projected_seeds[index])
        assert all(
            not cell.contains(other_seed)
            for other_index, other_seed in enumerate(projected_seeds)
            if other_index != index
        )

    union = unary_union([cell for _, cell in cells])
    assert union.symmetric_difference(boundary).area == pytest.approx(0, abs=1e-12)
    assert sum(cell.area for _, cell in cells) == pytest.approx(boundary.area, abs=1e-12)


def test_voronoi_cells_single_seed_returns_the_whole_boundary() -> None:
    boundary = _projected_sammamish_boundary()
    seed = LatLon(47.582, -122.090)

    cells = voronoi_cells([seed], boundary, MEAN_LAT)

    assert cells == [(seed, boundary)]


def test_voronoi_cells_deduplicates_seeds_within_one_metre() -> None:
    boundary = _projected_sammamish_boundary()
    seed = LatLon(47.582, -122.090)
    duplicate_within_half_metre = LatLon(47.582 + 0.5 / 111_000, -122.090)

    cells = voronoi_cells([seed, duplicate_within_half_metre], boundary, MEAN_LAT)

    assert cells == [(seed, boundary)]
