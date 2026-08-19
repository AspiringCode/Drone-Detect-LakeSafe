from datetime import datetime, timezone
from pathlib import Path
import re

import pytest

from app.risk_zones.connectors.king_county import (
    KingCountyIncidentConnector,
    ReviewedConnectorUnavailable,
)
from app.risk_zones.connectors.king_county_swim_beach import (
    KingCountySwimBeachProxyConnector,
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


def test_reviewed_multi_lake_migration_seeds_exact_sources_and_official_geometry() -> None:
    sql = (
        Path(__file__).resolve().parents[3]
        / "supabase"
        / "migrations"
        / "0036_reviewed_multi_lake_sources.sql"
    ).read_text(encoding="utf-8").lower()

    for lake_id in ("lake-sammamish", "lake-pine", "lake-beaver"):
        assert lake_id in sql
    for locator in ("0615sb", "sammlandingsb", "e708sb", "a709sb"):
        assert locator in sql
    assert "king_county_swim_beach_proxy" in sql
    assert "mbzm-4r9y" in sql
    assert "e9bt-i75a" in sql
    assert KingCountySwimBeachProxyConnector.attribution.lower() in sql
    assert "'reviewed'" in sql
    assert "2026-08-18t00:00:00z" in sql
    assert "st_setsrid" in sql and "4326" in sql
    assert "st_multi" in sql

    assert "from public.stations" in sql
    assert "legacy_org_id = 'org-demo'" in sql
    assert "public.organizations as organization" in sql
    assert "org_id = 'org-demo'" in sql
    assert not re.search(
        r"'[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}'",
        sql,
    )


def test_rebuild_context_exposes_source_configuration_and_remains_service_only() -> None:
    sql = (
        Path(__file__).resolve().parents[3]
        / "supabase"
        / "migrations"
        / "0036_reviewed_multi_lake_sources.sql"
    ).read_text(encoding="utf-8").lower()

    function_start = sql.index("create or replace function public.risk_plan_rebuild_context")
    function_sql = sql[function_start:]
    assert "security definer" in function_sql
    assert "set search_path = ''" in function_sql
    for field in (
        "connector_key",
        "domain",
        "dataset_id",
        "schema_version",
        "configuration",
        "source_configuration",
        "patrol_capacity",
        "safety_reserve",
        "prior_plan_id",
    ):
        assert f"'{field}'" in function_sql

    signature = "function public.risk_plan_rebuild_context(text)"
    assert f"revoke all on {signature} from public, anon, authenticated" in function_sql
    assert f"grant execute on {signature} to service_role" in function_sql
    assert not re.search(
        rf"grant\s+execute\s+on\s+{re.escape(signature)}\s+to\s+(public|anon|authenticated)",
        function_sql,
    )


def test_forward_migration_configures_one_drone_risk_plan_reserve() -> None:
    path = (
        Path(__file__).resolve().parents[3]
        / "supabase"
        / "migrations"
        / "0037_risk_plan_safety_reserve.sql"
    )

    assert path.exists(), "applied migration 0036 must be corrected by a forward migration"
    sql = path.read_text(encoding="utf-8").lower()
    function_start = sql.index("create or replace function public.risk_plan_rebuild_context")
    function_sql = sql[function_start:]
    assert "'safety_reserve', 1" in function_sql
    assert "security definer" in function_sql and "set search_path = ''" in function_sql
    assert "revoke all on function public.risk_plan_rebuild_context(text)" in function_sql
    assert "grant execute on function public.risk_plan_rebuild_context(text) to service_role" in function_sql
