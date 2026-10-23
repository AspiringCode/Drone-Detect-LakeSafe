from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from app import main
from app.api import devices
from app.devices.repository import DeviceRepositoryError
from app.detection.detector import ThermalDetector
from app.detection.temporal import TemporalPersistenceFilter
from app.devices import drone_detect, drone_link, live_alerts

LAKE_ID = next(iter(main.lake_runtimes))


class Repo:
    def __init__(self, public_key: str, lake_id: str | None) -> None:
        self.public_key = public_key
        self.lake_id = lake_id
        self.claimed: set[int] = set()
        self.saved: list = []
        self.save_fails = False

    def save_real_alert(self, station_id, lake_id, alert):
        if self.save_fails:
            raise DeviceRepositoryError("down")
        self.saved.append((station_id, lake_id, alert.alert_id))

    def active_credential(self, drone_id):
        return {"credential_id": "cred-1", "drone_id": drone_id, "station_id": "station-1", "public_key": self.public_key, "credential_state": "active"}

    def claim_sequence(self, drone_id, sequence):
        if sequence in self.claimed:
            return False
        self.claimed.add(sequence)
        return True

    def real_inventory(self, drone_id):
        return {"inventory_id": drone_id, "station_id": "station-1", "lake_id": self.lake_id, "source": "real", "credential_state": "active"}


def _setup(monkeypatch, lake_id, repo_out=None):
    key = Ed25519PrivateKey.generate()
    repo = Repo(drone_link.public_key_b64url(key), lake_id)
    monkeypatch.setattr(devices, "get_device_repository", lambda: repo)
    monkeypatch.setattr(live_alerts, "_pending", {})
    if repo_out is not None:
        repo_out.append(repo)
    return key, TestClient(main.app)


def test_real_alert_is_saved_and_still_shown_live_when_saving_fails(monkeypatch):
    holder = []
    key, client = _setup(monkeypatch, LAKE_ID, holder)
    first = _post(client, key, BODY)
    assert first.json()["persisted"] is True and holder[0].saved == [("station-1", LAKE_ID, first.json()["alert_id"])]
    holder[0].save_fails = True
    second = _post(client, key, BODY)
    assert second.status_code == 202 and second.json()["persisted"] is False
    assert [a.alert_id for a in live_alerts._pending[LAKE_ID]] == [first.json()["alert_id"], second.json()["alert_id"]]


def test_saved_real_alerts_are_read_back_from_postgis_ewkb():
    from shapely import wkb
    from shapely.geometry import Point
    from app.devices.repository import SupabaseDeviceRepository

    ewkb = wkb.dumps(Point(-122.032, 47.592), hex=True, srid=4326)
    row = {"alert_id": "alert-1", "occurred_at": "2026-10-22T18:00:00+00:00", "precise_location": ewkb, "category": "thermal-cv", "hardware_ref": "d-1", "thermal_clip_ref": None}

    class Query:
        def __getattr__(self, _name): return lambda *a, **k: self
        def execute(self): return type("R", (), {"data": [row]})()

    client = type("C", (), {"table": lambda self, _name: Query()})()
    [alert] = SupabaseDeviceRepository(client).active_real_alerts("test-drone-field")
    assert (alert.alert_id, alert.location.lat, alert.location.lon, alert.source, alert.drone_id) == ("alert-1", 47.592, -122.032, "real", "d-1")


def _post(client, key, body: bytes, signed_body: bytes | None = None):
    sequence, timestamp = drone_link._now()
    return client.post("/api/devices/d-1/detections", content=body,
                       headers=drone_link.signed_headers(key, "d-1", signed_body or body, sequence=sequence, timestamp=timestamp))


BODY = json.dumps({"confidence": 0.82, "bbox": [10, 20, 30, 40], "detected_at": "2026-10-22T18:00:00.000000Z",
                   "position": {"lat": 47.59, "lon": -122.09}}).encode()


