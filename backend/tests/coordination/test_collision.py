from app.coordination.collision import deconflict, detect_conflicts
from app.models import Drone, DroneStatus, LatLon


def mk_drone(drone_id: str, at: LatLon) -> Drone:
    return Drone(drone_id, at, 1.0, DroneStatus.PATROLLING, None)


def test_detects_same_altitude_horizontal_conflict():
    drones = [
        mk_drone("d1", LatLon(47.58, -122.09)),
        mk_drone("d2", LatLon(47.58001, -122.09001)),
    ]
    assert detect_conflicts(drones, min_sep_m=10.0, altitudes={"d1": 30.0, "d2": 30.0}) == [("d1", "d2")]


def test_deconflict_assigns_conflict_free_altitude_bands():
    drones = [
        mk_drone("d1", LatLon(47.58, -122.09)),
        mk_drone("d2", LatLon(47.58001, -122.09001)),
    ]
    altitudes = deconflict(drones, {"d1": 30.0, "d2": 30.0})
    assert detect_conflicts(drones, min_sep_m=10.0, altitudes=altitudes) == []
