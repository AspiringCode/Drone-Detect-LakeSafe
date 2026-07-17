import math

import pytest
from shapely.geometry import Point, Polygon
from shapely.ops import transform, unary_union

from app.models import LatLon
from app.coordination.assignment import haversine_m
from app.risk_zones.cluster_strategy import ClusterZone
from app.risk_zones.shoreline import load_lake_polygon
from app.geo import destination_point
from app.risk_zones.kmeans_strategy import MAX_RADIUS_M, MIN_RADIUS_M
from app.risk_zones.tessellation import (
    RESPONSE_RADIUS_M,
    adaptive_seeds,
    compute_tessellated_zones,
    patrol_center_and_radius,
    project,
    unproject,
    voronoi_cells,
)


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


def test_tessellated_scores_normalized_and_coverage_cells_proxy_flagged() -> None:
    zones = compute_tessellated_zones("lake-sammamish", drone_count=5, use_fixture=True)

    assert zones
    assert all(0.0 <= zone.risk_score <= 1.0 for zone in zones)
    assert any(zone.is_proxy for zone in zones)
    assert max(zone.risk_score for zone in zones) == 1.0
    assert min(zone.risk_score for zone in zones) == 0.0


def test_tessellated_hotspot_with_incidents_is_not_proxy() -> None:
    zones = compute_tessellated_zones("lake-sammamish", drone_count=5, use_fixture=True)
    hotspot_zones = [zone for zone in zones if "incidents" in zone.components]
    hot = max(hotspot_zones, key=lambda zone: zone.components["incidents"])

    assert hot.components["incidents"] > 0.0
    assert hot.is_proxy is False


def test_tessellated_coverage_cell_is_proxy() -> None:
    zones = compute_tessellated_zones("lake-sammamish", drone_count=5, use_fixture=True)
    proxy = next(zone for zone in zones if not zone.components)

    assert proxy.is_proxy is True


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


def test_voronoi_cells_cover_shoreline_with_two_non_collinear_seeds() -> None:
    boundary = _projected_sammamish_boundary()
    seeds = [
        LatLon(47.5820, -122.0900),
        LatLon(47.5825, -122.0897),
    ]

    cells = voronoi_cells(seeds, boundary, MEAN_LAT)

    union = unary_union([cell for _, cell in cells])
    assert boundary.difference(union).area == pytest.approx(0, abs=1e-12)


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


def test_patrol_circle_stays_inside_every_generated_cell_at_all_bearings() -> None:
    boundary = _projected_sammamish_boundary()
    cells = voronoi_cells(
        [
            LatLon(47.595, -122.092),
            LatLon(47.581, -122.090),
            LatLon(47.565, -122.091),
        ],
        boundary,
        MEAN_LAT,
    )

    for _, cell in cells:
        center, radius_m = patrol_center_and_radius(cell, MEAN_LAT)
        assert MIN_RADIUS_M <= radius_m <= MAX_RADIUS_M
        assert cell.contains(Point(project(center, MEAN_LAT)))
        for bearing in range(360):
            waypoint = destination_point(center, float(bearing), radius_m)
            assert cell.buffer(1e-9).contains(Point(project(waypoint, MEAN_LAT)))


def test_patrol_rejects_narrow_cell_that_cannot_fit_minimum_circle_at_all_bearings() -> None:
    """A 40 m-wide cell has only 10 m of radius after the 10 m edge buffer."""
    metres_per_degree = 111_000
    center = LatLon(MEAN_LAT, -122.09)
    half_width_degrees = 20 / metres_per_degree
    half_height_degrees = 40 / metres_per_degree
    center_x, center_y = project(center, MEAN_LAT)
    cell = Polygon(
        [
            (center_x - half_width_degrees * math.cos(math.radians(MEAN_LAT)), center_y - half_height_degrees),
            (center_x + half_width_degrees * math.cos(math.radians(MEAN_LAT)), center_y - half_height_degrees),
            (center_x + half_width_degrees * math.cos(math.radians(MEAN_LAT)), center_y + half_height_degrees),
            (center_x - half_width_degrees * math.cos(math.radians(MEAN_LAT)), center_y + half_height_degrees),
        ]
    )

    with pytest.raises(ValueError, match="minimum patrol radius"):
        patrol_center_and_radius(cell, MEAN_LAT)


def test_demo_four_final_cells_clamp_to_150m_and_patrols_remain_in_lake() -> None:
    """The four-cell fixture geometry used by the committed Lake Sammamish demo."""
    boundary = _projected_sammamish_boundary()
    demo_seeds = [
        LatLon(47.58051284634761, -122.09101863979849),
        LatLon(47.599119626168225, -122.0838831775701),
        LatLon(47.557000019, -122.09199999774616),
        LatLon(47.568608070855994, -122.08369597431815),
    ]
    cells = voronoi_cells(demo_seeds, boundary, MEAN_LAT)

    assert len(cells) == 4
    for _, cell in cells:
        center, radius_m = patrol_center_and_radius(cell, MEAN_LAT)
        assert radius_m == MAX_RADIUS_M == 150.0
        for bearing in range(360):
            waypoint = destination_point(center, float(bearing), radius_m)
            projected_waypoint = Point(project(waypoint, MEAN_LAT))
            assert cell.buffer(1e-9).contains(projected_waypoint)
            assert boundary.buffer(1e-9).contains(projected_waypoint)


