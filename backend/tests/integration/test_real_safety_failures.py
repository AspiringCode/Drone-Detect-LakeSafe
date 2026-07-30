from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.access.principal import Principal, StationMembership, StationRole, get_principal


class SafetyRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.status = {
            "station_id": "station-1", "lake_id": "lake-1", "autonomy": "paused",
            "active_assignments": (), "pending_assignments": (),
        }

    def lake_belongs_to_station(self, station_id: str, lake_id: str) -> bool:
        return station_id == "station-1" and lake_id == "lake-1"

    def set_real_autonomy(self, station_id: str, lake_id: str, enabled: bool, reason: str, actor_user_id: str):
        self.calls.append(("autonomy", (station_id, lake_id, enabled, reason, actor_user_id)))
        self.status = {**self.status, "autonomy": "pending_ack" if enabled else "safe_return_requested"}
        return self.status

    def request_safe_return(self, station_id: str, lake_id: str, reason: str, actor_user_id: str):
        self.calls.append(("safe-return", (station_id, lake_id, reason, actor_user_id)))
        self.status = {**self.status, "autonomy": "safe_return_requested"}
        return self.status

    def real_fleet_status(self, station_id: str, lake_id: str):
        assert self.lake_belongs_to_station(station_id, lake_id)
        return {
            **self.status,
            "source": "real",
            "heartbeat_age_seconds": 4,
            "eligible": True,
            "desired_state_version": 7,
            "acknowledged_state_version": 6,
        }

    def append_audit(self, event) -> None:
        self.calls.append(("audit", event))


class Reconciler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def reconcile_lake(self, lake_id: str, trigger: str, expected_plan_id=None):
        self.calls.append((lake_id, trigger))


def _principal(role: StationRole, *, recent_mfa: bool = True, station_id: str = "station-1") -> Principal:
    amr = ({"method": "totp", "timestamp": datetime.now(timezone.utc).timestamp()},) if recent_mfa else ()
    return Principal("user-1", "officer@example.gov", "aal2", "officer", "verified", (StationMembership(station_id, "Station", "active", frozenset({role})),), amr)


def _client(principal: Principal, repository: SafetyRepository, reconciler: Reconciler) -> TestClient:
    from app.api import safety
    app = FastAPI()
    app.include_router(safety.router)
    app.dependency_overrides[get_principal] = lambda: principal
    safety.get_safety_repository = lambda: repository
    safety.get_real_capacity_reconciler = lambda: reconciler
    return TestClient(app)


def test_admin_without_safety_role_cannot_enable_real_autonomy():
    response = _client(_principal(StationRole.STATION_ADMIN), SafetyRepository(), Reconciler()).post(
        "/api/stations/station-1/lakes/lake-1/safety/autonomy", json={"enabled": True, "reason": "shift start"}
    )
    assert response.status_code == 403


def test_verified_station_viewer_can_read_real_safety_status_without_secrets_or_controls():
    response = _client(_principal(StationRole.VIEWER), SafetyRepository(), Reconciler()).get(
        "/api/stations/station-1/lakes/lake-1/safety/status"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "station_id": "station-1", "lake_id": "lake-1", "autonomy": "paused",
        "active_assignments": [], "pending_assignments": [], "source": "real",
        "heartbeat_age_seconds": 4, "eligible": True,
        "desired_state_version": 7, "acknowledged_state_version": 6,
    }
    assert not {"public_key", "credential_id", "serial", "coordinate", "route"} & payload.keys()


def test_safety_supervisor_with_recent_mfa_changes_policy_audits_and_reconciles():
    repository, reconciler = SafetyRepository(), Reconciler()
    response = _client(_principal(StationRole.SAFETY_SUPERVISOR), repository, reconciler).post(
        "/api/stations/station-1/lakes/lake-1/safety/autonomy", json={"enabled": True, "reason": "shift start"}
    )
    assert response.status_code == 202
    assert response.json()["autonomy"] == "pending_ack"
    assert repository.calls[0][0] == "autonomy"
    assert repository.calls[1][0] == "audit"
    assert reconciler.calls == [("lake-1", "real_safety_policy_changed")]


