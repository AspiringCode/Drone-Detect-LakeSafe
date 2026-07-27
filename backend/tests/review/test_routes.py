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
