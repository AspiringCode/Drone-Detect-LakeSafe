"""Insert-only persistence boundary for risk-zone candidates."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import timezone
from typing import Protocol

from app.models import ZonePlanCandidate
from app.risk_zones.snapshots import RiskSnapshotInput


def _provenance_metadata(provenance) -> dict[str, object]:
    payload = {
        "connector_key": provenance.connector_key,
        "source_row_id": provenance.source_row_id,
        "locator": provenance.locator,
    }
    if provenance.observed_at is not None:
        payload["observed_at"] = provenance.observed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if provenance.reviewed_at is not None:
        payload["reviewed_at"] = provenance.reviewed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if provenance.temporal_basis != "publisher_observation":
        payload["temporal_basis"] = provenance.temporal_basis
    for field in (
        "source_latitude", "source_longitude", "derived_seed_latitude",
        "derived_seed_longitude", "adjustment_distance_m", "adjustment_reason",
    ):
        value = getattr(provenance, field, None)
        if value is not None:
            payload[field] = value
    return payload


def _cell_boundary_wkt(cell) -> str:
    rings = (cell.polygon, *cell.holes)
    return "POLYGON(" + ",".join(
        "(" + ",".join(f"{point.lon} {point.lat}" for point in ring) + ")"
        for ring in rings
    ) + ")"


class RiskPlanRepository(Protocol):
    def persist_candidate(self, candidate: ZonePlanCandidate) -> None: ...
    def activate_candidate(self, lake_id: str, candidate_id: str, expected_prior_id: str | None) -> bool: ...
    def active_plan_id(self, lake_id: str) -> str | None: ...


class RiskRefreshRepository(Protocol):
    """Durable work queue boundary used by the setup worker."""

    def lake_station_id(self, lake_id: str) -> str | None: ...
    def active_plan(self, lake_id: str) -> dict | None: ...
    def queue_lake(self, lake_id: str, reason: str = "manual") -> None: ...
    def claim_queued_lakes(self, limit: int) -> tuple[dict[str, str], ...]: ...
    def claim_due_source_lakes(self, limit: int) -> tuple[dict[str, str], ...]: ...
    def complete_refresh(self, lake_id: str, claim_token: str) -> bool: ...
    def fail_refresh(self, lake_id: str, claim_token: str, reason: str) -> bool: ...
    def claim_is_current(self, lake_id: str, claim_token: str) -> bool: ...


class InMemoryRiskPlanRepository:
    """Small deterministic repository used by service tests and local demos."""

    def __init__(self, active_id: str | None = None) -> None:
        self.active_id = active_id
        self.candidates: dict[str, ZonePlanCandidate] = {}
        self.cells = defaultdict(tuple)

    def persist_candidate(self, candidate: ZonePlanCandidate, claim_token: str | None = None) -> None:
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

    def persist_candidate(self, candidate: ZonePlanCandidate, claim_token: str | None = None) -> None:
        if not candidate.snapshot_id:
            raise ValueError("validated candidates require a persisted snapshot ID")
        cells = [
            {
                "ordinal": ordinal, "kind": cell.kind,
                "risk_score": cell.risk_score,
                "seed_wkt": f"POINT({cell.seed.lon} {cell.seed.lat})",
                "boundary_wkt": _cell_boundary_wkt(cell),
                "metadata": {
                    "radius_m": cell.radius_m,
                    "is_proxy": cell.is_proxy,
                    "provenance": [_provenance_metadata(provenance) for provenance in cell.provenance],
                },
            }
            for ordinal, cell in enumerate(candidate.cells)
        ]
        function = "persist_validated_zone_plan_claimed" if claim_token else "persist_validated_zone_plan"
        payload = {
            "p_plan_id": candidate.plan_id, "p_lake_id": candidate.lake_id,
            "p_station_id": candidate.station_id, "p_snapshot_id": candidate.snapshot_id,
            "p_prior_plan_id": candidate.prior_plan_id, "p_algorithm_version": "risk-zone-v1",
            "p_validation_payload": {"activity_data_unavailable": candidate.activity_data_unavailable},
            "p_cells": cells,
        }
        if claim_token: payload["p_claim_token"] = claim_token
        result = self._client.rpc(function, payload).execute()
        if result.data not in (candidate.plan_id, [candidate.plan_id], {"zone_plan_id": candidate.plan_id}):
            raise ValueError("candidate plan was not persisted")

    def activate_candidate(self, lake_id: str, candidate_id: str, expected_prior_id: str | None, claim_token: str | None = None) -> bool:
        function = "activate_zone_plan_claimed" if claim_token else "activate_zone_plan"
        payload = {
            "p_lake_id": lake_id, "p_candidate_id": candidate_id,
            "p_expected_prior_id": expected_prior_id,
        }
        if claim_token: payload["p_claim_token"] = claim_token
        result = self._client.rpc(function, payload).execute()
        return result.data is True

    def active_plan_id(self, lake_id: str) -> str | None:
        response = self._client.table("zone_plans").select("zone_plan_id").eq(
            "lake_id", lake_id
        ).eq("status", "active").maybe_single().execute()
        row = response.data if response is not None else None
        return str(row["zone_plan_id"]) if row else None

    def lake_station_id(self, lake_id: str) -> str | None:
        response = self._client.table("lakes").select("station_id").eq("lake_id", lake_id).maybe_single().execute()
        row = response.data if response is not None else None
        return str(row["station_id"]) if row else None

    def active_plan(self, lake_id: str) -> dict | None:
        response = self._client.table("zone_plans").select(
            "zone_plan_id,snapshot_id,algorithm_version,validation_payload,"
            "risk_snapshots(source_fresh_through,source_metadata),"
            "zone_plan_cells(kind,risk_score,seed,metadata)"
        ).eq("lake_id", lake_id).eq("status", "active").maybe_single().execute()
        row = response.data if response is not None else None
        if not row:
            return None
        snapshot = row.get("risk_snapshots") or {}
        if isinstance(snapshot, list):
            snapshot = snapshot[0] if snapshot else {}
        cells = []
        for cell in row.get("zone_plan_cells") or []:
            metadata = cell.get("metadata") or {}
            cells.append({
                "kind": cell["kind"], "risk_score": cell["risk_score"],
                "seed": cell.get("seed"),
                # Plan consumers need proxy semantics, not raw per-row source
                # provenance or canonical publisher payloads.
                "metadata": {"is_proxy": bool(metadata.get("is_proxy"))},
            })
        source_metadata = snapshot.get("source_metadata") or {}
        sources = source_metadata.get("sources") if isinstance(source_metadata, dict) else []
        source_attribution = sorted({
            attribution.strip()
            for source in sources or []
            if isinstance(source, dict)
            and isinstance((attribution := source.get("attribution")), str)
            and attribution.strip()
        })
        return {
            "plan_id": str(row["zone_plan_id"]), "snapshot_id": str(row["snapshot_id"]),
            "algorithm_version": row["algorithm_version"],
            "source_fresh_through": snapshot.get("source_fresh_through"),
            "source_attribution": source_attribution,
            "activity_data_unavailable": bool((row.get("validation_payload") or {}).get("activity_data_unavailable")),
            "cells": cells,
        }

    def queue_lake(self, lake_id: str, reason: str = "manual") -> None:
        self._client.rpc("enqueue_risk_refresh", {"p_lake_id": lake_id, "p_reason": reason}).execute()

    def claim_queued_lakes(self, limit: int) -> tuple[str, ...]:
        data = self._client.rpc("claim_queued_risk_refreshes", {"p_limit": limit}).execute().data or []
        return tuple({"lake_id": str(row["lake_id"]), "claim_token": str(row["claim_token"])} for row in data)

    def claim_due_source_lakes(self, limit: int) -> tuple[str, ...]:
        data = self._client.rpc("claim_due_risk_source_refreshes", {"p_limit": limit}).execute().data or []
        return tuple({"lake_id": str(row["lake_id"]), "claim_token": str(row["claim_token"])} for row in data)

    def complete_refresh(self, lake_id: str, claim_token: str) -> bool:
        return self._client.rpc("complete_risk_refresh", {"p_lake_id": lake_id, "p_claim_token": claim_token}).execute().data is True

    def fail_refresh(self, lake_id: str, claim_token: str, reason: str) -> bool:
        return self._client.rpc("fail_risk_refresh", {"p_lake_id": lake_id, "p_claim_token": claim_token, "p_reason": reason}).execute().data is True

    def claim_is_current(self, lake_id: str, claim_token: str) -> bool:
        return self._client.rpc("risk_refresh_claim_is_current", {"p_lake_id": lake_id, "p_claim_token": claim_token}).execute().data is True

    def rebuild_context(self, lake_id: str) -> dict | None:
        result = self._client.rpc("risk_plan_rebuild_context", {"p_lake_id": lake_id}).execute().data
        if isinstance(result, list):
            result = result[0] if result else None
        return result if isinstance(result, dict) else None

    def persist_snapshot(self, snapshot: RiskSnapshotInput, source_fresh_through, claim_token: str | None = None) -> str:
        function = "persist_risk_snapshot_claimed" if claim_token else "persist_risk_snapshot"
        payload = {
            "p_lake_id": snapshot.lake_id, "p_station_id": snapshot.station_id,
            "p_status": snapshot.status, "p_source_fresh_through": source_fresh_through.isoformat() if source_fresh_through else None,
            "p_source_metadata": {
                "sources": [asdict(source) for source in snapshot.sources],
                "connector_versions": list(snapshot.connector_versions),
            },
            "p_canonical_payload": snapshot.canonical_json,
            "p_payload_sha256": snapshot.sha256, "p_failure_reason": snapshot.failure_reason,
        }
        if claim_token: payload["p_claim_token"] = claim_token
        result = self._client.rpc(function, payload).execute().data
        if isinstance(result, list):
            result = result[0] if result else None
        if not result:
            raise ValueError("risk snapshot was not persisted")
        return str(result)
