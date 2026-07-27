from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.access.principal import Principal, StationMembership, StationRole, get_principal
from app.lakes import routes


class Repository:
    def __init__(self): self.value = None
    def create_lake(self, value):
        self.value = value
        return type("Lake", (), {"lake_id": value.lake_id, "station_id": value.station_id, "name": value.name})()


def _client(role: StationRole) -> tuple[TestClient, Repository]:
    repository = Repository(); app = FastAPI(); app.include_router(routes.router)
    principal = Principal("user-1", "officer@example.gov", "aal2", "officer", "verified", (StationMembership("station-1", "Station", "active", frozenset({role})),))
    app.dependency_overrides[get_principal] = lambda: principal
    routes.get_workflow_repository = lambda: repository
    routes.resolve_shoreline = lambda *_: {"type": "MultiPolygon", "coordinates": [[[[ -122.1, 47.6], [-122.0, 47.6], [-122.0, 47.7], [-122.1, 47.6]]]]}
    return TestClient(app), repository


def test_admin_creates_lake_with_fallback_when_no_reviewed_connector():
    client, repository = _client(StationRole.STATION_ADMIN)
    response = client.post("/api/stations/station-1/lakes", json={"name": "Lake Demo", "centroid_lat": 47.6, "centroid_lon": -122.1, "bbox": [-122.2, 47.5, -122.0, 47.7]})
    assert response.status_code == 201
    assert response.json()["data_source_status"] == "fallback_coverage"
    assert repository.value.station_id == "station-1"


def test_viewer_cannot_create_lake():
    client, _ = _client(StationRole.VIEWER)
    response = client.post("/api/stations/station-1/lakes", json={"name": "Lake Demo", "centroid_lat": 47.6, "centroid_lon": -122.1, "bbox": [-122.2, 47.5, -122.0, 47.7]})
    assert response.status_code == 403


def test_reviewed_connector_status_is_persisted_and_returned(monkeypatch):
    client, repository = _client(StationRole.STATION_ADMIN)
    monkeypatch.setattr(routes, "reviewed_connector_for", lambda *_: "king-county-water")
    response = client.post("/api/stations/station-1/lakes", json={"name": "Lake Demo", "centroid_lat": 47.6, "centroid_lon": -122.1, "bbox": [-122.2, 47.5, -122.0, 47.7]})
    assert response.status_code == 201
    assert response.json()["data_source_status"] == "reviewed"
    assert repository.value.data_source_status == "reviewed"
