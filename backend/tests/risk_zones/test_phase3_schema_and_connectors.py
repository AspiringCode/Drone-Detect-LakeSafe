from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.risk_zones.connectors.king_county import (
    KingCountyIncidentConnector,
    ReviewedConnectorUnavailable,
)


def test_schema_defines_versioned_plan_records() -> None:
    sql = (
        Path(__file__).resolve().parents[3]
        / "supabase"
        / "migrations"
        / "0011_risk_snapshots_zone_plans.sql"
    ).read_text(encoding="utf-8").lower()
    for name in (
        "socrata_connectors",
        "lake_data_sources",
        "risk_snapshots",
        "zone_plans",
        "zone_plan_cells",
    ):
        assert f"create table public.{name}" in sql
    assert "create function public.activate_zone_plan" in sql


def test_reviewed_connector_normalizes_and_rejects_drift() -> None:
    class Client:
        def get(self, dataset_id: str, **query: object) -> list[dict[str, str]]:
            assert dataset_id == "reviewed-test-dataset"
            assert "within_polygon" in str(query["where"])
            assert "occurred_at" in str(query["where"])
            assert query["order"] == "occurred_at asc, incident_id asc"
            return [
                {
                    "incident_id": "i-1",
                    "latitude": "47.58",
                    "longitude": "-122.09",
                    "occurred_at": "2026-07-01T12:00:00Z",
                    "severity": "2",
                }
            ]

    connector = KingCountyIncidentConnector("reviewed-test-dataset")
    result = connector.fetch(
        "POLYGON EMPTY", datetime(2026, 1, 1, tzinfo=timezone.utc), Client()
    )
    assert result.rows[0].source_row_id == "i-1"
    assert result.rows[0].occurred_at == datetime(2026, 7, 1, 12, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="schema"):
        connector.normalize({"incident_id": "broken"})


def test_unconfigured_king_county_connector_is_not_seedable() -> None:
    class Client:
        def get(self, *_: object, **__: object) -> list[dict[str, str]]:
            raise AssertionError("an unavailable connector must not query Socrata")

    with pytest.raises(ReviewedConnectorUnavailable, match="reviewed point-capable"):
        KingCountyIncidentConnector().fetch(
            "POLYGON EMPTY", datetime(2026, 1, 1, tzinfo=timezone.utc), Client()
        )


def test_connector_rejects_timestamp_without_explicit_offset() -> None:
    connector = KingCountyIncidentConnector("reviewed-test-dataset")
    with pytest.raises(ValueError, match="timezone"):
        connector.normalize(
            {
                "incident_id": "i-1",
                "latitude": "47.58",
                "longitude": "-122.09",
                "occurred_at": "2026-07-01T12:00:00",
                "severity": "2",
            }
        )


def test_connector_never_substitutes_fixture_when_live_fetch_fails() -> None:
    class FailingClient:
        def get(self, *_: object, **__: object) -> list[dict[str, str]]:
            raise OSError("network unavailable")

    with pytest.raises(OSError, match="network unavailable"):
        KingCountyIncidentConnector("reviewed-test-dataset").fetch(
            "POLYGON EMPTY", datetime(2026, 1, 1, tzinfo=timezone.utc), FailingClient()
        )
