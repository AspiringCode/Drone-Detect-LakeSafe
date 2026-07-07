from app.coordination.battery import needs_return, reassign_on_low_battery
from app.models import Drone, DroneStatus, LatLon, RiskZone


def mk_drone(drone_id: str, battery: float, assigned: str | None = None) -> Drone:
    return Drone(drone_id, LatLon(47.58, -122.09), battery, DroneStatus.PATROLLING, assigned)


def mk_zone(zone_id: str) -> RiskZone:
    at = LatLon(47.58, -122.09)
    return RiskZone(zone_id, at, [at, at, at, at], 1.0, {}, is_proxy=False)


def test_needs_return_true_below_reserve():
    assert needs_return(mk_drone("d1", 0.2), reserve=0.25) is True
    assert needs_return(mk_drone("d2", 0.3), reserve=0.25) is False


def test_low_battery_zone_reassigned_to_charged_free_drone():
    drones = [mk_drone("low", 0.1, "z1"), mk_drone("fresh", 0.9, None)]
    assignment = {"low": "z1", "fresh": None}
    updated = reassign_on_low_battery(drones, [mk_zone("z1")], assignment)
    assert drones[0].status == DroneStatus.RETURNING
    assert updated["low"] is None
    assert updated["fresh"] == "z1"
