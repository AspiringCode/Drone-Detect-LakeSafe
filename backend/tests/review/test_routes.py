from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.access.principal import Principal, get_principal
from app.review import routes


def _client(principal: Principal) -> TestClient:
    app = FastAPI(); app.include_router(routes.router)
    app.dependency_overrides[get_principal] = lambda: principal
    return TestClient(app)


def test_ordinary_user_cannot_access_internal_reviews():
    response = _client(Principal("user-1", "officer@example.gov", "aal2", "officer", "verified", ())).get(
        "/api/internal/reviews/station-requests"
    )
    assert response.status_code == 403


def test_reviewer_receives_repository_backed_station_queue(monkeypatch):
    class Repository:
        def list_station_requests_for_review(self):
            return [{"station_request_id": "request-1", "requested_name": "Station One", "status": "pending"}]
    app = FastAPI(); app.include_router(routes.router)
    app.dependency_overrides[get_principal] = lambda: Principal("staff-1", "staff@example.gov", "aal2", "officer", "verified", ())
    monkeypatch.setattr(routes, "is_reviewer", lambda _: True)
    monkeypatch.setattr(routes, "get_workflow_repository", lambda: Repository())
    response = TestClient(app).get("/api/internal/reviews/station-requests")
    assert response.status_code == 200
    assert response.json()["requests"][0]["station_request_id"] == "request-1"
