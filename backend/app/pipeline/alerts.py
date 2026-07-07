from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
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
    now = datetime.utcnow()
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
    def __init__(self) -> None:
        from supabase import create_client

        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY are required")
        self.client = create_client(SUPABASE_URL, SUPABASE_KEY)

    def save(self, alert: Alert) -> str:
        payload = asdict(alert)
        payload["location"] = asdict(alert.location)
        payload["created_at"] = alert.created_at.isoformat()
        self.client.table("alerts").insert(payload).execute()
        return alert.alert_id


class AlertRepository:
    def __init__(self, backend=None) -> None:
        self.backend = backend if backend is not None else SupabaseBackend()

    def save(self, alert: Alert) -> str:
        return self.backend.save(alert)
