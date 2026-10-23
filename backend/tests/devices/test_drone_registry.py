from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.access.principal import Principal, StationMembership, StationRole, get_principal
from app.api import device_admin
from app.devices import live_positions
from app.devices.repository import DeviceRepositoryError


class Repo:
    def __init__(self):
        self.drones = {"d-1": {"inventory_id": "d-1", "lake_id": None, "lifecycle": "available"}}

    def list_real(self, station_id):
        return list(self.drones.values())

    def attach_real_to_lake(self, station_id, drone_id, lake_id):
        if lake_id == "other-station-lake" or drone_id not in self.drones:
            raise DeviceRepositoryError("no")
        self.drones[drone_id].update(lake_id=lake_id, lifecycle="circulating" if lake_id else "available")
        return {"inventory_id": drone_id, **self.drones[drone_id]}


def _client(monkeypatch, role, *, mfa_age=timedelta(0), judge=False):
    amr = () if judge else ({"method": "totp", "timestamp": (datetime.now(timezone.utc) - mfa_age).timestamp()},)
    principal = Principal("user-1", "o@gov", "aal1" if judge else "aal2", "officer", "verified",
                          (StationMembership("st-1", "Station", "active", frozenset({role})),), amr, judge_demo_access=judge)
    repo = Repo()
    app = FastAPI()
    app.include_router(device_admin.router)
    app.dependency_overrides[get_principal] = lambda: principal
    monkeypatch.setattr(device_admin, "get_device_repository", lambda: repo)
    monkeypatch.setattr(live_positions, "_latest", {})
    return TestClient(app), repo


def test_only_inventory_admins_list_real_drones(monkeypatch):
    client, _ = _client(monkeypatch, StationRole.VIEWER)
    assert client.get("/api/stations/st-1/inventory/real").status_code == 403
    assert client.get("/api/stations/other/inventory/real").status_code == 404
    client, _ = _client(monkeypatch, StationRole.STATION_ADMIN)
    assert client.get("/api/stations/st-1/inventory/real").json()["drones"][0]["inventory_id"] == "d-1"


def test_assigning_a_lake_needs_recent_mfa_and_a_station_lake(monkeypatch):
    stale, _ = _client(monkeypatch, StationRole.STATION_ADMIN, mfa_age=timedelta(hours=1))
    assert stale.post("/api/stations/st-1/inventory/d-1/lake", json={"lake_id": "test-drone-field"}).status_code in {401, 403}
    client, repo = _client(monkeypatch, StationRole.STATION_ADMIN)
    assert client.post("/api/stations/st-1/inventory/d-1/lake", json={"lake_id": "other-station-lake"}).status_code == 409
    assert client.post("/api/stations/st-1/inventory/d-1/lake", json={"lake_id": "test-drone-field"}).json()["lifecycle"] == "circulating"
    assert client.post("/api/stations/st-1/inventory/d-1/lake", json={"lake_id": None}).json()["lifecycle"] == "available"


def test_password_only_demo_admin_skips_only_the_mfa_step_up(monkeypatch):
    judge, _ = _client(monkeypatch, StationRole.STATION_ADMIN, judge=True)
    assert judge.post("/api/stations/st-1/inventory/d-1/lake", json={"lake_id": "test-drone-field"}).status_code == 200
    viewer_judge, _ = _client(monkeypatch, StationRole.VIEWER, judge=True)
    assert viewer_judge.post("/api/stations/st-1/inventory/d-1/lake", json={"lake_id": "test-drone-field"}).status_code == 403


def test_test_position_is_labeled_simulated_and_needs_an_assigned_lake(monkeypatch):
    client, repo = _client(monkeypatch, StationRole.STATION_ADMIN)
    assert client.post("/api/stations/st-1/inventory/d-1/test-position", json={"lat": 47.592, "lon": -122.032}).status_code == 409
    repo.drones["d-1"]["lake_id"] = "test-drone-field"
    response = client.post("/api/stations/st-1/inventory/d-1/test-position", json={"lat": 47.592, "lon": -122.032})
    assert response.status_code == 202
    [marker] = live_positions.snapshot("test-drone-field")
    assert marker.source == "simulated" and marker.drone_id == "d-1 (test)"
    # Outlives a heartbeat TTL but still expires.
    assert live_positions.snapshot("test-drone-field", datetime.now(timezone.utc) + timedelta(minutes=1))
    assert not live_positions.snapshot("test-drone-field", datetime.now(timezone.utc) + timedelta(minutes=6))
