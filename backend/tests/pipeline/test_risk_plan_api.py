from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.access.principal import Principal, StationMembership, StationRole, get_principal


class PlanRepository:
    def __init__(self) -> None:
        self.queued: list[str] = []

    def lake_station_id(self, lake_id: str) -> str | None:
        return "station-1" if lake_id == "lake-1" else None

    def active_plan(self, lake_id: str):
        if lake_id != "lake-1":
            return None
        return {
            "plan_id": "plan-1", "snapshot_id": "snapshot-1", "algorithm_version": "risk-zone-v1",
            "source_fresh_through": "2026-07-28T00:00:00Z", "activity_data_unavailable": False,
            "cells": [{"kind": "hotspot", "risk_score": 2.0, "seed": {"lat": 47.6, "lon": -122.1}}],
        }

    def queue_lake(self, lake_id: str, reason: str = "manual") -> None:
        self.queued.append(f"{lake_id}:{reason}")


def _client(role: StationRole) -> tuple[TestClient, PlanRepository]:
    from app.api import risk_plans
    repository = PlanRepository()
    app = FastAPI()
    app.include_router(risk_plans.router)
    principal = Principal("user-1", "officer@example.gov", "aal2", "officer", "verified", (
        StationMembership("station-1", "Station", "active", frozenset({role})),
    ))
    app.dependency_overrides[get_principal] = lambda: principal
    risk_plans.get_risk_plan_repository = lambda: repository
    return TestClient(app), repository


def test_viewer_reads_stored_plan_versions_and_freshness_without_rebuild() -> None:
    client, repository = _client(StationRole.VIEWER)

    response = client.get("/api/stations/station-1/lakes/lake-1/zone-plan")

    assert response.status_code == 200
    assert {"plan_id", "snapshot_id", "algorithm_version", "source_fresh_through", "cells"} <= response.json().keys()
    assert repository.queued == []


def test_viewer_cannot_request_a_risk_refresh() -> None:
    client, repository = _client(StationRole.VIEWER)

    response = client.post("/api/stations/station-1/lakes/lake-1/risk-refresh")

    assert response.status_code == 403
    assert repository.queued == []


def test_admin_queues_owned_lake_for_refresh() -> None:
    client, repository = _client(StationRole.STATION_ADMIN)

    response = client.post("/api/stations/station-1/lakes/lake-1/risk-refresh")

    assert response.status_code == 202
    assert repository.queued == ["lake-1:manual"]


def test_cross_station_lake_is_not_disclosed() -> None:
    client, _ = _client(StationRole.VIEWER)

    response = client.get("/api/stations/station-2/lakes/lake-1/zone-plan")

    assert response.status_code == 404


def test_main_application_registers_risk_plan_routes() -> None:
    from fastapi.testclient import TestClient
    from app.main import app

    # The FastAPI version used by the project wraps included routers, so route
    # dispatch is the reliable registration assertion.
    assert TestClient(app).get("/api/stations/station-1/lakes/lake-1/zone-plan").status_code == 401
