"""Insert-only persistence boundary for risk-zone candidates."""

from __future__ import annotations

from collections import defaultdict
from typing import Protocol

from app.models import ZonePlanCandidate


class RiskPlanRepository(Protocol):
    def persist_candidate(self, candidate: ZonePlanCandidate) -> None: ...
    def activate_candidate(self, lake_id: str, candidate_id: str, expected_prior_id: str | None) -> bool: ...
    def active_plan_id(self, lake_id: str) -> str | None: ...


class InMemoryRiskPlanRepository:
    """Small deterministic repository used by service tests and local demos."""

    def __init__(self, active_id: str | None = None) -> None:
        self.active_id = active_id
        self.candidates: dict[str, ZonePlanCandidate] = {}
        self.cells = defaultdict(tuple)

    def persist_candidate(self, candidate: ZonePlanCandidate) -> None:
        if candidate.plan_id in self.candidates:
            raise ValueError("candidate plans are insert-only")
        self.candidates[candidate.plan_id] = candidate
        self.cells[candidate.plan_id] = candidate.cells

    def activate_candidate(self, lake_id: str, candidate_id: str, expected_prior_id: str | None) -> bool:
        if candidate_id not in self.candidates or self.candidates[candidate_id].lake_id != lake_id:
            return False
        if self.active_id != expected_prior_id:
            return False
        self.active_id = candidate_id
        return True

    def active_plan_id(self, lake_id: str) -> str | None:
        del lake_id
        return self.active_id


class SupabaseRiskPlanRepository:
    """Service-role adapter; activation is delegated to the database CAS RPC."""

    def __init__(self, client) -> None:
        self._client = client

    def persist_candidate(self, candidate: ZonePlanCandidate) -> None:
        version_row = self._client.table("zone_plans").select("version").eq(
            "lake_id", candidate.lake_id
        ).order("version", desc=True).limit(1).execute().data or []
        version = int(version_row[0]["version"]) + 1 if version_row else 1
        self._client.table("zone_plans").insert({
            "zone_plan_id": candidate.plan_id, "lake_id": candidate.lake_id,
            "snapshot_id": candidate.snapshot_id, "version": version, "status": "validated",
            "algorithm_version": "risk-zone-v1", "prior_plan_id": candidate.prior_plan_id,
            "validation_payload": {"activity_data_unavailable": candidate.activity_data_unavailable},
        }).execute()
        self._client.table("zone_plan_cells").insert([
            {
                "zone_plan_id": candidate.plan_id, "ordinal": ordinal, "kind": cell.kind,
                "risk_score": cell.risk_score,
                "seed": f"SRID=4326;POINT({cell.seed.lon} {cell.seed.lat})",
                "boundary": "SRID=4326;POLYGON((" + ",".join(
                    f"{point.lon} {point.lat}" for point in cell.polygon
                ) + "))",
                "metadata": {"radius_m": cell.radius_m, "is_proxy": cell.is_proxy},
            }
            for ordinal, cell in enumerate(candidate.cells)
        ]).execute()

    def activate_candidate(self, lake_id: str, candidate_id: str, expected_prior_id: str | None) -> bool:
        result = self._client.rpc("activate_zone_plan", {
            "p_lake_id": lake_id, "p_candidate_id": candidate_id,
            "p_expected_prior_id": expected_prior_id,
        }).execute()
        return result.data is True

    def active_plan_id(self, lake_id: str) -> str | None:
        row = self._client.table("zone_plans").select("zone_plan_id").eq(
            "lake_id", lake_id
        ).eq("status", "active").maybe_single().execute().data
        return str(row["zone_plan_id"]) if row else None
