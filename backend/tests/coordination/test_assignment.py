from app.coordination.assignment import assign_zones
from app.models import Drone, DroneStatus, LatLon, RiskZone


def mk_zone(zone_id: str, score: float, at: LatLon = LatLon(47.58, -122.09)) -> RiskZone:
    return RiskZone(zone_id, at, [at, at, at, at], score, {}, is_proxy=False)


def mk_drone(drone_id: str, at: LatLon = LatLon(47.58, -122.09)) -> Drone:
    return Drone(drone_id, at, 1.0, DroneStatus.IDLE, None)


def test_five_drones_get_distinct_zones():
    drones = [mk_drone(f"d{i}", LatLon(47.58 + i * 0.001, -122.09)) for i in range(5)]
    zones = [mk_zone(f"z{i}", 1.0 - i * 0.1, LatLon(47.58 + i * 0.001, -122.09)) for i in range(5)]
    assignment = assign_zones(drones, zones)
    covered = [z for z in assignment.values() if z is not None]
    assert len(covered) == 5
    assert len(set(covered)) == 5


def test_highest_risk_zone_gets_nearest_drone():
    zones = [
        mk_zone("hot", score=1.0, at=LatLon(47.58, -122.09)),
        mk_zone("cool", score=0.1, at=LatLon(47.60, -122.08)),
    ]
    drones = [
        mk_drone("near", at=LatLon(47.581, -122.091)),
        mk_drone("far", at=LatLon(47.601, -122.081)),
    ]
    a = assign_zones(drones, zones)
    assert a["near"] == "hot"


def test_unreachable_zone_not_forced():
    zones = [mk_zone("far_zone", 1.0, LatLon(47.606, -122.078))]
    drones = [mk_drone("d1", LatLon(47.556, -122.104))]
    assignment = assign_zones(drones, zones, max_eta_s=1.0)
    assert assignment["d1"] is None


def test_covers_highest_risk_first_when_short_on_drones():
    zones = [mk_zone("z1", 1.0), mk_zone("z2", 0.9), mk_zone("z3", 0.2)]
    drones = [mk_drone("d1"), mk_drone("d2")]
    a = assign_zones(drones, zones)
    covered = set(a.values())
    assert "z1" in covered and "z2" in covered and "z3" not in covered
