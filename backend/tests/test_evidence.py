from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.access.principal import Principal, StationMembership, StationRole
from app.evidence import EvidenceForbidden, EvidenceNotFound, EvidenceService


class _Alerts:
    def __init__(self, alert: dict | None):
        self.alert = alert

    def get_operational_alert(self, alert_id: str) -> dict | None:
        return self.alert if self.alert and self.alert["alert_id"] == alert_id else None


class _Storage:
    def __init__(self):
        self.calls: list[tuple[str, str, int]] = []

    def create_signed_url(self, bucket: str, path: str, expires_in: int) -> str:
        self.calls.append((bucket, path, expires_in))
        return "https://evidence.test/signed"


class _Audit:
    def __init__(self):
        self.events = []

    def record(self, event):
        self.events.append(event)


def _principal(*, station_id: str = "station-a", civilian: bool = False) -> Principal:
    return Principal(
        user_id="00000000-0000-0000-0000-000000000001",
        email="officer@example.test",
        aal="aal2",
        account_class="civilian" if civilian else "officer",
        verification_status=None if civilian else "verified",
        memberships=() if civilian else (
            StationMembership(station_id, "Station A", "active", frozenset({StationRole.VIEWER})),
        ),
    )


def _alert(*, station_id: str = "station-a", clip: str | None = "clips/alert-1.mp4") -> dict:
    return {
        "alert_id": "alert-1",
        "station_id": station_id,
        "lake_id": "lake-1",
        "thermal_clip_ref": clip,
    }


def test_station_viewer_receives_a_sixty_second_thermal_url_and_allowed_audit():
    storage = _Storage()
    audit = _Audit()
    service = EvidenceService(_Alerts(_alert()), storage, audit)

    result = service.create_authorized_url("alert-1", _principal())

    assert result.url == "https://evidence.test/signed"
    assert result.expires_in == 60
    assert storage.calls == [("thermal-clips", "clips/alert-1.mp4", 60)]
    assert audit.events[-1].decision == "allowed"
    assert audit.events[-1].action == "thermal_evidence.read"


def test_cross_station_evidence_access_is_not_disclosed():
    storage = _Storage()
    audit = _Audit()
    service = EvidenceService(_Alerts(_alert(station_id="station-b")), storage, audit)

    with pytest.raises(EvidenceNotFound):
        service.create_authorized_url("alert-1", _principal())

    assert storage.calls == []
    assert audit.events[-1].decision == "denied"


def test_civilian_evidence_access_is_denied_without_loading_evidence():
    storage = _Storage()
    audit = _Audit()
    service = EvidenceService(_Alerts(_alert()), storage, audit)

    with pytest.raises(EvidenceForbidden):
        service.create_authorized_url("alert-1", _principal(civilian=True))

    assert storage.calls == []
    assert audit.events[-1].decision == "denied"


def test_missing_and_cross_station_evidence_have_the_same_not_found_outcome():
    principal = _principal()
    missing = EvidenceService(_Alerts(None), _Storage(), _Audit())
    cross_station = EvidenceService(_Alerts(_alert(station_id="station-b")), _Storage(), _Audit())

    with pytest.raises(EvidenceNotFound):
        missing.create_authorized_url("missing", principal)
    with pytest.raises(EvidenceNotFound):
        cross_station.create_authorized_url("alert-1", principal)


def test_thermal_endpoint_returns_only_a_short_lived_url(monkeypatch):
    from app.access.principal import get_principal
    from app.main import app
    import app.evidence as evidence

    app.dependency_overrides[get_principal] = lambda: _principal()
    monkeypatch.setattr(
        evidence,
        "get_evidence_service",
        lambda: EvidenceService(_Alerts(_alert()), _Storage(), _Audit()),
    )
    try:
        response = TestClient(app).get("/api/evidence/alerts/alert-1/thermal")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"url": "https://evidence.test/signed", "expires_in": 60}
