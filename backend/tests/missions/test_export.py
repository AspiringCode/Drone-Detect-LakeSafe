import json

import pytest

from app.missions.export import MAX_FENCE_VERTICES, export_zone_mission, simplified_fence
from app.models import LatLon

HOME = LatLon(47.5795, -122.0895)


def test_simplified_fence_reduces_vertex_count_substantially():
    from app.risk_zones.shoreline import load_lake_polygon

    full = load_lake_polygon("lake-sammamish")
    full_count = len(full.exterior.coords)
    fence = simplified_fence("lake-sammamish", tolerance=0.0008)
    # ArduPilot's polygon fence has a bounded point budget; the real lake
    # outline is ~213 vertices and must come down before it can be uploaded.
    assert len(fence) < full_count
    assert len(fence) <= MAX_FENCE_VERTICES
    assert all(isinstance(point, LatLon) for point in fence)


def test_simplified_fence_is_an_open_ring_not_a_closed_one():
    # Shapely polygons repeat the first vertex as the last to close the ring;
    # QGC/ArduPilot fences expect an open ring (first != last).
    fence = simplified_fence("lake-sammamish", tolerance=0.0008)
    assert fence[0] != fence[-1]


def test_simplified_fence_raises_when_over_the_vertex_budget():
    with pytest.raises(ValueError, match="vertices"):
        simplified_fence("lake-sammamish", tolerance=0.00001)


def test_simplified_fence_still_contains_the_lake_centre():
    from shapely.geometry import Point, Polygon

    from app.risk_zones.shoreline import load_lake_polygon

    original = load_lake_polygon("lake-sammamish")
    fence = simplified_fence("lake-sammamish", tolerance=0.0008)
    simplified = Polygon([(point.lon, point.lat) for point in fence])
    centre = original.representative_point()
    assert simplified.contains(Point(centre.x, centre.y))


def test_export_writes_a_loadable_plan_file(tmp_path):
    output = tmp_path / "zone0.plan"
    result = export_zone_mission(
        lake_id="lake-sammamish",
        zone_index=0,
        drone_count=5,
        altitude_m=30.0,
        home=HOME,
        output_path=output,
    )
    assert result == output
    assert output.exists()

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["fileType"] == "Plan"
    assert len(payload["mission"]["items"]) >= 3
    assert payload["geoFence"]["polygons"][0]["inclusion"] is True


def test_export_rejects_out_of_range_zone_index(tmp_path):
    with pytest.raises(IndexError, match="zone_index"):
        export_zone_mission(
            lake_id="lake-sammamish",
            zone_index=99,
            drone_count=5,
            altitude_m=30.0,
            home=HOME,
            output_path=tmp_path / "nope.plan",
        )


def test_all_waypoints_are_inside_the_fence_polygon(tmp_path):
    """Cross-module invariant: a mission's waypoints must fall inside its own
    geofence. Neither module's own tests check this on their own."""
    from shapely.geometry import Point, Polygon

    output = tmp_path / "zone0.plan"
    export_zone_mission(
        lake_id="lake-sammamish",
        zone_index=0,
        drone_count=5,
        altitude_m=30.0,
        home=HOME,
        output_path=output,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    # Fence vertices are stored [lat, lon]; shapely wants (lon, lat).
    fence_coords = [(lon, lat) for lat, lon in payload["geoFence"]["polygons"][0]["polygon"]]
    fence = Polygon(fence_coords).buffer(1e-9)

    waypoints = [
        item
        for item in payload["mission"]["items"]
        if item["command"] == 16  # CMD_NAV_WAYPOINT
    ]
    assert waypoints, "expected at least one waypoint in the exported mission"
    for item in waypoints:
        lat, lon = item["params"][4], item["params"][5]
        assert fence.contains(Point(lon, lat))


def test_export_writes_mission_planner_waypoints_by_suffix(tmp_path):
    output = export_zone_mission("lake-sammamish", 0, 5, 30.0, HOME, tmp_path / "zone0.waypoints")
    assert output.read_text(encoding="utf-8").startswith("QGC WPL 110\n0\t1\t0\t16\t")
