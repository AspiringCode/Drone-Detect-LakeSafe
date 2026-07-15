from unittest.mock import patch

from app.models import LatLon
from app.risk_zones.hybrid import compute_hybrid_zones
from app.risk_zones.kmeans_strategy import MIN_RADIUS_M
from app.risk_zones.scoring import compute_risk_zones


def _boundary_straddling_fixture():
    # grid_n=2 over LAKE_BBOX (47.556, -122.104, 47.606, -122.078) puts the
    # row boundary at lat 47.581. Place a tight incident cluster straddling
    # that exact boundary: half the points just below it, half just above.
    incidents = [
        {"lat": 47.5809, "lon": -122.091},
        {"lat": 47.5808, "lon": -122.0911},
        {"lat": 47.5811, "lon": -122.0909},
        {"lat": 47.5812, "lon": -122.091},
    ]
    return incidents, [], []


def test_boundary_straddling_hotspot_gets_one_precise_cluster_not_diluted_grid_cells():
    incidents, depths, access = _boundary_straddling_fixture()
    with (
        patch("app.risk_zones.hybrid.fetch_incidents", return_value=incidents),
        patch("app.risk_zones.hybrid.fetch_depth_contours", return_value=depths),
        patch("app.risk_zones.hybrid.fetch_access_points", return_value=access),
    ):
        zones = compute_hybrid_zones(grid_n=2, use_fixture=True, k=1)

    clusters = [z for z in zones if z.zone_id.startswith("cluster-")]
    assert len(clusters) == 1
    cluster = clusters[0]
    # True hotspot center is ~47.581, not diluted toward either grid cell's
    # own centroid (which would sit further from 47.581 for grid_n=2).
    assert abs(cluster.centroid.lat - 47.581) < 0.001
    assert cluster.radius_m >= MIN_RADIUS_M


def test_grid_cells_outside_any_cluster_pass_through_unchanged():
    incidents, depths, access = _boundary_straddling_fixture()
    with (
        patch("app.risk_zones.hybrid.fetch_incidents", return_value=incidents),
        patch("app.risk_zones.hybrid.fetch_depth_contours", return_value=depths),
        patch("app.risk_zones.hybrid.fetch_access_points", return_value=access),
        patch("app.risk_zones.scoring.fetch_incidents", return_value=incidents),
        patch("app.risk_zones.scoring.fetch_depth_contours", return_value=depths),
        patch("app.risk_zones.scoring.fetch_access_points", return_value=access),
    ):
        zones = compute_hybrid_zones(grid_n=2, use_fixture=True, k=1)
        expected_grid = compute_risk_zones(grid_n=2, use_fixture=True)

    grid_zones = [z for z in zones if not z.zone_id.startswith("cluster-")]
    assert [zone.zone_id for zone in grid_zones] == [zone.zone_id for zone in expected_grid]
    assert grid_zones == expected_grid


def test_sparse_data_produces_no_cluster_and_full_grid_coverage():
    with (
        patch("app.risk_zones.hybrid.fetch_incidents", return_value=[]),
        patch("app.risk_zones.hybrid.fetch_depth_contours", return_value=[]),
        patch("app.risk_zones.hybrid.fetch_access_points", return_value=[]),
    ):
        zones = compute_hybrid_zones(grid_n=2, use_fixture=True, k=1)

    assert len(zones) == 4  # grid_n=2 -> 4 cells, no cluster met MIN_CLUSTER_WEIGHT
    assert all(not z.zone_id.startswith("cluster-") for z in zones)
