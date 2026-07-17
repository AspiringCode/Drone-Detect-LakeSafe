import pytest
from shapely.geometry import Point, Polygon

from app.risk_zones.shoreline import ShorelineNotFoundError, load_lake_polygon


def test_load_lake_sammamish_polygon_contains_lake_point_not_land_point():
    polygon = load_lake_polygon("lake-sammamish")

    assert isinstance(polygon, Polygon)
    assert polygon.is_valid
    assert polygon.contains(Point(-122.090, 47.581))
    assert not polygon.contains(Point(-122.060, 47.581))


def test_load_lake_polygon_raises_for_unknown_lake():
    with pytest.raises(ShorelineNotFoundError):
        load_lake_polygon("lake-unknown")
