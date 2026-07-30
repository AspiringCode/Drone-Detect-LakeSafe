from datetime import datetime, timedelta, timezone

from app.models import Detection, Drone, DroneStatus, LatLon
from app.pipeline.alerts import AlertRepository, InMemoryBackend, SupabaseBackend, assemble_alert


def test_assemble_alert_sets_latency_source_and_confirmed():
    detected_at = datetime.now(timezone.utc) - timedelta(milliseconds=5)
    detection = Detection(0, (1.0, 2.0, 3.0, 4.0), 0.9, detected_at, "simulated")
    drone = Drone("d1", LatLon(47.58, -122.09), 0.9, DroneStatus.INVESTIGATING, "z1")
    alert = assemble_alert(detection, drone, confirmed=True, clip_ref="clips/a.npy", detected_at=detected_at)

    assert alert.latency_ms is not None and alert.latency_ms >= 0
    assert alert.latency_ms < 10_000
    assert alert.source == "simulated"
    assert alert.confirmed is True


def test_assemble_alert_uses_timezone_aware_utc_timestamp():
    detected_at = datetime.now(timezone.utc)
    detection = Detection(0, (1.0, 2.0, 3.0, 4.0), 0.9, detected_at, "simulated")
    drone = Drone("d1", LatLon(47.58, -122.09), 0.9, DroneStatus.INVESTIGATING, "z1")

    alert = assemble_alert(detection, drone, confirmed=True, clip_ref=None, detected_at=detected_at)

    assert alert.created_at.tzinfo is timezone.utc


def test_in_memory_repository_saves_and_retrieves_alert():
    backend = InMemoryBackend()
    repo = AlertRepository(backend)
    now = datetime.now(timezone.utc)
    alert = assemble_alert(
        Detection(0, (1, 1, 2, 2), 0.8, now, "real"),
        Drone("d1", LatLon(47.58, -122.09), 1.0, DroneStatus.IDLE, None, source="real"),
        confirmed=False,
        clip_ref=None,
        detected_at=now,
    )

    saved_id = repo.save(alert)
    assert saved_id == alert.alert_id
    assert backend.get(saved_id) == alert


def test_supabase_persistence_targets_operational_alerts_only():
    calls = []

    class Table:
        def insert(self, payload):
            calls.append(payload)
            return self
        def execute(self):
            return None
    class Client:
        def table(self, name):
            assert name == "operational_alerts"
            return Table()

    backend = SupabaseBackend.__new__(SupabaseBackend)
    backend.client = Client()
    backend.station_id = "station-1"
    backend.lake_id = "lake-sammamish"
    now = datetime.now(timezone.utc)
    alert = assemble_alert(Detection(0, (1, 1, 2, 2), .8, now, "simulated"), Drone("d1", LatLon(47.58, -122.09), 1, DroneStatus.IDLE, None), False, None, now)

    backend.save(alert)

    assert calls[0]["station_id"] == "station-1"
    assert calls[0]["lake_id"] == "lake-sammamish"
    assert "precise_location" in calls[0]
    assert "location" not in calls[0]
