import random

from app.risk_zones.cluster_strategy import WeightedPoint
from app.risk_zones.kmeans_strategy import WeightedKMeansStrategy

BBOX = (47.556, -122.104, 47.606, -122.078)


def _two_tight_clusters() -> list[WeightedPoint]:
    # Cluster A: 4 points tightly packed near (47.58, -122.09), heavy weight.
    # Cluster B: 4 points tightly packed near (47.60, -122.08), heavy weight.
    # Far apart relative to point spread, so k=2 must recover them cleanly.
    a = [
        WeightedPoint(47.5800, -122.0900, 1.0, "incidents"),
        WeightedPoint(47.5801, -122.0901, 1.0, "incidents"),
        WeightedPoint(47.5799, -122.0899, 0.5, "depth"),
        WeightedPoint(47.5800, -122.0899, 0.5, "crowding"),
    ]
    b = [
        WeightedPoint(47.6000, -122.0800, 1.0, "incidents"),
        WeightedPoint(47.6001, -122.0801, 1.0, "incidents"),
        WeightedPoint(47.5999, -122.0799, 0.5, "depth"),
        WeightedPoint(47.6000, -122.0799, 0.5, "crowding"),
    ]
    return a + b


def test_recovers_two_well_separated_clusters():
    strategy = WeightedKMeansStrategy(k=2, seed=42)
    zones = strategy.refine(_two_tight_clusters(), BBOX)
    assert len(zones) == 2
    centroids = sorted((z.centroid.lat, z.centroid.lon) for z in zones)
    assert abs(centroids[0][0] - 47.580) < 0.01
    assert abs(centroids[1][0] - 47.600) < 0.01


def test_is_deterministic_across_runs():
    points = _two_tight_clusters()
    first = WeightedKMeansStrategy(k=2, seed=42).refine(points, BBOX)
    second = WeightedKMeansStrategy(k=2, seed=42).refine(points, BBOX)
    assert [(z.centroid.lat, z.centroid.lon) for z in first] == [
        (z.centroid.lat, z.centroid.lon) for z in second
    ]


def test_category_weights_sum_correctly_per_cluster():
    zones = WeightedKMeansStrategy(k=2, seed=42).refine(_two_tight_clusters(), BBOX)
    for zone in zones:
        assert sum(zone.category_weights.values()) == zone.weight
        assert zone.category_weights.keys() == {"incidents", "depth", "crowding"}


def test_radius_is_clamped_to_bounds():
    # A single outlier point paired with a tight cluster must not blow the
    # radius past MAX_RADIUS_M, and a perfectly collinear/duplicate cluster
    # must not collapse below MIN_RADIUS_M.
    from app.risk_zones.kmeans_strategy import MAX_RADIUS_M, MIN_RADIUS_M

    duplicate_points = [WeightedPoint(47.58, -122.09, 1.0, "incidents") for _ in range(3)]
    zones = WeightedKMeansStrategy(k=1, seed=42).refine(duplicate_points, BBOX)
    assert zones[0].radius_m == MIN_RADIUS_M

    far_outlier = _two_tight_clusters()[:4] + [WeightedPoint(47.60, -122.08, 0.01, "incidents")]
    zones = WeightedKMeansStrategy(k=1, seed=42).refine(far_outlier, BBOX)
    assert zones[0].radius_m <= MAX_RADIUS_M


def test_drops_clusters_below_min_cluster_weight():
    from app.risk_zones.kmeans_strategy import MIN_CLUSTER_WEIGHT

    sparse = [WeightedPoint(47.58, -122.09, MIN_CLUSTER_WEIGHT / 4, "crowding")]
    zones = WeightedKMeansStrategy(k=1, seed=42).refine(sparse, BBOX)
    assert zones == []