def test_adaptive_seeds_deduplicates_hotspots_before_reserving_fleet_capacity() -> None:
    boundary = _projected_sammamish_boundary()
    hotspot = LatLon(47.5805, -122.0910)
    duplicate = LatLon(47.5805 + 0.5 / 111_000, -122.0910)

    seeds, kinds = adaptive_seeds(
        [hotspot, duplicate, LatLon(47.5991, -122.0839)], boundary, MEAN_LAT, drone_count=3
    )

    assert seeds[:2] == [hotspot, LatLon(47.5991, -122.0839)]
    assert kinds[:2] == ["hotspot", "hotspot"]
    assert len(seeds) <= 2  # one drone is always kept on standby


def test_duplicate_hotspot_centroids_retain_first_cluster_metadata() -> None:
    first = ClusterZone(
        centroid=LatLon(47.5805, -122.0910), radius_m=40, weight=10, member_count=3,
        category_weights={"incidents": 10},
    )
    duplicate = ClusterZone(
        centroid=first.centroid, radius_m=40, weight=100, member_count=1,
        category_weights={"crowding": 100},
    )
    second = ClusterZone(
        centroid=LatLon(47.5991, -122.0839), radius_m=40, weight=5, member_count=2,
        category_weights={"depth": 5},
    )

    class DuplicateCentroidStrategy:
        def refine(self, points, bbox):
            return [first, duplicate, second]

    zones = compute_tessellated_zones(
        "lake-sammamish", drone_count=3, use_fixture=True, strategy=DuplicateCentroidStrategy()
    )

    assert len(zones) == 2
    assert {frozenset(zone.components) for zone in zones} == {
        frozenset({"incidents"}),
        frozenset({"depth"}),
    }


def test_adaptive_seeds_adds_coverage_only_when_response_reach_exceeds_limit() -> None:
    boundary = _projected_sammamish_boundary()
    seeds, kinds = adaptive_seeds([LatLon(47.5805, -122.0910)], boundary, MEAN_LAT, drone_count=5)

    assert len(seeds) <= 4
    assert kinds[0] == "hotspot"
    assert all(kind == "coverage" for kind in kinds[1:])
    assert any(kind == "coverage" for kind in kinds)
    for seed, kind in zip(seeds, kinds, strict=True):
        if kind == "coverage":
            assert min(haversine_m(seed, other) for other in seeds if other != seed) > RESPONSE_RADIUS_M


def test_tessellated_pipeline_rejects_a_non_positive_drone_count() -> None:
    with pytest.raises(ValueError, match="drone_count"):
        compute_tessellated_zones("lake-sammamish", drone_count=0)


def test_fixture_pipeline_has_two_hotspots_two_coverage_cells_and_a_standby_drone() -> None:
    zones = compute_tessellated_zones("lake-sammamish", drone_count=5)
    lake = load_lake_polygon("lake-sammamish")
    projected_boundary = _projected_sammamish_boundary()

    assert len(zones) == 4
    assert len(zones) < 5
    hotspot_zones = [zone for zone in zones if zone.risk_score > 0]
    coverage_zones = [zone for zone in zones if zone.risk_score == 0]
    assert len(hotspot_zones) == 2
    assert len(coverage_zones) == 2
    assert all(zone.components == {} and zone.is_proxy for zone in coverage_zones)
    assert all(zone.radius_m == MAX_RADIUS_M == 150.0 for zone in zones)
    assert all(lake.contains(Point(zone.centroid.lon, zone.centroid.lat)) for zone in zones)

    zone_polygons = [
        Polygon([(point.lon, point.lat) for point in zone.polygon]) for zone in zones
    ]
    assert unary_union(zone_polygons).symmetric_difference(lake).area == pytest.approx(0, abs=1e-12)

    for zone in zones:
        zone_cell = Polygon([(point.lon * math.cos(math.radians(MEAN_LAT)), point.lat) for point in zone.polygon])
        assert zone.polygon[0] == zone.polygon[-1]
        for bearing in range(360):
            waypoint = destination_point(zone.centroid, float(bearing), zone.radius_m)
            projected_waypoint = Point(project(waypoint, MEAN_LAT))
            assert zone_cell.buffer(1e-9).contains(projected_waypoint)
            assert projected_boundary.buffer(1e-9).contains(projected_waypoint)
