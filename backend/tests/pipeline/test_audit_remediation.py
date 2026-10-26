from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from app import main
from app.models import Alert, LatLon


def test_simulation_review_validates_existence_and_is_idempotent(monkeypatch):
    monkeypatch.setattr(main, "authorize_lake", lambda *args: SimpleNamespace(user_id="operator"))
    monkeypatch.setattr(main, "get_alert_review_repository", lambda: SimpleNamespace(review=lambda *args: None))
    runtime = main.build_lake_runtime("lake-sammamish")
    monkeypatch.setitem(main.lake_runtimes, runtime.lake_id, runtime)
    with pytest.raises(HTTPException) as error:
        main.review_alert(runtime.lake_id, "missing", None)
    assert error.value.status_code == 404
    alert = Alert("test-review", datetime.now(timezone.utc), LatLon(47.6, -122.1), "thermal-cv", "sim-1", None, True, "simulated", None)
    runtime.alerts.save(alert)
    first = main.review_alert(runtime.lake_id, alert.alert_id, None)
    second = main.review_alert(runtime.lake_id, alert.alert_id, None)
    assert first["reviewed"] is True and first["durable"] is False
    assert first['review_decision'] is None  # legacy acknowledgement is not a yes/no decision
    assert second["already_reviewed"] is True
    assert second["reviewed_at"] == first["reviewed_at"]
    assert "escalated" not in first


def test_real_review_requires_durable_success(monkeypatch):
    monkeypatch.setattr(main, "authorize_lake", lambda *args: SimpleNamespace(user_id="operator"))
    runtime = main.build_lake_runtime("lake-sammamish")
    monkeypatch.setitem(main.lake_runtimes, runtime.lake_id, runtime)
    calls = []
    class Repository:
        def review(self, lake_id, alert_id, actor):
            calls.append((lake_id, alert_id, actor))
            return {"alert_id": alert_id, "source": "real", "reviewed": True, "durable": True, "reviewed_at": "2026-10-24T00:00:00Z", "already_reviewed": False}
    monkeypatch.setattr(main, "get_alert_review_repository", lambda: Repository())
    result = main.review_alert(runtime.lake_id, "real-alert-not-in-memory", None)
    assert result["durable"] is True
    assert calls == [(runtime.lake_id, "real-alert-not-in-memory", "operator")]


def test_persisted_ready_lake_creates_runtime_and_uses_stored_plan(monkeypatch):
    from app.lakes.runtime_repository import zones_from_plan
    from shapely.geometry import Polygon, Point
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 0)])
    context = {"lake_id": "new-lake", "name": "New lake", "shoreline": polygon.wkb_hex,
               "plan_id": "plan-1", "cells": [{"zone_plan_cell_id": "cell-1", "seed": Point(.5, .2).wkb_hex,
               "boundary": polygon.wkb_hex, "risk_score": 0, "metadata": {"is_proxy": False}}]}
    class Repository:
        def runtime_context(self, lake_id): return context
    monkeypatch.setattr(main, "get_lake_runtime_repository", lambda: Repository())
    runtime = main.get_runtime("new-lake")
    try:
        assert runtime.name == "New lake"
        assert runtime.zones == zones_from_plan(context)
        assert not runtime.engine.drones
        assert main.get_runtime("new-lake") is runtime
    finally:
        main.lake_runtimes.pop("new-lake", None)


def test_pending_lake_returns_actionable_setup_status(monkeypatch):
    class Repository:
        def runtime_context(self, lake_id):
            return {"lake_id": lake_id, "setup_status": "queued"}
    monkeypatch.setattr(main, "get_lake_runtime_repository", lambda: Repository())
    with pytest.raises(HTTPException) as error:
        main.get_runtime("pending-lake")
    assert error.value.status_code == 409
    assert error.value.detail["setup_status"] == "queued"


