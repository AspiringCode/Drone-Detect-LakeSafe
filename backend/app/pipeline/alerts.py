from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.config import SUPABASE_KEY, SUPABASE_URL
from app.models import Alert, Detection, Drone


def assemble_alert(
    detection: Detection,
    drone: Drone,
    confirmed: bool,
    clip_ref: str | None,
    detected_at: datetime,
) -> Alert:
    now = datetime.now(timezone.utc)
    latency_ms = max(0, int((now - detected_at).total_seconds() * 1000))
    return Alert(
        alert_id=f"alert-{uuid4().hex}",
        created_at=now,
        location=drone.pos,
        detection_mode="thermal-cv",
        drone_id=drone.drone_id,
        thermal_clip_ref=clip_ref,
        confirmed=confirmed,
        source=detection.source,
        latency_ms=latency_ms,
        confidence=detection.confidence,
        bbox=detection.bbox,
    )


class InMemoryBackend:
    def __init__(self) -> None:
        self.records: dict[str, Alert] = {}

    def save(self, alert: Alert) -> str:
        self.records[alert.alert_id] = alert
        return alert.alert_id

    def get(self, alert_id: str) -> Alert | None:
        return self.records.get(alert_id)

    def list(self) -> list[Alert]:
        return list(self.records.values())


class SupabaseBackend:
    def __init__(self, station_id: str, lake_id: str) -> None:
        from supabase import create_client

        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY are required")
        self.client = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.station_id = station_id
        self.lake_id = lake_id

    def save(self, alert: Alert) -> str:
        payload = {
            "alert_id": alert.alert_id,
            "station_id": self.station_id,
            "lake_id": self.lake_id,
            "occurred_at": alert.created_at.isoformat(),
            "precise_location": f"POINT({alert.location.lon} {alert.location.lat})",
            "category": alert.detection_mode,
            "status": "active",
            "source": alert.source,
            "thermal_clip_ref": alert.thermal_clip_ref,
        }
        self.client.table("operational_alerts").insert(payload).execute()
        return alert.alert_id


class AlertRepository:
    def __init__(self, backend=None, *, station_id: str | None = None, lake_id: str | None = None) -> None:
        if backend is None:
            if not station_id or not lake_id:
                raise ValueError("station_id and lake_id are required for operational alert persistence")
            backend = SupabaseBackend(station_id, lake_id)
        self.backend = backend

    def save(self, alert: Alert) -> str:
        return self.backend.save(alert)
