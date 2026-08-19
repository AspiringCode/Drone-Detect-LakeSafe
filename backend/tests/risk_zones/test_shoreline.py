import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from shapely.geometry import Point, Polygon

from app.risk_zones import shoreline
from app.risk_zones.shoreline import ShorelineNotFoundError, load_lake_polygon


@pytest.fixture
def fixture_directory():
    with TemporaryDirectory(dir=Path(__file__).parent) as directory:
        yield Path(directory)


def test_load_lake_sammamish_polygon_contains_lake_point_not_land_point():
    polygon = load_lake_polygon("lake-sammamish")

    assert isinstance(polygon, Polygon)
    assert polygon.is_valid
    assert polygon.contains(Point(-122.090, 47.581))
    assert not polygon.contains(Point(-122.060, 47.581))


def test_load_lake_polygon_raises_for_unknown_lake():
    with pytest.raises(ShorelineNotFoundError):
        load_lake_polygon("lake-unknown")


@pytest.mark.parametrize("lake_id", ["lake-sammamish", "lake-pine", "lake-beaver"])
def test_load_reviewed_lake_polygon(lake_id):
    polygon = load_lake_polygon(lake_id)

    assert isinstance(polygon, Polygon)
    assert polygon.is_valid
    assert not polygon.is_empty


def _write_catalog_and_fixture(tmp_path, geometry, centroid=(1.0, 1.0)):
    (tmp_path / "reviewed_lakes.json").write_text(
        json.dumps({"lakes": [{
            "lake_id": "lake-multi",
            "centroid": {"longitude": centroid[0], "latitude": centroid[1]},
        }]}),
        encoding="utf-8",
    )
    (tmp_path / "lake_multi_shoreline.geojson").write_text(
        json.dumps({
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {"lake_id": "lake-multi"},
                "geometry": geometry,
            }],
        }),
        encoding="utf-8",
    )


def test_load_multipolygon_selects_only_component_containing_catalog_centroid(
    fixture_directory, monkeypatch
):
    _write_catalog_and_fixture(fixture_directory, {
        "type": "MultiPolygon",
        "coordinates": [
            [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
            [[[10, 10], [12, 10], [12, 12], [10, 12], [10, 10]]],
        ],
    })
    monkeypatch.setattr(shoreline, "FIXTURE_DIRECTORY", fixture_directory)

    polygon = load_lake_polygon("lake-multi")

    assert polygon.equals(Polygon([(0, 0), (2, 0), (2, 2), (0, 2)]))


@pytest.mark.parametrize("centroid", [(5.0, 5.0), (1.0, 1.0)])
def test_load_multipolygon_rejects_zero_or_multiple_centroid_matches(
    fixture_directory, monkeypatch, centroid
):
    components = (
        [
            [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
            [[[10, 10], [12, 10], [12, 12], [10, 12], [10, 10]]],
        ]
        if centroid == (5.0, 5.0)
        else [
            [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            [[[1, 1], [2, 1], [2, 2], [1, 2], [1, 1]]],
        ]
    )
    _write_catalog_and_fixture(
        fixture_directory, {"type": "MultiPolygon", "coordinates": components}, centroid
    )
    monkeypatch.setattr(shoreline, "FIXTURE_DIRECTORY", fixture_directory)

    with pytest.raises(ShorelineNotFoundError, match="exactly one"):
        load_lake_polygon("lake-multi")


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Polygon", "coordinates": []},
        {"type": "Polygon", "coordinates": [[[0, 0], [2, 2], [0, 2], [2, 0], [0, 0]]]},
        {"type": "Point", "coordinates": [1, 1]},
    ],
)
def test_load_lake_polygon_rejects_empty_invalid_or_non_polygon_geometry(
    fixture_directory, monkeypatch, geometry
):
    _write_catalog_and_fixture(fixture_directory, geometry)
    monkeypatch.setattr(shoreline, "FIXTURE_DIRECTORY", fixture_directory)

    with pytest.raises(ShorelineNotFoundError, match="valid non-empty"):
        load_lake_polygon("lake-multi")
