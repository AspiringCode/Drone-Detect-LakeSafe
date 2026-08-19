from __future__ import annotations

from pathlib import Path

from datetime import datetime, timezone

from app.models import LatLon, RiskPointProvenance, ZonePlanCandidate, ZonePlanCell
from app.risk_zones.plan_repository import SupabaseRiskPlanRepository


def _candidate() -> ZonePlanCandidate:
    cell = ZonePlanCell("cell-0", "fallback", LatLon(47.5, -122.1), LatLon(47.5, -122.1),
                        (LatLon(47.4, -122.2), LatLon(47.4, -122.0), LatLon(47.6, -122.0), LatLon(47.4, -122.2)),
                        25, 0, True)
    return ZonePlanCandidate("plan-1", "lake-1", "station-1", "snapshot-1", None, True, (cell,))


class _Result:
    def __init__(self, data): self.data = data


class _Call:
    def __init__(self, client, name, payload): self.client, self.name, self.payload = client, name, payload
    def execute(self): self.client.calls.append((self.name, self.payload)); return _Result(self.client.result)


class _Client:
    def __init__(self, result="plan-1"): self.calls, self.result = [], result
    def rpc(self, name, payload): return _Call(self, name, payload)


class _PlanQuery:
    def __init__(self, client, selection):
        self.client, self.selection = client, selection
    def eq(self, *_args): return self
    def maybe_single(self): return self
    def execute(self):
        self.client.selection = self.selection
        return _Result(self.client.row)


class _PlanClient:
    def __init__(self, row): self.row, self.selection = row, None
    def table(self, name):
        assert name == "zone_plans"
        return self
    def select(self, selection): return _PlanQuery(self, selection)


def test_candidate_and_cells_are_persisted_by_one_station_bound_rpc() -> None:
    client = _Client()
    SupabaseRiskPlanRepository(client).persist_candidate(_candidate())

    name, payload = client.calls[0]
    assert name == "persist_validated_zone_plan"
    assert payload["p_station_id"] == "station-1"
    assert payload["p_cells"][0]["kind"] == "fallback"
    assert len(client.calls) == 1


def test_persisted_proxy_priority_cell_retains_exact_source_provenance() -> None:
    provenance = RiskPointProvenance(
        "king_county_swim_beach_proxy", "0615SB:2026-07-20T17:00:00+00:00", "0615SB",
        datetime(2026, 7, 20, 17, tzinfo=timezone.utc),
    )
    cell = ZonePlanCell(
        "cell-0", "hotspot", LatLon(47.5, -122.1), LatLon(47.5, -122.1),
        (LatLon(47.4, -122.2), LatLon(47.4, -122.0), LatLon(47.6, -122.0), LatLon(47.4, -122.2)),
        25, 1, True, (provenance,),
    )
    candidate = ZonePlanCandidate("plan-1", "lake-1", "station-1", "snapshot-1", None, False, (cell,))
    client = _Client()

    SupabaseRiskPlanRepository(client).persist_candidate(candidate)

    assert client.calls[0][1]["p_cells"][0]["metadata"]["provenance"] == [{
        "connector_key": "king_county_swim_beach_proxy",
        "source_row_id": "0615SB:2026-07-20T17:00:00+00:00",
        "locator": "0615SB",
        "observed_at": "2026-07-20T17:00:00Z",
    }]


def test_persisted_cell_boundary_wkt_retains_interior_rings() -> None:
    outer = (
        LatLon(47.4, -122.2), LatLon(47.4, -122.0),
        LatLon(47.6, -122.0), LatLon(47.4, -122.2),
    )
    hole = (
        LatLon(47.45, -122.15), LatLon(47.46, -122.14),
        LatLon(47.45, -122.13), LatLon(47.45, -122.15),
    )
    cell = ZonePlanCell(
        "cell-0", "hotspot", LatLon(47.5, -122.1), LatLon(47.5, -122.1),
        outer, 25, 1, True, (), (hole,),
    )
    candidate = ZonePlanCandidate(
        "plan-1", "lake-1", "station-1", "snapshot-1", None, False, (cell,),
    )
    client = _Client()

    SupabaseRiskPlanRepository(client).persist_candidate(candidate)

    assert client.calls[0][1]["p_cells"][0]["boundary_wkt"] == (
        "POLYGON((-122.2 47.4,-122.0 47.4,-122.0 47.6,-122.2 47.4),"
        "(-122.15 47.45,-122.14 47.46,-122.13 47.45,-122.15 47.45))"
    )


