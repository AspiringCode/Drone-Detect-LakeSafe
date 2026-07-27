from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.risk_zones.connectors.king_county import KingCountyIncidentConnector


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
            assert dataset_id == KingCountyIncidentConnector.dataset_id
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

    result = KingCountyIncidentConnector().fetch(
        "POLYGON EMPTY", datetime(2026, 1, 1, tzinfo=timezone.utc), Client()
    )
    assert result.rows[0].source_row_id == "i-1"
    assert result.rows[0].occurred_at == datetime(2026, 7, 1, 12, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="schema"):
        KingCountyIncidentConnector().normalize({"incident_id": "broken"})


def test_connector_never_substitutes_fixture_when_live_fetch_fails() -> None:
    class FailingClient:
        def get(self, *_: object, **__: object) -> list[dict[str, str]]:
            raise OSError("network unavailable")

    with pytest.raises(OSError, match="network unavailable"):
        KingCountyIncidentConnector().fetch(
            "POLYGON EMPTY", datetime(2026, 1, 1, tzinfo=timezone.utc), FailingClient()
        )
