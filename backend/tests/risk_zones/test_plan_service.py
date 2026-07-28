from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest
from shapely.geometry import Polygon

from app.models import LatLon
from app.risk_zones.connectors.base import NormalizedRiskPoint
from app.risk_zones.plan_builder import build_candidate
from app.risk_zones.plan_repository import InMemoryRiskPlanRepository
from app.risk_zones.plan_service import PlanBuildRequest, PlanConflict, RiskPlanService
from app.risk_zones.snapshots import RiskSnapshotInput


SHORELINE = Polygon([
    (-122.10, 47.57), (-122.08, 47.57), (-122.08, 47.59), (-122.10, 47.59),
])
NOW = datetime(2026, 7, 27, tzinfo=timezone.utc)


def _snapshot(points=()) -> RiskSnapshotInput:
    return RiskSnapshotInput(
        lake_id="lake-1", station_id="station-1", status="ready", failure_reason=None,
        boundary=SHORELINE.wkt, since=NOW, captured_at=NOW, sources=(), connector_versions=(),
        points=tuple(points), canonical_json="{}", sha256="snapshot-1",
    )


def test_no_hotspots_creates_one_labeled_fallback() -> None:
    plan = build_candidate(_snapshot(), SHORELINE, patrol_capacity=0, reserve=0, prior_plan_id=None)

    assert [cell.kind for cell in plan.cells] == ["fallback"]
    assert plan.activity_data_unavailable is True


def test_supported_hotspots_are_preserved_before_coverage_capacity() -> None:
    points = [
        NormalizedRiskPoint("a", 47.575, -122.095, NOW, 2.0, {}),
        NormalizedRiskPoint("b", 47.5751, -122.0951, NOW, 2.0, {}),
        NormalizedRiskPoint("c", 47.585, -122.085, NOW, 2.0, {}),
        NormalizedRiskPoint("d", 47.5851, -122.0851, NOW, 2.0, {}),
    ]
    plan = build_candidate(_snapshot(points), SHORELINE, patrol_capacity=1, reserve=1, prior_plan_id=None)

    assert [cell.kind for cell in plan.cells] == ["hotspot", "hotspot"]


def test_stale_candidate_preserves_active_plan() -> None:
    repository = InMemoryRiskPlanRepository(active_id="plan-newer")
    service = RiskPlanService(repository, lambda _: _snapshot(), lambda _: SHORELINE)

    with pytest.raises(PlanConflict):
        service.activate_candidate("lake-1", "candidate", "plan-old")

    assert repository.active_id == "plan-newer"


def test_rebuild_persists_then_activates_valid_candidate() -> None:
    repository = InMemoryRiskPlanRepository()
    service = RiskPlanService(repository, lambda _: _snapshot(), lambda _: SHORELINE)

    result = service.rebuild(PlanBuildRequest("lake-1", "snapshot-1", 1, 0, None))

    assert result.status == "active"
    assert repository.active_id == result.plan_id
    assert len(repository.cells[result.plan_id]) == 1
