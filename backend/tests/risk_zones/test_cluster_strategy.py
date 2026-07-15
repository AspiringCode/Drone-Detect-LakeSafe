from app.models import LatLon
from app.risk_zones.cluster_strategy import ClusterZone, WeightedPoint, ZoneClusterStrategy


class _StubStrategy:
    def refine(self, points, bbox):
        return [
            ClusterZone(
                centroid=LatLon(47.58, -122.09),
                radius_m=50.0,
                weight=3.0,
                member_count=2,
                category_weights={"incidents": 3.0, "depth": 0.0, "crowding": 0.0},
            )
        ]


def test_weighted_point_holds_lat_lon_weight_category():
    p = WeightedPoint(lat=47.58, lon=-122.09, weight=0.5, category="incidents")
    assert (p.lat, p.lon, p.weight, p.category) == (47.58, -122.09, 0.5, "incidents")


def test_cluster_zone_holds_expected_fields():
    z = ClusterZone(
        centroid=LatLon(47.58, -122.09),
        radius_m=50.0,
        weight=3.0,
        member_count=2,
        category_weights={"incidents": 3.0, "depth": 0.0, "crowding": 0.0},
    )
    assert z.radius_m == 50.0
    assert z.member_count == 2


def test_stub_satisfies_protocol_shape():
    strategy: ZoneClusterStrategy = _StubStrategy()
    result = strategy.refine([], (47.556, -122.104, 47.606, -122.078))
    assert len(result) == 1
    assert isinstance(result[0], ClusterZone)


def test_stub_is_runtime_instance_of_protocol():
    assert isinstance(_StubStrategy(), ZoneClusterStrategy)