def test_signed_detection_becomes_a_real_alert_in_its_lake_runtime(monkeypatch):
    key, client = _setup(monkeypatch, LAKE_ID)
    response = _post(client, key, BODY)
    assert response.status_code == 202, response.text
    alert_id = response.json()["alert_id"]

    monkeypatch.setattr(main, "authorize_lake", lambda *args: None)
    alerts = client.get(f"/api/lakes/{LAKE_ID}/alerts").json()
    alert = next(a for a in alerts if a["alert_id"] == alert_id)
    assert (alert["source"], alert["drone_id"], alert["confirmed"], alert["location"]) == ("real", "d-1", True, {"lat": 47.59, "lon": -122.09})
    assert main.lake_runtimes[LAKE_ID].alert_backend.get(alert_id) is not None
    # Other lakes never see it.
    other = next(lake for lake in main.lake_runtimes if lake != LAKE_ID)
    assert all(a["alert_id"] != alert_id for a in client.get(f"/api/lakes/{other}/alerts").json())


def test_detection_from_a_drone_without_a_lake_is_rejected(monkeypatch):
    key, client = _setup(monkeypatch, None)
    assert _post(client, key, BODY).status_code == 409
    assert live_alerts._pending == {}


def test_tampered_detection_fails_authentication(monkeypatch):
    key, client = _setup(monkeypatch, LAKE_ID)
    assert _post(client, key, BODY.replace(b"0.82", b"0.99"), signed_body=BODY).status_code == 401
    assert live_alerts._pending == {}


@pytest.mark.parametrize("change", [{"confidence": 1.5}, {"position": None}, {"extra": 1}, {"detected_at": "2026-10-22T18:00:00"}])
def test_invalid_detection_payload_is_422(monkeypatch, change):
    key, client = _setup(monkeypatch, LAKE_ID)
    payload = {**json.loads(BODY), **change}
    assert _post(client, key, json.dumps(payload).encode()).status_code == 422


def test_thermal_frame_keeps_the_top_palette_half_as_single_channel():
    frame = np.zeros((384, 256, 3), dtype=np.uint8)
    frame[:192] = 200  # palette image
    frame[192:] = 7    # raw thermal bytes
    out = drone_detect.thermal_frame(frame)
    assert out.shape == (192, 256) and (out == 200).all()


class _Box:
    xyxy = np.array([[10.0, 10.0, 30.0, 50.0]])
    conf = np.array([0.9])


class _FakeYolo:
    def predict(self, frame, verbose=False):
        assert frame.shape == (192, 256, 3)
        return [type("Result", (), {"boxes": [_Box()]})()]


def test_one_person_in_view_alerts_once_per_cooldown():
    sent, now = [], [0.0]

    def frames():
        for index in range(10):
            now[0] = index * 5.0  # frames 5 s apart
            yield np.zeros((384, 256, 3), dtype=np.uint8)

    drone_detect.run(frames(), ThermalDetector(model=_FakeYolo(), source="real"), TemporalPersistenceFilter(n_consecutive=3),
                     lambda d: sent.append(d) or True, cooldown_s=30.0, clock=lambda: now[0])
    # Confirmed from the third frame (t=10 s); the next alert waits until t=40 s.
    assert [d.frame_idx for d in sent] == [2, 8] and sent[0].source == "real"


def test_undelivered_detection_is_retried_on_the_next_confirmed_frame():
    attempts = []
    frames = [np.zeros((384, 256, 3), dtype=np.uint8)] * 5
    drone_detect.run(frames, ThermalDetector(model=_FakeYolo(), source="real"), TemporalPersistenceFilter(n_consecutive=3),
                     lambda d: attempts.append(d) and False, clock=lambda: 0.0)
    assert [d.frame_idx for d in attempts] == [2, 3, 4]


def test_newest_real_alert_rides_the_operations_frame(monkeypatch):
    from datetime import datetime, timezone
    from app import main
    from app.devices import live_alerts
    from app.models import Detection, Drone, DroneStatus, LatLon
    from app.pipeline.alerts import assemble_alert

    runtime = main.build_test_area_runtime()
    monkeypatch.setattr(live_alerts, "_pending", {})
    assert main.current_state(runtime)["latest_alert"] is None
    at = datetime.now(timezone.utc)
    alert = assemble_alert(Detection(0, (1.0, 1.0, 2.0, 2.0), 0.9, at, source="real"),
                           Drone("d-1", LatLon(47.592, -122.032), 0.0, DroneStatus.INVESTIGATING, None, source="real"),
                           confirmed=True, clip_ref=None, detected_at=at)
    live_alerts.record(runtime.lake_id, alert)
    frame = main.current_state(runtime)
    assert frame["latest_alert"]["alert_id"] == alert.alert_id and frame["latest_alert"]["source"] == "real"
