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
