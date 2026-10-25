from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.access.principal import Principal, StationMembership, StationRole, get_principal
from app.access.principal import principal_from_claims
from app.stations import routes
from app.review import routes as review_routes
from app.stations.models import JoinRequest, StationMembership as WorkflowMembership, StationRequest


class Repository:
    def __init__(self) -> None:
        self.created_invitation = None

    def create_station_request(self, value):
        return StationRequest("request-1", value.requested_by, value.requested_name, value.requested_address, "pending")

    def create_join_request(self, value):
        return JoinRequest("join-1", value.station_id, value.user_id, "pending")

    def create_invitation(self, value):
        self.created_invitation = value

    def accept_invitation(self, token_hash, user_id, email):
        return WorkflowMembership("membership-1", "station-1", user_id, "active", ("viewer",))

    def search_stations(self, query, state=None):
        return [{"station_id": "station-1", "name": "Station One", "state": "WA"}]

    def list_station_requests_for_user(self, user_id):
        return [StationRequest("request-1", user_id, "Station One", None, "pending")]

    def list_join_requests_for_station(self, station_id):
        return [JoinRequest("join-1", station_id, "user-2", "pending")]


def _principal(*, role: StationRole | None = None, aal: str = "aal2") -> Principal:
    memberships = () if role is None else (StationMembership("station-1", "Station One", "active", frozenset({role})),)
    return Principal("user-1", "officer@example.gov", aal, "officer", "verified", memberships)


def _client(principal: Principal, repository: Repository) -> TestClient:
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_principal] = lambda: principal
    routes.get_workflow_repository = lambda: repository
    return TestClient(app)


def test_civilian_cannot_request_station():
    response = _client(Principal("user-1", None, "aal2", "civilian", None, ()), Repository()).post(
        "/api/station-requests", json={"name": "LakeSafe PD", "address": "1 Main St, Seattle, WA"}
    )
    assert response.status_code == 403


def test_admin_invitation_returns_plaintext_once_and_stores_only_hash():
    repository = Repository()
    response = _client(_principal(role=StationRole.STATION_ADMIN), repository).post(
        "/api/stations/station-1/invitations",
        json={"email": "Officer@Example.Gov", "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()},
    )
    assert response.status_code == 201
    assert len(response.json()["token"]) >= 43
    assert repository.created_invitation.intended_email == "officer@example.gov"
    assert len(repository.created_invitation.token_hash) == 64


def test_aal1_cannot_create_invitation():
    response = _client(_principal(role=StationRole.STATION_ADMIN, aal="aal1"), Repository()).post(
        "/api/stations/station-1/invitations", json={"email": "officer@example.gov"}
    )
    assert response.status_code == 403


def test_authenticated_jwt_email_is_used_when_accepting_an_invitation():
    repository = Repository()
    principal = principal_from_claims(
        {"sub": "user-1", "email": "Officer@Example.Gov", "aal": "aal2"},
        type("Access", (), {"load_principal_state": lambda *_: {"account_class": "officer", "verification_status": "verified", "memberships": []}})(),
    )
    response = _client(principal, repository).post("/api/invitations/accept", json={"token": "a" * 43})
    assert response.status_code == 200


def test_search_and_workflow_queues_are_repository_backed():
    response = _client(_principal(role=StationRole.STATION_ADMIN), Repository()).get("/api/stations?query=one")
    assert response.status_code == 200
    assert response.json()["stations"][0]["station_id"] == "station-1"
    client = _client(_principal(role=StationRole.STATION_ADMIN), Repository())
    assert client.get("/api/station-requests/mine").json()["requests"][0]["station_request_id"] == "request-1"
    assert client.get("/api/stations/station-1/join-requests").json()["requests"][0]["station_join_request_id"] == "join-1"


def test_station_search_rejects_unimplemented_state_filter():
    assert _client(_principal(), Repository()).get("/api/stations?state=WA").status_code == 422


@pytest.mark.parametrize(("roles", "expected"), [
    (frozenset({StationRole.VIEWER}), {"station.read"}),
    (frozenset({StationRole.DISPATCHER}), {"station.read", "alert.manage"}),
    (frozenset({StationRole.SAFETY_SUPERVISOR}), {"station.read", "autonomy.manage", "fleet_safety.manage"}),
    (frozenset({StationRole.STATION_ADMIN}), {"station.read", "alert.manage", "lake.create", "inventory.manage", "autonomy.manage", "member.manage"}),
    (frozenset({StationRole.DISPATCHER, StationRole.SAFETY_SUPERVISOR}), {"station.read", "alert.manage", "autonomy.manage", "fleet_safety.manage"}),
])
def test_me_capabilities_mirror_additive_policy_roles(monkeypatch, roles, expected):
    principal = Principal("user-1", "officer@example.gov", "aal2", "officer", "verified", (
        StationMembership("station-1", "Station One", "active", roles),
    ))
    monkeypatch.setattr(review_routes, "is_reviewer", lambda _: False)
    response = _client(principal, Repository()).get("/api/me")
    assert response.status_code == 200
    assert set(response.json()["memberships"][0]["capabilities"]) == expected


@pytest.mark.parametrize("allowed", [True, False])
def test_me_reports_server_judge_session_exception(monkeypatch, allowed):
    from dataclasses import replace
    principal = replace(_principal(), judge_demo_access=allowed)
    monkeypatch.setattr(review_routes, "is_reviewer", lambda _: False)
    response = _client(principal, Repository()).get("/api/me")
    assert response.status_code == 200
    assert response.json()["judge_demo_access"] is allowed
