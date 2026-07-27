import pytest

from app.missions.qgc_plan import build_patrol_plan
from app.models import LatLon

CENTER = LatLon(47.58, -122.09)
HOME = LatLon(47.5795, -122.0895)


def test_plan_has_qgc_envelope():
    plan = build_patrol_plan(CENTER, radius_m=150.0, altitude_m=30.0, home=HOME)
    assert plan["fileType"] == "Plan"
    assert plan["version"] == 1
    assert plan["groundStation"] == "QGroundControl"
    # firmwareType 3 = ArduPilotMega, vehicleType 2 = quadrotor. A mismatch here
    # makes QGC silently reinterpret altitude semantics.
    assert plan["mission"]["firmwareType"] == 3
    assert plan["mission"]["vehicleType"] == 2


def test_home_position_is_lat_lon_alt_order():
    plan = build_patrol_plan(CENTER, radius_m=150.0, altitude_m=30.0, home=HOME)
    # QGC uses [lat, lon, alt] here - the opposite of GeoJSON's [lon, lat].
    assert plan["mission"]["plannedHomePosition"] == [HOME.lat, HOME.lon, 0]


def test_mission_is_takeoff_then_circle_then_rtl():
    plan = build_patrol_plan(CENTER, radius_m=150.0, altitude_m=30.0, home=HOME, n_points=16)
    items = plan["mission"]["items"]
    assert len(items) == 1 + 16 + 1
    assert items[0]["command"] == 22    # MAV_CMD_NAV_TAKEOFF
    assert all(item["command"] == 16 for item in items[1:-1])  # MAV_CMD_NAV_WAYPOINT
    assert items[-1]["command"] == 20   # MAV_CMD_NAV_RETURN_TO_LAUNCH


def test_do_jump_ids_are_sequential_from_one():
    plan = build_patrol_plan(CENTER, radius_m=150.0, altitude_m=30.0, home=HOME, n_points=8)
    ids = [item["doJumpId"] for item in plan["mission"]["items"]]
    assert ids == list(range(1, len(ids) + 1))


def test_waypoint_params_carry_lat_lon_alt_in_slots_four_five_six():
    plan = build_patrol_plan(CENTER, radius_m=150.0, altitude_m=30.0, home=HOME, n_points=4)
    waypoint = plan["mission"]["items"][1]
    assert waypoint["frame"] == 3          # MAV_FRAME_GLOBAL_RELATIVE_ALT
    assert waypoint["params"][6] == 30.0
    # latitude/longitude must be near the patrol centre, not the origin (0, 0)
    assert waypoint["params"][4] == pytest.approx(CENTER.lat, abs=0.01)
    assert waypoint["params"][5] == pytest.approx(CENTER.lon, abs=0.01)


def test_all_waypoints_sit_on_the_patrol_circle():
    from app.coordination.assignment import haversine_m

    plan = build_patrol_plan(CENTER, radius_m=150.0, altitude_m=30.0, home=HOME, n_points=16)
    for item in plan["mission"]["items"][1:-1]:
        point = LatLon(item["params"][4], item["params"][5])
        assert haversine_m(CENTER, point) == pytest.approx(150.0, abs=1.0)


def test_fence_polygon_is_included_as_inclusion_fence():
    fence = [LatLon(47.60, -122.10), LatLon(47.60, -122.08), LatLon(47.56, -122.08)]
    plan = build_patrol_plan(
        CENTER, radius_m=150.0, altitude_m=30.0, home=HOME, fence_polygon=fence
    )
    polygons = plan["geoFence"]["polygons"]
    assert len(polygons) == 1
    assert polygons[0]["inclusion"] is True
    # geofence vertices are [lat, lon] pairs, same ordering as plannedHomePosition
    assert polygons[0]["polygon"][0] == [47.60, -122.10]


def test_no_fence_polygon_yields_empty_geofence():
    plan = build_patrol_plan(CENTER, radius_m=150.0, altitude_m=30.0, home=HOME)
    assert plan["geoFence"]["polygons"] == []
    assert plan["geoFence"]["circles"] == []


def test_rejects_non_positive_altitude():
    with pytest.raises(ValueError, match="altitude"):
        build_patrol_plan(CENTER, radius_m=150.0, altitude_m=0.0, home=HOME)
