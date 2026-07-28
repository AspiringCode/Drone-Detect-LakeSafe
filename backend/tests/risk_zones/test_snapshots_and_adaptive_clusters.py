from __future__ import annotations

from datetime import datetime, timezone

from app.risk_zones.adaptive_clusters import select_hotspots
from app.risk_zones.cluster_strategy import WeightedPoint
from app.risk_zones.connectors.base import ConnectorFetch, NormalizedRiskPoint
from app.risk_zones.snapshots import build_snapshot


BBOX = (47.556, -122.104, 47.606, -122.078)
NOW = datetime(2026, 7, 27, tzinfo=timezone.utc)


def _fetch(*, rows: tuple[NormalizedRiskPoint, ...]) -> ConnectorFetch:
    return ConnectorFetch(
        connector_key="king_county_incidents",
        connector_schema_version="1",
        attribution="King County Open Data",
        rows=rows,
    )


def test_no_reviewed_connector_is_quarantined() -> None:
    snapshot = build_snapshot("lake-1", "st-1", (), "POLYGON EMPTY", NOW, NOW)
    assert snapshot.status == "quarantined"
    assert snapshot.failure_reason == "no_reviewed_connector"


def test_snapshot_is_canonical_across_connector_and_row_order() -> None:
    earlier = NormalizedRiskPoint(
        source_row_id="b",
        latitude=47.58,
        longitude=-122.09,
        occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        weight=2.0,
        source_payload={"severity": "2", "incident_id": "b"},
    )
    later = NormalizedRiskPoint(
        source_row_id="a",
        latitude=47.59,
        longitude=-122.08,
        occurred_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        weight=1.0,
        source_payload={"incident_id": "a", "severity": "1"},
    )
    first = build_snapshot("lake-1", "st-1", (_fetch(rows=(later, earlier)),), "POLYGON EMPTY", NOW, NOW)
    second = build_snapshot("lake-1", "st-1", (_fetch(rows=(earlier, later)),), "POLYGON EMPTY", NOW, NOW)
    assert first.status == "ready"
    assert first.sha256 == second.sha256
    assert first.points == second.points
    assert first.connector_versions == (("king_county_incidents", "1"),)


def test_connector_failures_are_quarantined() -> None:
    snapshot = build_snapshot("lake-1", "st-1", (ValueError("schema drift"),), "POLYGON EMPTY", NOW, NOW)
    assert snapshot.status == "quarantined"
    assert snapshot.failure_reason == "connector_schema_failure"


def test_malformed_normalized_row_is_quarantined() -> None:
    malformed = NormalizedRiskPoint(
        source_row_id="bad-time",
        latitude=47.58,
        longitude=-122.09,
        occurred_at=datetime(2026, 7, 1),
        weight=1.0,
        source_payload={},
    )
    snapshot = build_snapshot("lake-1", "st-1", (_fetch(rows=(malformed,)),), "POLYGON EMPTY", NOW, NOW)
    assert snapshot.status == "quarantined"
    assert snapshot.failure_reason == "connector_schema_failure"


def test_adaptive_count_is_deterministic() -> None:
    points = tuple(
        WeightedPoint(47.56 + group * 0.02 + item * 0.0001, -122.09, 1.0, "incidents")
        for group in range(2)
        for item in range(5)
    )
    first = select_hotspots(points, BBOX, max_k=5)
    second = select_hotspots(points, BBOX, max_k=5)
    assert first == second
    assert first.k == 2


def test_under_supported_data_returns_no_hotspots() -> None:
    result = select_hotspots((WeightedPoint(47.58, -122.09, 1.0, "incidents"),), BBOX)
    assert result.k == 0
    assert result.hotspots == ()
    assert result.reason == "insufficient_support"


def test_equal_scores_choose_smaller_k() -> None:
    duplicate = tuple(WeightedPoint(47.58, -122.09, 1.0, "incidents") for _ in range(6))
    result = select_hotspots(duplicate, BBOX, min_k=1, max_k=3)
    assert result.k == 1