def test_activation_maps_database_guard_failure_to_false() -> None:
    client = _Client(False)

    assert SupabaseRiskPlanRepository(client).activate_candidate("lake-1", "plan-1", None) is False


def test_database_rpc_serializes_version_and_rejects_incomplete_activation() -> None:
    sql = (Path(__file__).parents[3] / "supabase" / "migrations" / "0012_atomic_zone_plan_persistence.sql").read_text().lower()

    assert "create or replace function public.persist_validated_zone_plan" in sql
    assert "for update" in sql
    assert "jsonb_array_length(p_cells) = 0" in sql
    assert "candidate cell set is incomplete" in sql
    assert "'cell_count'" in sql
    assert "zone_plan_cells where zone_plan_id = p_candidate_id" in sql
    assert "public.st_setsrid(public.st_geomfromtext" in sql
    assert "where snapshot_id = p_snapshot_id and lake_id = p_lake_id" in sql


def test_worker_migration_reclaims_stale_claims_and_applies_failure_backoff() -> None:
    sql = (Path(__file__).parents[3] / "supabase" / "migrations" / "0014_risk_refresh_worker_hardening.sql").read_text().lower()

    assert "for update skip locked" in sql
    assert "claimed_at < now() - interval '10 minutes'" in sql
    assert "next_attempt_at" in sql
    assert "now() + interval '15 minutes'" in sql


def test_claim_ownership_migration_requires_matching_opaque_token_for_completion() -> None:
    sql = (Path(__file__).parents[3] / "supabase" / "migrations" / "0015_risk_refresh_claim_tokens.sql").read_text().lower()

    assert "claim_token uuid" in sql
    assert "p_claim_token uuid" in sql
    assert "claim_token = p_claim_token" in sql
    assert "returning job.lake_id, job.claim_token" in sql


def test_active_plan_exposes_only_safe_attribution_freshness_and_cell_semantics() -> None:
    client = _PlanClient({
        "zone_plan_id": "plan-1",
        "snapshot_id": "snapshot-1",
        "algorithm_version": "risk-zone-v1",
        "validation_payload": {"activity_data_unavailable": False},
        "risk_snapshots": {
            "source_fresh_through": "2026-08-18T00:00:00Z",
            "source_metadata": {"sources": [
                {"attribution": "King County Open Data — Freshwater Swim Beach Data and Water Quality Monitoring Sites", "raw": "omit"},
                {"attribution": "County shoreline"},
                {"attribution": "County shoreline"},
            ]},
            "canonical_payload": {"raw": "must not escape"},
        },
        "zone_plan_cells": [
            {"kind": "hotspot", "risk_score": 1.0, "seed": {"lat": 47.6, "lon": -122.1}, "metadata": {"is_proxy": True, "radius_m": 25, "provenance": [{"source_row_id": "raw-row"}]}},
            {"kind": "hotspot", "risk_score": 0.8, "seed": {"lat": 47.61, "lon": -122.11}, "metadata": {"is_proxy": False, "source_payload": {"raw": True}}},
            {"kind": "coverage", "risk_score": 0.0, "seed": {"lat": 47.62, "lon": -122.12}, "metadata": {"is_proxy": True}},
        ],
    })

    plan = SupabaseRiskPlanRepository(client).active_plan("lake-1")

    assert "source_metadata" in client.selection
    assert "canonical_payload" not in client.selection
    assert plan["source_fresh_through"] == "2026-08-18T00:00:00Z"
    assert plan["source_attribution"] == [
        "County shoreline",
        "King County Open Data — Freshwater Swim Beach Data and Water Quality Monitoring Sites",
    ]
    assert [cell["kind"] for cell in plan["cells"]] == ["hotspot", "hotspot", "coverage"]
    assert [cell["metadata"] for cell in plan["cells"]] == [
        {"is_proxy": True}, {"is_proxy": False}, {"is_proxy": True},
    ]
    assert "canonical_payload" not in plan
    assert "source_metadata" not in plan
