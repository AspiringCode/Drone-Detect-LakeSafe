from __future__ import annotations

import pytest

from app.onboarding.shoreline_lookup import ShorelineLookupError, normalize_shoreline
from app.onboarding import shoreline_lookup
import httpx


POLYGON = {"type": "Polygon", "coordinates": [[[-122.1,47.6],[-122.0,47.6],[-122.0,47.7],[-122.1,47.7],[-122.1,47.6]]]}


def source(monkeypatch, features=None, failure=None):
    def get(url, **kwargs):
        assert url == shoreline_lookup.WATERBODY_QUERY_URL
        assert kwargs["params"]["outSR"] == 4326
        assert kwargs["params"]["geometry"] == "-122.05,47.65"
        if failure:
            raise failure
        return httpx.Response(200, request=httpx.Request("GET", url), json={"type": "FeatureCollection", "features": features})
    monkeypatch.setattr(shoreline_lookup.httpx, "get", get)


def feature(name="Test Lake", geometry=POLYGON):
    return {"type": "Feature", "properties": {"NAME": name, "FEAT_TYPE": "Lake or pond", "WATER": "Water"}, "geometry": geometry}


def resolve():
    return shoreline_lookup.resolve_shoreline("test lake",47.65,-122.05,[-122.1,47.6,-122.0,47.7])


def test_resolves_official_named_polygon_containing_requested_point(monkeypatch):
    source(monkeypatch,[feature()])
    assert resolve() == {"type": "MultiPolygon", "coordinates": [POLYGON["coordinates"]]}


@pytest.mark.parametrize("features", [[], [feature("Other lake")], [feature(),feature()], [feature(geometry={"type":"Polygon","coordinates":[[[-121,46],[-120,46],[-120,47],[-121,46]]]})]])
def test_rejects_absent_mismatched_ambiguous_or_distant_lakes(monkeypatch, features):
    source(monkeypatch,features)
    with pytest.raises(ShorelineLookupError):
        resolve()


def test_publisher_failure_has_no_fixture_fallback(monkeypatch):
    source(monkeypatch,failure=httpx.ReadTimeout("unavailable"))
    with pytest.raises(ShorelineLookupError):
        resolve()


@pytest.mark.parametrize("ring", [
    [[0,0],[1,1],[0,1],[1,0],[0,0]],
    [[0,0],[1,0],[1,1],[0,1]],
])
def test_rejects_self_intersecting_and_unclosed_boundaries(ring):
    with pytest.raises(ShorelineLookupError):
        normalize_shoreline({"type":"Polygon","coordinates":[ring]})


def test_normalize_rejects_empty_polygon():
    with pytest.raises(ShorelineLookupError):
        normalize_shoreline({"type": "Polygon", "coordinates": []})


def test_normalize_promotes_polygon_to_multipolygon():
    value = normalize_shoreline({"type": "Polygon", "coordinates": [[[ -122.1, 47.6], [-122.0, 47.6], [-122.0, 47.7], [-122.1, 47.6]]]})
    assert value["type"] == "MultiPolygon"


def test_esri_rings_preserve_islands_and_disconnected_water():
    from shapely.geometry import Point, shape
    shell = [[0,0],[0,10],[10,10],[10,0],[0,0]]
    island = [[2,2],[8,2],[8,8],[2,8],[2,2]]
    inner_lake = [[3,3],[3,4],[4,4],[4,3],[3,3]]
    result = shape(shoreline_lookup.esri_shoreline({"rings": [shell,island,inner_lake]}))
    assert result.is_valid and result.area == 65
    assert not result.covers(Point(5,5))
    assert result.covers(Point(3.5,3.5))


def test_name_search_uses_official_ids_and_keeps_duplicate_names(monkeypatch):
    features = [{"attributes": {"OBJECTID": i, "NAME": "Test Lake", "FEAT_TYPE": "Lake or pond", "WATER": "Water"}, "geometry": POLYGON} for i in (1,2)]
    def get(url, **kwargs):
        assert "LOWER(NAME) LIKE '%test%'" in kwargs["params"]["where"]
        assert "geometry" not in kwargs["params"]
        return httpx.Response(200,request=httpx.Request("GET",url),json={"features":features})
    monkeypatch.setattr(shoreline_lookup.httpx,"get",get)
    assert [item["candidate_id"] for item in shoreline_lookup.search_lakes("Test")] == [1,2]


def test_name_search_rejects_sql_wildcards():
    with pytest.raises(ShorelineLookupError): shoreline_lookup.search_lakes("%'; DROP")


def test_disconnected_official_water_areas_are_explicit_separate_choices():
    from shapely.geometry import shape
    large = [[0,0],[0,5],[5,5],[5,0],[0,0]]
    small = [[10,0],[10,1],[11,1],[11,0],[10,0]]
    value = {"attributes":{"OBJECTID":1,"NAME":"Lake Washington","FEAT_TYPE":"Lake or pond","WATER":"Water"},"geometry":{"rings":[small,large]}}
    main = shoreline_lookup._candidate(value)
    detached = shoreline_lookup._candidate(value,1)
    assert main["area_label"] == "Main waterbody" and main["component_count"] == 2
    assert detached["area_label"] == "Separate waterbody 2"
    assert len(shape(main["shoreline"]).geoms) == 1 and shape(main["shoreline"]).area == 25
    assert shape(detached["shoreline"]).area == 1
    with pytest.raises(ShorelineLookupError): shoreline_lookup._candidate(value,2)
