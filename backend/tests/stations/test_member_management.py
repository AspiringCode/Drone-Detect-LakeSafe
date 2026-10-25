from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.access.principal import Principal, StationMembership, StationRole, get_principal
from app.stations import routes
from app.stations.repository import WorkflowConflict


class Repository:
    def __init__(self):
        self.changed = None

    def list_members(self, station_id):
        return [{"membership_id": "m-1", "user_id": "u-2", "status": "active", "roles": ["viewer"], "display_name": "Operator"}]

    def change_member(self, station_id, membership_id, actor, roles, status):
        if membership_id == "last-admin":
            raise WorkflowConflict("A station must retain an administrator")
        self.changed = (station_id, membership_id, actor, roles, status)
        return {"membership_id": membership_id, "status": status, "roles": list(roles)}

    def list_my_join_requests(self, user_id):
        return [{"station_join_request_id": "j-1", "station_id": "s-1", "station_name": "Station", "status": "pending"}]


def client_for(monkeypatch, role=StationRole.STATION_ADMIN):
    principal = Principal("u-1", "u@gov", "aal2", "officer", "verified", (
        StationMembership("s-1", "Station", "active", frozenset({role})),
    ), ({"method": "totp", "timestamp": datetime.now(timezone.utc).timestamp()},))
    repository = Repository()
    monkeypatch.setattr(routes, "get_workflow_repository", lambda: repository)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_principal] = lambda: principal
    return TestClient(app), repository


def test_roster_and_changes_are_station_admin_scoped(monkeypatch):
    client, repo = client_for(monkeypatch)
    assert client.get("/api/stations/s-1/members").json()["members"][0]["display_name"] == "Operator"
    body = {"roles": ["dispatcher"], "status": "active"}
    assert client.patch("/api/stations/s-1/members/m-1", json=body).status_code == 200
    assert repo.changed == ("s-1", "m-1", "u-1", ("dispatcher",), "active")
    assert client.patch("/api/stations/other/members/m-1", json=body).status_code == 403
    assert client.patch("/api/stations/s-1/members/last-admin", json=body).status_code == 409
    assert client.patch("/api/stations/s-1/members/m-1", json={**body, "roles": ["owner"]}).status_code == 422
    viewer, _ = client_for(monkeypatch, StationRole.VIEWER)
    assert viewer.get("/api/stations/s-1/members").status_code == 403
    assert viewer.patch("/api/stations/s-1/members/m-1", json=body).status_code == 403


def test_request_status_is_only_the_signed_in_users_queue(monkeypatch):
    client, _ = client_for(monkeypatch)
    result = client.get("/api/station-join-requests/mine")
    assert result.status_code == 200
    assert result.json()["requests"][0]["status"] == "pending"
