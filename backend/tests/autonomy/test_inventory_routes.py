from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.access.principal import Principal, StationMembership, StationRole, get_principal


class Repository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def register_simulated_inventory(self, station_id: str, count: int) -> list[dict]:
        self.calls.append(("register", (station_id, count)))
        return [{"inventory_id": "drone-1", "station_id": station_id, "source": "simulated", "lifecycle": "available", "desired_state_version": 0, "acknowledged_state_version": 0}]

    def set_simulated_circulation(self, station_id: str, inventory_id: str, lake_id: str, eligible: bool, reason: str, actor_user_id: str, reconciliation_id: str) -> dict:
        self.calls.append(("circulation", (station_id, inventory_id, lake_id, eligible, reason, actor_user_id, reconciliation_id)))
        return {"inventory_id": inventory_id, "station_id": station_id, "lake_id": lake_id if eligible else None, "source": "simulated", "lifecycle": "circulating" if eligible else "available", "desired_state_version": 4 if eligible else 5, "acknowledged_state_version": 2, "pending_command_type": None if eligible else "return_to_reserve", "reconciliation_id": reconciliation_id}

    def fleet(self, station_id: str, lake_id: str) -> list[dict]:
        self.calls.append(("fleet", (station_id, lake_id)))
        return [{"inventory_id": "drone-1", "station_id": station_id, "lake_id": lake_id, "source": "simulated", "lifecycle": "circulating", "desired_state_version": 4, "acknowledged_state_version": 2}]


def _principal(role: StationRole | None, station_id: str = "station-1", *, recent_mfa: bool = True) -> Principal:
    amr = ({"method": "totp", "timestamp": datetime.now(timezone.utc).timestamp()},) if recent_mfa else ()
    memberships = () if role is None else (StationMembership(station_id, "Station", "active", frozenset({role})),)
    return Principal("user-1", "officer@example.gov", "aal2", "officer", "verified", memberships, amr)


def _client(principal: Principal, repository: Repository) -> TestClient:
    from app.api import inventory

    app = FastAPI()
    app.include_router(inventory.router)
    app.dependency_overrides[get_principal] = lambda: principal
    inventory.get_inventory_repository = lambda: repository
    return TestClient(app)


def test_station_admin_can_register_simulated_inventory_only():
    repository = Repository()
    response = _client(_principal(StationRole.STATION_ADMIN), repository).post("/api/stations/station-1/inventory/simulated", json={"count": 1})
    assert response.status_code == 201
    assert response.json()["drones"][0]["source"] == "simulated"
    assert repository.calls == [("register", ("station-1", 1))]


def test_viewer_cannot_register_or_change_circulation():
    client = _client(_principal(StationRole.VIEWER), Repository())
    assert client.post("/api/stations/station-1/inventory/simulated", json={"count": 1}).status_code == 403
    assert client.post("/api/stations/station-1/lakes/lake-1/circulation/drone-1", json={"eligible": True, "reason": "routine patrol"}).status_code == 403


def test_inventory_allowance_conflict_is_not_reported_as_a_success():
    from app.autonomy.inventory_repository import InventoryWorkflowConflict

    class FullRepository(Repository):
        def register_simulated_inventory(self, station_id: str, count: int) -> list[dict]:
            raise InventoryWorkflowConflict("allowance exceeded")

    response = _client(_principal(StationRole.STATION_ADMIN), FullRepository()).post("/api/stations/station-1/inventory/simulated", json={"count": 2})
    assert response.status_code == 409


def test_safety_supervisor_changes_circulation_with_recent_mfa_and_reconciliation_id():
    repository = Repository()
    response = _client(_principal(StationRole.SAFETY_SUPERVISOR), repository).post(
        "/api/stations/station-1/lakes/lake-1/circulation/drone-1",
        json={"eligible": True, "reason": "routine patrol"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["desired_state_version"] == 4
    assert body["acknowledged_state_version"] == 2
    assert body["reconciliation_id"]
    assert repository.calls[0][0] == "circulation"


def test_station_admin_can_change_simulated_circulation():
    response = _client(_principal(StationRole.STATION_ADMIN), Repository()).post(
        "/api/stations/station-1/lakes/lake-1/circulation/drone-1",
        json={"eligible": False, "reason": "return to reserve"},
    )
    assert response.status_code == 202
    assert response.json()["pending_command_type"] == "return_to_reserve"
    assert response.json()["desired_state_version"] > response.json()["acknowledged_state_version"]


def test_circulation_payload_rejects_any_manual_or_real_control_fields():
    response = _client(_principal(StationRole.STATION_ADMIN), Repository()).post(
        "/api/stations/station-1/lakes/lake-1/circulation/drone-1",
        json={"eligible": True, "reason": "routine patrol", "source": "real"},
    )
    assert response.status_code == 422


def test_circulation_requires_recent_mfa():
    response = _client(_principal(StationRole.SAFETY_SUPERVISOR, recent_mfa=False), Repository()).post(
        "/api/stations/station-1/lakes/lake-1/circulation/drone-1",
        json={"eligible": True, "reason": "routine patrol"},
    )
    assert response.status_code == 403


def test_cross_station_is_hidden_and_fleet_exposes_desired_vs_acknowledged_versions():
    repository = Repository()
    client = _client(_principal(StationRole.STATION_ADMIN), repository)
    assert client.get("/api/stations/station-2/lakes/lake-1/fleet").status_code == 404
    response = client.get("/api/stations/station-1/lakes/lake-1/fleet")
    assert response.status_code == 200
    drone = response.json()["drones"][0]
    assert drone["desired_state_version"] == 4
    assert drone["acknowledged_state_version"] == 2