def test_safety_controls_require_reason_recent_mfa_and_exact_lake():
    client = _client(_principal(StationRole.SAFETY_SUPERVISOR, recent_mfa=False), SafetyRepository(), Reconciler())
    assert client.post("/api/stations/station-1/lakes/lake-1/safety/autonomy", json={"enabled": True, "reason": "x"}).status_code == 403
    client = _client(_principal(StationRole.SAFETY_SUPERVISOR), SafetyRepository(), Reconciler())
    assert client.post("/api/stations/station-1/lakes/lake-2/safety/autonomy", json={"enabled": True, "reason": "x"}).status_code == 404
    assert client.post("/api/stations/station-1/lakes/lake-1/safety/autonomy", json={"enabled": True, "reason": "   "}).status_code == 422


def test_safe_return_requests_fleet_policy_without_coordinates():
    repository, reconciler = SafetyRepository(), Reconciler()
    response = _client(_principal(StationRole.SAFETY_SUPERVISOR), repository, reconciler).post(
        "/api/stations/station-1/lakes/lake-1/safety/safe-return", json={"reason": "weather warning"}
    )
    assert response.status_code == 202
    assert response.json()["autonomy"] == "safe_return_requested"
    assert repository.calls[0][0] == "safe-return"
    assert reconciler.calls == [("lake-1", "real_safe_return_requested")]
    assert client_payload_rejects_coordinates(_client(_principal(StationRole.SAFETY_SUPERVISOR), SafetyRepository(), Reconciler()))


def client_payload_rejects_coordinates(client: TestClient) -> bool:
    response = client.post("/api/stations/station-1/lakes/lake-1/safety/safe-return", json={"reason": "weather", "latitude": 47.0})
    return response.status_code == 422


def test_partial_ack_is_degraded_not_active_and_preserves_last_acknowledged_state():
    from app.autonomy.safety import RealFleetStatus, classify_real_fleet_status

    result = classify_real_fleet_status(
        RealFleetStatus("pending_ack", active_assignments=("d1",), pending_assignments=("d2",), last_acknowledged_versions={"d1": 3, "d2": 1}),
        expired_drone_ids=("d2",), safe_return_required=False,
    )
    assert result.autonomy == "degraded"
    assert result.active_assignments == ("d1",)
    assert result.pending_assignments == ()
    assert result.last_acknowledged_versions == {"d1": 3, "d2": 1}


def test_gateway_unavailable_and_safe_return_are_truthful_failure_states():
    from app.autonomy.safety import RealFleetStatus, mark_gateway_unavailable, request_safe_return

    pending = RealFleetStatus("pending_ack", active_assignments=("d1",), pending_assignments=("d2",))
    assert mark_gateway_unavailable(pending).autonomy == "gateway_unavailable"
    assert request_safe_return(pending).autonomy == "safe_return_requested"


def test_bounded_real_command_retry_expires_without_losing_last_acknowledgement():
    from app.autonomy.outbox import retry_schedule

    assert retry_schedule(attempts=1, maximum_attempts=3, now=10.0, expires_at=100.0) == ("retry", 12.0)
    assert retry_schedule(attempts=3, maximum_attempts=3, now=10.0, expires_at=100.0) == ("expired", None)
    assert retry_schedule(attempts=1, maximum_attempts=3, now=101.0, expires_at=100.0) == ("expired", None)


def test_database_safety_contract_requires_supervisor_and_emits_coordinate_free_return_commands():
    sql = (Path(__file__).parents[3] / "supabase" / "migrations" / "0026_real_fleet_safety.sql").read_text().lower()
    assert "membership_role.role='safety_supervisor'" in sql
    assert "return_to_reserve" in sql and "desired_state_version" in sql
    assert "jsonb_build_object('source','real','transport','real_gateway','reason'" in sql
