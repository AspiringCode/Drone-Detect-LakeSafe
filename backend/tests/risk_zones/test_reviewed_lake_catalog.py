import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
CATALOG_PATH = FIXTURES / "reviewed_lakes.json"
EXPECTED_LOCATORS = {
    "lake-sammamish": ["0615SB", "SAMMLANDINGSB"],
    "lake-pine": ["E708SB"],
    "lake-beaver": ["A709SB"],
}
EXPECTED_MONITORING_COORDINATES = {
    "0615SB": (47.55684, -122.07032),
    "SAMMLANDINGSB": (47.64865, -122.08846),
    "E708SB": (47.58737, -122.03977),
    "A709SB": (47.58738, -122.00242),
}
EXPECTED_FEATURE_IDS = {
    "lake-sammamish": 301,
    "lake-pine": 312,
    "lake-beaver": 311,
}


def _catalog() -> list[dict[str, object]]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["lakes"]


def _fixture(lake_id: str) -> dict[str, object]:
    filename = lake_id.replace("lake-", "lake_") + "_shoreline.geojson"
    return json.loads((FIXTURES / filename).read_text(encoding="utf-8"))


def test_catalog_has_exactly_the_three_reviewed_lakes_and_locator_mappings() -> None:
    lakes = _catalog()

    assert [lake["lake_id"] for lake in lakes] == [
        "lake-sammamish",
        "lake-pine",
        "lake-beaver",
    ]
    assert len({lake["lake_id"] for lake in lakes}) == 3
    assert {lake["lake_id"]: lake["locators"] for lake in lakes} == EXPECTED_LOCATORS


@pytest.mark.parametrize("lake_id", EXPECTED_LOCATORS)
def test_catalog_geometry_and_provenance_are_reviewed(lake_id: str) -> None:
    lake = next(item for item in _catalog() if item["lake_id"] == lake_id)
    payload = _fixture(lake_id)

    assert payload["type"] == "FeatureCollection"
    assert len(payload["features"]) == 1
    feature = payload["features"][0]
    geometry = shape(feature["geometry"])
    assert geometry.geom_type in {"Polygon", "MultiPolygon"}
    assert not geometry.is_empty
    assert geometry.is_valid
    assert geometry.area > 0
    assert all(-180 <= x <= 180 and -90 <= y <= 90 for x, y in geometry.exterior.coords) if geometry.geom_type == "Polygon" else all(
        -180 <= x <= 180 and -90 <= y <= 90
        for polygon in geometry.geoms
        for x, y in polygon.exterior.coords
    )

    assert lake["display_name"]
    assert lake["king_county_feature_id"] == EXPECTED_FEATURE_IDS[lake_id]
    assert lake["geometry_attribution"] == "King County GIS Open Data"
    assert feature["properties"]["lake_id"] == lake_id
    assert feature["properties"]["FEATURE_ID"] == lake["king_county_feature_id"]
    assert feature["properties"]["source"] == "King County GIS Open Data"

    query_url = urlparse(lake["geometry_query_url"])
    assert query_url.scheme == "https"
    assert query_url.netloc == "services.arcgis.com"
    assert query_url.path.endswith("/WTRBDY_AREA_485/FeatureServer/0/query")
    query = parse_qs(query_url.query)
    assert query["f"] == ["geojson"]
    assert query["outSR"] == ["4326"]
    assert query["returnGeometry"] == ["true"]
    assert query["outFields"] == ["NAME,FEATURE_ID"]

    assert lake["socrata_dataset_urls"] == {
        "observations": "https://data.kingcounty.gov/resource/mbzm-4r9y.json",
        "monitoring_sites": "https://data.kingcounty.gov/resource/e9bt-i75a.json",
    }


@pytest.mark.parametrize("lake_id", EXPECTED_LOCATORS)
def test_catalog_points_are_consistent_with_official_geometry(lake_id: str) -> None:
    lake = next(item for item in _catalog() if item["lake_id"] == lake_id)
    geometry = shape(_fixture(lake_id)["features"][0]["geometry"])
    to_metres = Transformer.from_crs(4326, 32610, always_xy=True).transform
    metric_geometry = transform(to_metres, geometry)

    centroid = Point(lake["centroid"]["longitude"], lake["centroid"]["latitude"])
    assert geometry.contains(centroid)

    shore_station = Point(
        lake["shore_station"]["longitude"], lake["shore_station"]["latitude"]
    )
    assert not geometry.covers(shore_station)
    assert metric_geometry.distance(transform(to_metres, shore_station)) <= 500
    assert lake["shore_station"]["derivation"]

    monitoring = lake["official_monitoring_coordinates"]
    assert [point["locator"] for point in monitoring] == EXPECTED_LOCATORS[lake_id]
    for point in monitoring:
        assert (point["latitude"], point["longitude"]) == EXPECTED_MONITORING_COORDINATES[
            point["locator"]
        ]
        official_point = Point(point["longitude"], point["latitude"])
        assert metric_geometry.distance(transform(to_metres, official_point)) <= 100
