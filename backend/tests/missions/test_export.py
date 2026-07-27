import json

import pytest

from app.missions.export import export_zone_mission, simplified_fence
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
    assert len(fence) <= 60
    assert all(isinstance(point, LatLon) for point in fence)


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
