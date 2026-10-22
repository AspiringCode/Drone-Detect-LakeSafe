from __future__ import annotations

import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import devices
from app.devices import drone_link


class Repo:
    def __init__(self, public_key: str) -> None:
        self.public_key = public_key
        self.heartbeats = []

    def active_credential(self, drone_id):
        return {"credential_id": "cred-1", "drone_id": drone_id, "station_id": "station-1", "public_key": self.public_key, "credential_state": "active"}

    def record_heartbeat(self, principal, heartbeat, received_at):
        self.heartbeats.append((principal, heartbeat))
        return {"eligible": True, "lake_id": "lake-1", "eligibility_changed": False}


def test_client_signed_heartbeat_is_accepted_by_the_device_endpoint(monkeypatch):
    key = Ed25519PrivateKey.generate()
    repo = Repo(drone_link.public_key_b64url(key))
    app = FastAPI()
    app.include_router(devices.router)
    monkeypatch.setattr(devices, "get_device_repository", lambda: repo)
    client = TestClient(app)

    body = json.dumps({"battery_percent": 87, "health": "healthy", "connected": True}).encode()
    sequence, timestamp = drone_link._now()
    response = client.post("/api/devices/d-1/heartbeat", content=body,
                           headers=drone_link.signed_headers(key, "d-1", body, sequence=sequence, timestamp=timestamp))

    assert response.status_code == 202, response.text
    principal, heartbeat = repo.heartbeats[0]
    assert (principal.drone_id, principal.sequence, heartbeat.battery_percent) == ("d-1", sequence, 87)

    # Signing a different body than the one sent must fail closed.
    tampered = client.post("/api/devices/d-1/heartbeat", content=body.replace(b"87", b"99"),
                           headers=drone_link.signed_headers(key, "d-1", body, sequence=sequence + 1, timestamp=timestamp))
    assert tampered.status_code == 401


def test_positioned_heartbeat_reaches_the_operations_feed_as_real_until_stale(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app.devices import live_positions

    key = Ed25519PrivateKey.generate()
    repo = Repo(drone_link.public_key_b64url(key))
    app = FastAPI()
    app.include_router(devices.router)
    monkeypatch.setattr(devices, "get_device_repository", lambda: repo)
    monkeypatch.setattr(live_positions, "_latest", {})
    body = json.dumps({"battery_percent": 64, "health": "healthy", "connected": True, "flight_status": "patrolling",
                       "position": {"lat": 47.59, "lon": -122.09, "alt_m": 30}}).encode()
    sequence, timestamp = drone_link._now()
    response = TestClient(app).post("/api/devices/d-1/heartbeat", content=body,
                                    headers=drone_link.signed_headers(key, "d-1", body, sequence=sequence, timestamp=timestamp))
    assert response.status_code == 202, response.text

    state = live_positions.with_real_drones("lake-1", {"drones": ["sim"], "t": 1})
    real = state["drones"][1]
    assert state["drones"][0] == "sim" and state["t"] == 1
    assert (real.drone_id, real.source, real.pos.lat, real.battery, real.status.value) == ("d-1", "real", 47.59, 0.64, "patrolling")
    assert live_positions.snapshot("other-lake") == []
    assert live_positions.snapshot("lake-1", datetime.now(timezone.utc) + timedelta(minutes=5)) == []


def test_keygen_refuses_to_overwrite_an_existing_identity(tmp_path, capsys):
    path = tmp_path / "drone.pem"
    assert drone_link.main(["keygen", "--key", str(path)]) == 0
    assert len(capsys.readouterr().out.strip()) == 43  # 32 raw bytes, unpadded base64url
    try:
        drone_link.main(["keygen", "--key", str(path)])
    except SystemExit:
        pass
    else:
        raise AssertionError("keygen overwrote an existing key")
