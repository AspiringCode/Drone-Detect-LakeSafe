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


def _single_cell_hotspot_fixture():
    # Well inside grid_n=2's top-right cell (lat 47.581-47.606, lon
    # -122.091--122.078 for LAKE_BBOX (47.556,-122.104,47.606,-122.078)) and
    # nowhere near any cell boundary, so exactly one grid cell should be
    # suppressed and the other three should pass through untouched.
    incidents = [
        {"lat": 47.598, "lon": -122.083},
        {"lat": 47.599, "lon": -122.0831},
        {"lat": 47.5985, "lon": -122.0825},
    ]
    return incidents, [], []


def test_cluster_suppresses_only_the_grid_cell_it_falls_inside():
    incidents, depths, access = _single_cell_hotspot_fixture()
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
    # The top-right cell (z1-1) contains the hotspot and must be replaced by
    # the cluster; the other three cells must pass through byte-for-byte.
    assert "z1-1" not in [z.zone_id for z in grid_zones]
    assert len(grid_zones) == 3
    for zone in grid_zones:
        assert zone == next(z for z in expected_grid if z.zone_id == zone.zone_id)


def test_grid_never_gets_suppressed_when_cluster_radius_cant_reach_cell_centroids():
    # Regression test for the reported bug: at the demo's real grid_n=3
    # resolution, cells are large enough (multi-km) that a cluster's clamped
    # radius (<=150m) can never reach a cell's own centroid. Suppression must
    # be based on whether the cluster sits INSIDE the cell, not on distance
    # to that cell's centroid -- otherwise every grid cell renders alongside
    # every cluster circle with nothing ever actually replaced.
    incidents, depths, access = _single_cell_hotspot_fixture()
    with (
        patch("app.risk_zones.hybrid.fetch_incidents", return_value=incidents),
        patch("app.risk_zones.hybrid.fetch_depth_contours", return_value=depths),
        patch("app.risk_zones.hybrid.fetch_access_points", return_value=access),
    ):
        zones = compute_hybrid_zones(grid_n=3, use_fixture=True, k=1)

    grid_zone_ids = [z.zone_id for z in zones if not z.zone_id.startswith("cluster-")]
    assert len(grid_zone_ids) == 8  # 9 grid cells minus the one the cluster falls inside
    cluster = next(z for z in zones if z.zone_id.startswith("cluster-"))
    assert cluster.radius_m <= 150.0


def test_sparse_data_produces_no_cluster_and_full_grid_coverage():
    with (
        patch("app.risk_zones.hybrid.fetch_incidents", return_value=[]),
        patch("app.risk_zones.hybrid.fetch_depth_contours", return_value=[]),
        patch("app.risk_zones.hybrid.fetch_access_points", return_value=[]),
    ):
        zones = compute_hybrid_zones(grid_n=2, use_fixture=True, k=1)

    assert len(zones) == 4  # grid_n=2 -> 4 cells, no cluster met MIN_CLUSTER_WEIGHT
    assert all(not z.zone_id.startswith("cluster-") for z in zones)
