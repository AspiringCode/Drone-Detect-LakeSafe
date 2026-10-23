import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from httpx import ConnectError
from postgrest.exceptions import APIError

from app.access.principal import get_principal, principal_from_claims


class Repository:
    def __init__(self, state): self.state = state
    def load_principal_state(self, user_id): return self.state


def test_principal_uses_server_side_profile_and_memberships_not_jwt_roles():
    principal = principal_from_claims(
        {"sub": "user-1", "aal": "aal2", "role": "station_admin"},
        Repository({"account_class": "officer", "verification_status": "verified", "memberships": [{"station_id": "station-1", "station_name": "One", "membership_status": "active", "roles": ["viewer"]}]}),
    )
    assert principal.memberships[0].roles == {"viewer"}
    assert principal.account_class == "officer"


def test_missing_server_profile_is_civilian_without_memberships():
    principal = principal_from_claims({"sub": "user-1", "aal": "aal2"}, Repository(None))
    assert principal.account_class == "civilian"
    assert not principal.memberships

@pytest.mark.parametrize("failure", [
    RuntimeError("upstream unavailable"),
    ConnectError("connection failed"),
    APIError({"message": "profiles unavailable", "code": "42P01", "hint": None, "details": None}),
    UnicodeEncodeError("ascii", "\u2028", 0, 1, "invalid header"),
])
def test_principal_repository_failures_are_service_unavailable(failure):
    class UnavailableRepository:
        def load_principal_state(self, user_id):
            raise failure

    with pytest.raises(HTTPException) as error:
        principal_from_claims({"sub": "user-1"}, UnavailableRepository())
    assert error.value.status_code == 503
    assert error.value.detail == "Account data is temporarily unavailable"


def test_principal_does_not_mask_authorization_or_programming_errors():
    for failure in (HTTPException(403, "denied"), TypeError("programming error")):
        class RepositoryFailure:
            def load_principal_state(self, user_id):
                raise failure
        with pytest.raises(type(failure)) as error:
            principal_from_claims({"sub": "user-1"}, RepositoryFailure())
        assert error.value is failure


@pytest.mark.parametrize("url, key", [("https://example.supabase.co", "invalid-\u2028-key"), ("", "configured-key"), ("invalid-url", "configured-key")])
def test_repository_configuration_failure_is_service_unavailable(monkeypatch, url, key):
    from app.access import principal, repository
    monkeypatch.setattr(principal, "verify_supabase_jwt", lambda token: {"sub": "user-1"})
    monkeypatch.setattr(repository, "SUPABASE_URL", url)
    monkeypatch.setattr(repository, "SUPABASE_SERVICE_ROLE_KEY", key)
    repository.get_access_repository.cache_clear()
    try:
        with pytest.raises(HTTPException) as error:
            principal.get_principal("Bearer valid-token")
        assert error.value.status_code == 503
        assert error.value.detail == "Account data is temporarily unavailable"
    finally:
        repository.get_access_repository.cache_clear()


def test_invalid_token_is_not_converted_to_repository_unavailability(monkeypatch):
    from app.access import principal, repository
    failure = HTTPException(401, "invalid token")
    def reject(token):
        raise failure
    monkeypatch.setattr(principal, "verify_supabase_jwt", reject)
    monkeypatch.setattr(repository, "get_access_repository", lambda: pytest.fail("repository must not be used"))
    with pytest.raises(HTTPException) as error:
        principal.get_principal("Bearer invalid-token")
    assert error.value is failure


def test_account_outage_response_retains_cors_headers(monkeypatch):
    from app.access import principal, repository
    monkeypatch.setattr(principal, "verify_supabase_jwt", lambda token: {"sub": "user-1"})
    class UnavailableRepository:
        def load_principal_state(self, user_id):
            raise APIError({"message": "profiles unavailable", "code": "42P01", "hint": None, "details": None})
    monkeypatch.setattr(repository, "get_access_repository", lambda: UnavailableRepository())
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"])
    @app.get("/api/me")
    def account(user=Depends(get_principal)):
        return {"user_id": user.user_id}
    with TestClient(app) as client:
        response = client.get("/api/me", headers={"Authorization": "Bearer valid-token", "Origin": "http://localhost:5173"})
    assert response.status_code == 503
    assert response.json() == {"detail": "Account data is temporarily unavailable"}
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


@pytest.mark.parametrize("trusted", [False, True])
def test_judge_access_comes_only_from_server_state(trusted):
    principal = principal_from_claims({
        "sub": "user-1", "aal": "aal1", "judge_demo_access": True,
        "user_metadata": {"judge_demo_access": True},
        "app_metadata": {"judge_demo_access": True},
    }, Repository({"account_class": "officer", "judge_demo_access": trusted}))
    assert principal.judge_demo_access is trusted
