from __future__ import annotations

import pytest

from app.onboarding.shoreline_lookup import ShorelineLookupError, normalize_shoreline


def test_normalize_rejects_empty_polygon():
    with pytest.raises(ShorelineLookupError):
        normalize_shoreline({"type": "Polygon", "coordinates": []})


def test_normalize_promotes_polygon_to_multipolygon():
    value = normalize_shoreline({"type": "Polygon", "coordinates": [[[ -122.1, 47.6], [-122.0, 47.6], [-122.0, 47.7], [-122.1, 47.6]]]})
    assert value["type"] == "MultiPolygon"
