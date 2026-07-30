from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import devices
from app.devices.auth import canonical_request_bytes
from app.devices.auth import DevicePrincipal
from app.devices.heartbeat import HeartbeatService
from app.devices.monitor import HeartbeatMonitor


class Repository:
    def __init__(self) -> None:
        self.records: list[dict] = []
        self.expired = False

    def record_heartbeat(self, principal, heartbeat, received_at):
        self.records.append({"principal": principal, "heartbeat": heartbeat, "received_at": received_at})
        recovered = self.expired
        self.expired = False
        return {"eligible": True, "lake_id": "lake-1", "eligibility_changed": recovered}

    def expire_stale_eligible_real(self, now, ttl_seconds):
        if self.expired:
            return ()
        self.expired = True
        return ("lake-1",)


class Autonomy:
    def __init__(self) -> None:
        self.calls = []

    def reconcile_lake(self, lake_id, trigger, expected_plan_id=None):
        self.calls.append((lake_id, trigger))


class AuthRepository(Repository):
    def __init__(self, public_key: bytes) -> None:
        super().__init__()
        self._public_key = base64.urlsafe_b64encode(public_key).rstrip(b"=").decode()

    def active_credential(self, drone_id):
        return {"drone_id": drone_id, "station_id": "station-1", "credential_id": "credential-1", "public_key": self._public_key}

    def claim_sequence(self, drone_id, sequence):
        return True


def heartbeat(**overrides):
    return {
        "battery_percent": 80,
        "health": "healthy",
        "connected": True,
        **overrides,
    }


def test_authenticated_recovery_triggers_replan():
    repository, autonomy = Repository(), Autonomy()
    repository.expired = True
    result = HeartbeatService(repository, autonomy).record(
        DevicePrincipal("d-1", "station-1", "credential-1"), heartbeat()
    )
    assert result.eligible is True
    assert result.reconcile_trigger == "heartbeat_recovery"
    assert autonomy.calls == [("lake-1", "heartbeat_recovery")]


def test_stale_heartbeat_marks_offline_once():
    repository, autonomy = Repository(), Autonomy()
    monitor = HeartbeatMonitor(repository, autonomy, ttl_seconds=15)
    assert monitor.scan(datetime.now(timezone.utc)) == ("lake-1",)
    assert monitor.scan(datetime.now(timezone.utc)) == ()
    assert autonomy.calls == [("lake-1", "heartbeat_expired")]


def _signature(private, drone_id, timestamp, sequence, body):
    return base64.urlsafe_b64encode(private.sign(canonical_request_bytes(drone_id, timestamp, sequence, body))).rstrip(b"=").decode()


def test_heartbeat_authenticates_raw_body_before_json_parsing(monkeypatch):
    private = Ed25519PrivateKey.generate()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = b"this is not json"
    app = FastAPI()
    app.include_router(devices.router)
    monkeypatch.setattr(devices, "get_device_repository", lambda: AuthRepository(private.public_key().public_bytes_raw()))
    # A bad signature on non-JSON must be rejected by device auth, not parsed as
    # a request body before its signature is checked.
    response = TestClient(app).post(
        "/api/devices/d-1/heartbeat",
        content=body,
        headers={"X-Device-Timestamp": timestamp, "X-Device-Sequence": "1", "X-Device-Signature": "A" * 86},
    )
    assert response.status_code == 401
