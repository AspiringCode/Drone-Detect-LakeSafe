from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.access.principal import Principal, StationMembership, StationRole, get_principal
from app.lakes import routes

STATION = "00000000-0000-4000-8000-000000000001"

def client(monkeypatch, role=StationRole.STATION_ADMIN, recent=True):
    app = FastAPI(); app.include_router(routes.router)
    actor = Principal("actor", None, "aal2", "officer", "verified", (
        StationMembership(STATION, "Existing station", "active", frozenset({role})),),
        amr=({"method":"totp","timestamp":datetime.now(timezone.utc).timestamp()},) if recent else ())
    app.dependency_overrides[get_principal] = lambda: actor
    calls = []
    def create(source, target, name, lake):
        calls.append((source,target,name,lake))
        return {"lake_id":lake.lake_id,"station_id":target or "new-station","station_created":target is None}
    monkeypatch.setattr(routes,"get_workflow_repository",lambda:SimpleNamespace(create_lake_workspace=create))
    monkeypatch.setattr(routes,"selected_lake",lambda candidate_id:{"name":"Lake Washington","centroid_lat":47.64,"centroid_lon":-122.258,"shoreline":{"type":"MultiPolygon","coordinates":[]}})
    monkeypatch.setattr(routes,"search_lakes",lambda query:[{"candidate_id":13645,"name":"Lake Washington"}])
    return TestClient(app),calls

def test_admin_searches_by_name_and_creates_in_existing_station(monkeypatch):
    http,calls=client(monkeypatch)
    assert http.get("/api/lake-search?query=Washington").json()["candidates"][0]["candidate_id"]==13645
    response=http.post("/api/lake-setups",json={"candidate_id":13645,"station_id":STATION})
    assert response.status_code==201 and response.json()["station_created"] is False
    assert calls[0][3].name=="Lake Washington"

def test_admin_can_create_new_lake_station_without_granting_other_roles(monkeypatch):
    http,calls=client(monkeypatch)
    response=http.post("/api/lake-setups",json={"candidate_id":13645,"new_station_name":"Washington station"})
    assert response.status_code==201 and response.json()["station_created"] is True
    assert calls[0][:3]==(STATION,None,"Washington station")

@pytest.mark.parametrize("body",[{"candidate_id":13645},{"candidate_id":13645,"station_id":STATION,"new_station_name":"New"},{"candidate_id":13645,"new_station_name":"  "}])
def test_destination_must_be_explicit(monkeypatch,body):
    http,calls=client(monkeypatch)
    assert http.post("/api/lake-setups",json=body).status_code==422
    assert calls==[]

def test_viewer_and_cross_station_requests_cannot_create_workspaces(monkeypatch):
    http,calls=client(monkeypatch,StationRole.VIEWER)
    assert http.get("/api/lake-search?query=Washington").status_code==403
    assert http.post("/api/lake-setups",json={"candidate_id":13645,"new_station_name":"New station"}).status_code==403
    http,calls=client(monkeypatch)
    assert http.post("/api/lake-setups",json={"candidate_id":13645,"station_id":"00000000-0000-4000-8000-000000000002"}).status_code==403
    assert calls==[]

def test_new_station_creation_keeps_recent_mfa_requirement(monkeypatch):
    http,calls=client(monkeypatch,recent=False)
    assert http.post("/api/lake-setups",json={"candidate_id":13645,"new_station_name":"New station"}).status_code==403
    assert calls==[]
