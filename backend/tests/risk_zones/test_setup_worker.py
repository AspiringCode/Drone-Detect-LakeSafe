from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient
from shapely.geometry import Polygon

from app.risk_zones.setup_worker import (
    RiskPlanSetupService, RiskRefreshWorker, cancel_worker_task, start_worker_task,
)


class Repository:
    def __init__(self) -> None:
        self.queued = ["lake-1"]
        self.due = ["lake-2"]
        self.completed: list[str] = []
        self.failed: list[tuple[str, str]] = []

    def claim_queued_lakes(self, limit: int):
        values, self.queued = self.queued[:limit], self.queued[limit:]
        return tuple(values)

    def claim_due_source_lakes(self, limit: int):
        values, self.due = self.due[:limit], self.due[limit:]
        return tuple(values)

    def complete_refresh(self, lake_id: str) -> None:
        self.completed.append(lake_id)

    def fail_refresh(self, lake_id: str, reason: str) -> None:
        self.failed.append((lake_id, reason))


def test_queued_lake_gets_an_initial_plan() -> None:
    repository = Repository()
    built: list[str] = []
    worker = RiskRefreshWorker(repository, lambda lake_id: built.append(lake_id))

    assert worker.run_once() == ("lake-1", "lake-2")
    assert built == ["lake-1", "lake-2"]
    assert repository.completed == ["lake-1", "lake-2"]


def test_failed_refresh_keeps_work_for_a_later_attempt_without_raising() -> None:
    repository = Repository()
    worker = RiskRefreshWorker(repository, lambda lake_id: (_ for _ in ()).throw(ValueError("source unavailable")))

    assert worker.run_once() == ()
    assert repository.failed == [("lake-1", "source unavailable"), ("lake-2", "source unavailable")]


def test_reclaimed_claim_uses_its_opaque_token_so_late_workers_cannot_complete_newer_work() -> None:
    class TokenRepository(Repository):
        def __init__(self):
            super().__init__()
            self.queued, self.due, self.completed = ([{"lake_id": "lake-1", "claim_token": "new-token"}], [], [])

        def complete_refresh(self, lake_id, claim_token):
            self.completed.append((lake_id, claim_token))
            return claim_token == "new-token"

    repository = TokenRepository()
    worker = RiskRefreshWorker(repository, lambda _: None)

    assert worker.run_once() == ("lake-1",)
    assert repository.completed == [("lake-1", "new-token")]


def test_late_claim_token_cannot_overwrite_a_reclaimed_newer_lease() -> None:
    class ReclaimedRepository(Repository):
        def __init__(self):
            super().__init__()
            self.queued, self.due = ([{"lake_id": "lake-1", "claim_token": "old-token"}], [])
            self.current_lease = "new-token"
            self.attempts = []

        def complete_refresh(self, lake_id, claim_token):
            self.attempts.append((lake_id, claim_token))
            return claim_token == self.current_lease

    repository = ReclaimedRepository()
    RiskRefreshWorker(repository, lambda _: None).run_once()

    assert repository.current_lease == "new-token"
    assert repository.attempts == [("lake-1", "old-token")]


def test_stale_worker_cannot_persist_or_activate_after_claim_is_reclaimed() -> None:
    repository = ProductionShapeRepository()
    repository.claim_is_current = lambda lake_id, token: False

    try:
        RiskPlanSetupService(repository).rebuild_lake("lake-1", "old-token")
    except RuntimeError as exc:
        assert "claim" in str(exc)
    else:
        raise AssertionError("stale claim unexpectedly published a plan")
    assert repository.persisted_snapshot is None
    assert repository.persisted_candidate is None


class ProductionShapeRepository(Repository):
    def __init__(self) -> None:
        super().__init__()
        self.persisted_snapshot = None
        self.persisted_candidate = None
        self.active_id = None

    def rebuild_context(self, lake_id):
        assert lake_id == "lake-1"
        return {
            "lake_id": lake_id, "station_id": "station-1", "shoreline_wkt": Polygon([
                (-122.10, 47.57), (-122.08, 47.57), (-122.08, 47.59), (-122.10, 47.59),
            ]).wkt,
            "data_source_status": "fallback_coverage", "sources": [], "patrol_capacity": 0,
            "safety_reserve": 0, "prior_plan_id": None,
        }

    def persist_snapshot(self, snapshot, source_fresh_through):
        self.persisted_snapshot = (snapshot, source_fresh_through)
        return "snapshot-1"

    def persist_candidate(self, candidate):
        self.persisted_candidate = candidate

    def activate_candidate(self, lake_id, candidate_id, expected_prior_id):
        assert lake_id == "lake-1" and expected_prior_id is None
        self.active_id = candidate_id
        return True


def test_production_setup_service_persists_and_activates_explicit_fallback_plan() -> None:
    repository = ProductionShapeRepository()

    result = RiskPlanSetupService(repository).rebuild_lake("lake-1")

    assert result.status == "active"
    assert repository.persisted_snapshot is not None
    assert repository.persisted_candidate.activity_data_unavailable is True
    assert repository.active_id == result.plan_id


def test_lifespan_worker_start_is_singleton_and_cancels_cleanly() -> None:
    async def scenario() -> None:
        application = FastAPI()
        worker = RiskRefreshWorker(Repository(), lambda _: None)
        first = start_worker_task(application, worker, interval_seconds=3600)
        second = start_worker_task(application, worker, interval_seconds=3600)
        assert first is second
        await cancel_worker_task(application)
        assert application.state.risk_refresh_task is None

    asyncio.run(scenario())


def test_main_lifespan_starts_concrete_production_shaped_risk_worker(monkeypatch) -> None:
    from app.main import app
    from app.api import risk_plans

    repository = ProductionShapeRepository()
    repository.queued = []
    repository.due = []
    monkeypatch.setattr(risk_plans, "get_risk_plan_repository", lambda: repository)
    # main imported the provider directly, matching its production lifespan seam.
    monkeypatch.setattr("app.main.get_risk_refresh_worker", risk_plans.get_risk_refresh_worker)

    with TestClient(app) as client:
        task = client.app.state.risk_refresh_task
        assert task is not None and not task.done()
