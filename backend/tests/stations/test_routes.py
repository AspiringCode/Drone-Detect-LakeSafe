from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.access.principal import Principal, StationMembership, StationRole, get_principal
from app.stations import routes
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
