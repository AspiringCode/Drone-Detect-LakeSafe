from app.coordination.collision import deconflict, detect_conflicts, detect_segment_conflicts
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


def test_segment_conflict_caught_between_ticks_even_if_not_colocated_at_either_tick():
    # d1 moves straight east, d2 moves straight west; their paths cross the
    # midpoint mid-tick, but at both tick 0 and tick 1 they are >10m apart.
    prev_positions = {
        "d1": LatLon(47.5800, -122.0910),
        "d2": LatLon(47.5800, -122.0890),
    }
    drones = [
        mk_drone("d1", LatLon(47.5800, -122.0890)),
        mk_drone("d2", LatLon(47.5800, -122.0910)),
    ]
    conflicts = detect_segment_conflicts(
        prev_positions, drones, min_sep_m=10.0, altitudes={"d1": 30.0, "d2": 30.0}
    )
    assert ("d1", "d2") in conflicts or ("d2", "d1") in conflicts


def test_segment_conflict_absent_when_paths_never_come_close():
    prev_positions = {
        "d1": LatLon(47.5800, -122.0910),
        "d2": LatLon(47.6000, -122.0800),
    }
    drones = [
        mk_drone("d1", LatLon(47.5801, -122.0911)),
        mk_drone("d2", LatLon(47.6001, -122.0801)),
    ]
    conflicts = detect_segment_conflicts(
        prev_positions, drones, min_sep_m=10.0, altitudes={"d1": 30.0, "d2": 30.0}
    )
    assert conflicts == []
