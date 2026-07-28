"""Candidate construction and compare-and-swap activation orchestration."""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.risk_zones.plan_builder import RiskDataUnavailable, build_candidate
from app.risk_zones.plan_repository import RiskPlanRepository
from app.risk_zones.validation import PlanValidationError


class PlanConflict(RuntimeError):
    """The active plan changed after a candidate observed it."""


@dataclass(frozen=True)
class PlanBuildRequest:
    lake_id: str
    snapshot_id: str
    patrol_capacity: int
    safety_reserve: int
    expected_prior_plan_id: str | None


@dataclass(frozen=True)
class PlanBuildResult:
    plan_id: str
    hotspot_count: int
    cell_count: int
    status: str


class RiskPlanService:
    def __init__(self, repository: RiskPlanRepository, snapshot_loader, shoreline_loader) -> None:
        self._repository = repository
        self._snapshot_loader = snapshot_loader
        self._shoreline_loader = shoreline_loader

    def activate_candidate(self, lake_id: str, candidate_id: str, expected_prior_id: str | None) -> None:
        if not self._repository.activate_candidate(lake_id, candidate_id, expected_prior_id):
            raise PlanConflict("active plan changed; candidate was not activated")

    def rebuild(self, request: PlanBuildRequest) -> PlanBuildResult:
        snapshot = self._snapshot_loader(request.snapshot_id)
        if snapshot.lake_id != request.lake_id:
            raise RiskDataUnavailable("snapshot_lake_mismatch")
        candidate = build_candidate(
            snapshot, self._shoreline_loader(request.lake_id), request.patrol_capacity,
            request.safety_reserve, request.expected_prior_plan_id,
        )
        candidate = replace(candidate, snapshot_id=request.snapshot_id)
        self._repository.persist_candidate(candidate)
        self.activate_candidate(request.lake_id, candidate.plan_id, request.expected_prior_plan_id)
        hotspots = sum(cell.kind == "hotspot" for cell in candidate.cells)
        return PlanBuildResult(candidate.plan_id, hotspots, len(candidate.cells), "active")


__all__ = ["PlanBuildRequest", "PlanBuildResult", "PlanConflict", "PlanValidationError", "RiskDataUnavailable", "RiskPlanService"]