def _stored_context(lake_id="persisted-lake"):
    from shapely.geometry import Polygon, Point
    polygon = Polygon([(-122.1, 47.5), (-122.09, 47.5), (-122.09, 47.51), (-122.1, 47.5)])
    return {"lake_id": lake_id, "name": "Persisted lake", "shoreline": polygon.wkb_hex,
            "setup_status": "ready", "plan_id": "stored-plan", "cells": [{
                "zone_plan_cell_id": "stored-cell", "seed": Point(-122.092, 47.502).wkb_hex,
                "boundary": polygon.wkb_hex, "risk_score": 0, "metadata": {"is_proxy": False}}]}


def test_ready_lake_initializes_tick_after_authorized_read(monkeypatch):
    from fastapi.testclient import TestClient
    from app.access.principal import Principal, StationMembership, StationRole
    lake_id = "persisted-lake"
    context = _stored_context(lake_id)
    monkeypatch.setattr(main, "get_lake_runtime_repository", lambda: SimpleNamespace(runtime_context=lambda _: context))
    monkeypatch.setattr(main, "get_current_principal", lambda _: Principal("actor", None, "aal2", "officer", "verified", (
        StationMembership("station-owned", "Owned", "active", frozenset({StationRole.VIEWER})),)))
    monkeypatch.setattr(main, "get_access_repository", lambda: SimpleNamespace(lake_station_id=lambda _: "station-owned"))
    monkeypatch.setattr(main, "get_risk_refresh_worker", lambda: None)
    with TestClient(main.app) as client:
        try:
            response = client.get(f"/api/lakes/{lake_id}/drones", headers={"Authorization": "Bearer test"})
            assert response.status_code == 200
            assert response.json()["drones"] == []
            assert lake_id in main.app.state.tick_tasks
            assert not main.app.state.tick_tasks[lake_id].done()
        finally:
            main.lake_runtimes.pop(lake_id, None)
    assert main.app.state.tick_tasks == {}


def test_cross_station_cannot_initialize_persisted_runtime(monkeypatch):
    from app.access.principal import Principal
    calls = []
    monkeypatch.setattr(main, "get_access_repository", lambda: SimpleNamespace(lake_station_id=lambda _: "another-station"))
    monkeypatch.setattr(main, "get_current_principal", lambda _: Principal("actor", None, "aal2", "officer", "verified", ()))
    monkeypatch.setattr(main, "get_lake_runtime_repository", lambda: calls.append(True))
    with pytest.raises(HTTPException) as error:
        main.authorize_lake("unowned-persisted-lake", None, main.Permission.READ_OPERATIONS)
    assert error.value.status_code == 404
    assert calls == []


def test_invalid_plan_never_creates_runtime(monkeypatch):
    from shapely.geometry import Point
    context = _stored_context("invalid-persisted-lake")
    context["cells"][0]["seed"] = Point(0, 0).wkb_hex
    monkeypatch.setattr(main, "get_lake_runtime_repository", lambda: SimpleNamespace(runtime_context=lambda _: context))
    with pytest.raises(HTTPException) as error:
        main.get_runtime("invalid-persisted-lake")
    assert error.value.status_code == 409
    assert error.value.detail["setup_status"] == "failed"
    assert "invalid-persisted-lake" not in main.lake_runtimes


def test_real_review_failure_cannot_be_reported_as_reviewed(monkeypatch):
    from app.pipeline.alert_review import AlertReviewUnavailable
    monkeypatch.setattr(main, "authorize_lake", lambda *args: SimpleNamespace(user_id="operator"))
    runtime = main.build_lake_runtime("lake-sammamish")
    monkeypatch.setitem(main.lake_runtimes, runtime.lake_id, runtime)
    class Repository:
        def review(self, *args): raise AlertReviewUnavailable()
    monkeypatch.setattr(main, "get_alert_review_repository", lambda: Repository())
    with pytest.raises(HTTPException) as error:
        main.review_alert(runtime.lake_id, "unpersisted", None)
    assert error.value.status_code == 503
    assert "unpersisted" not in runtime.reviewed_alerts


