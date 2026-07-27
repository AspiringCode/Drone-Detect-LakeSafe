from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.access.principal import Principal, get_principal
from app.verification import routes
from app.verification.idme import IdMeSettings


def _app():
    app = FastAPI(); app.include_router(routes.router)
    app.dependency_overrides[get_principal] = lambda: Principal("user", None, None, "civilian", None, ())
    return app


def test_start_requires_principal_and_returns_authorization_url(monkeypatch):
    monkeypatch.setattr(routes, "get_workflow_repository", lambda: type("R", (), {"create_verification_session": lambda *_: None})())
    monkeypatch.setattr(routes, "start_authorization", lambda *_: "https://authorize?state=state")
    monkeypatch.setattr(routes.IdMeSettings, "from_config", classmethod(lambda cls: IdMeSettings("id", "secret", "https://cb", "issuer", "aud", "https://authorize", "https://token", "https://keys", "https://userinfo", "/ok", "/fail")))
    response = TestClient(_app()).post("/api/verifications/idme/start")
    assert response.status_code == 200 and "authorization_url" in response.json()
    assert "code_verifier" not in response.json()["authorization_url"]


def test_callback_failure_redirects_without_promoting(monkeypatch):
    monkeypatch.setattr(routes.IdMeSettings, "from_config", classmethod(lambda cls: IdMeSettings("id", "secret", "https://cb", "issuer", "aud", "https://authorize", "https://token", "https://keys", "https://userinfo", "/ok", "/fail")))
    response = TestClient(_app()).get("/api/verifications/idme/callback?error=denied", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/fail"
