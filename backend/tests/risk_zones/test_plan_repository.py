from __future__ import annotations

from pathlib import Path

from app.models import LatLon, ZonePlanCandidate, ZonePlanCell
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


def test_candidate_and_cells_are_persisted_by_one_station_bound_rpc() -> None:
    client = _Client()
    SupabaseRiskPlanRepository(client).persist_candidate(_candidate())

    name, payload = client.calls[0]
    assert name == "persist_validated_zone_plan"
    assert payload["p_station_id"] == "station-1"
    assert payload["p_cells"][0]["kind"] == "fallback"
    assert len(client.calls) == 1


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