def test_reviewed_state_is_reloaded_from_durable_storage(monkeypatch):
    runtime = main.build_lake_runtime("lake-sammamish")
    runtime.alerts.save(Alert("real-reviewed", datetime.now(timezone.utc), LatLon(47.6, -122.1), "thermal-cv", "real-1", None, True, "real", None))
    monkeypatch.setitem(main.lake_runtimes, runtime.lake_id, runtime)
    monkeypatch.setattr(main, "authorize_lake", lambda *args: None)
    monkeypatch.setattr(main, "get_alert_review_repository", lambda: SimpleNamespace(reviewed_alerts=lambda _: {"real-reviewed": "2026-10-24T00:00:00Z"}))
    assert main.get_alerts(runtime.lake_id, None)[0]["reviewed_at"] == "2026-10-24T00:00:00Z"


@pytest.mark.parametrize("action", ["start", "regenerate"])
def test_replanning_real_zones_requires_safety_permission(monkeypatch, action):
    from app.access.principal import Principal, StationMembership, StationRole
    principal = Principal("admin", None, "aal2", "officer", "verified", (
        StationMembership("station-1", "Station", "active", frozenset({StationRole.STATION_ADMIN})),))
    runtime = main.build_lake_runtime("lake-sammamish")
    monkeypatch.setitem(main.lake_runtimes, runtime.lake_id, runtime)
    monkeypatch.setattr(main, "authorize_lake", lambda *args: principal)
    monkeypatch.setattr(main, "get_access_repository", lambda: SimpleNamespace(lake_station_id=lambda _: "station-1"))
    monkeypatch.setattr(main, "_real_drone_ids", lambda _: ["real-1"])
    before = list(runtime.zones)
    with pytest.raises(HTTPException) as error:
        if action == "start":
            main.start_simulation(runtime.lake_id, main.StartSimulationRequest(real_drones="replan"), None)
        else:
            main.regenerate_zones(runtime.lake_id, None)
    assert error.value.status_code == 403
    assert runtime.zones == before
    assert not runtime.engine.drones


def test_review_migration_is_atomic_idempotent_and_service_only():
    from pathlib import Path
    sql = (Path(__file__).parents[3] / "supabase/migrations/0045_alert_operator_review.sql").read_text().lower()
    assert "for update" in sql
    assert "if not was_reviewed then" in sql
    assert "source = 'real'" in sql
    assert "private.record_workflow_audit" in sql
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql
    assert "'resolved'" not in sql


def test_real_replan_requires_recent_mfa_even_for_safety_supervisor(monkeypatch):
    from app.access.principal import Principal, StationMembership, StationRole
    principal = Principal("supervisor", None, "aal2", "officer", "verified", (
        StationMembership("station-1", "Station", "active", frozenset({StationRole.SAFETY_SUPERVISOR})),))
    runtime = main.build_lake_runtime("lake-sammamish")
    monkeypatch.setitem(main.lake_runtimes, runtime.lake_id, runtime)
    monkeypatch.setattr(main, "authorize_lake", lambda *args: principal)
    monkeypatch.setattr(main, "get_access_repository", lambda: SimpleNamespace(lake_station_id=lambda _: "station-1"))
    monkeypatch.setattr(main, "_real_drone_ids", lambda _: ["real-1"])
    with pytest.raises(HTTPException) as error:
        main.start_simulation(runtime.lake_id, main.StartSimulationRequest(real_drones="replan"), None)
    assert error.value.status_code == 403
    assert error.value.detail == "Recent MFA is required"
    assert not runtime.engine.drones


def test_setup_status_does_not_claim_invalid_plan_is_ready(monkeypatch):
    context = _stored_context("invalid-status-lake")
    context["cells"] = []
    monkeypatch.setattr(main, "get_current_principal", lambda _: object())
    monkeypatch.setattr(main, "require_lake_permission", lambda *args: None)
    monkeypatch.setattr(main, "get_lake_runtime_repository", lambda: SimpleNamespace(runtime_context=lambda _: context))
    assert main.get_lake_setup_status("invalid-status-lake", None)["setup_status"] == "failed"
