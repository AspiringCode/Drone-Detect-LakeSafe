from app.risk_zones.socrata_client import (
    fetch_access_points,
    fetch_depth_contours,
    fetch_incidents,
)


def test_fetch_incidents_uses_fixture_offline():
    rows = fetch_incidents(use_fixture=True)
    assert isinstance(rows, list) and len(rows) > 0
    assert {"lat", "lon"} <= set(rows[0].keys())


def test_fixture_contains_depth_and_access_rows():
    assert len(fetch_depth_contours(use_fixture=True)) > 0
    assert len(fetch_access_points(use_fixture=True)) > 0
