from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import public_api


class PublicRepository:
    def list_lakes(self):
        return [
            {
                "lake_id": "lake-1",
                "name": "Lake Sammamish",
                "approximate_center_geohash": "c23nb",
                "public_status": "patrolling",
                "refreshed_at": datetime.now(timezone.utc).isoformat(),
            }
        ]

    def list_alerts(self, lake_id: str):
        assert lake_id == "lake-1"
        return [
            {
                "lake_id": lake_id,
                "category": "safety_notice",
                "approximate_area_label": "North lake area",
                "public_status": "active",
                "occurred_at": "2026-07-30T12:00:00Z",
                "published_at": "2026-07-30T12:05:00Z",
            }
        ]

    def list_patrol_presence(self, lake_id: str):
        assert lake_id == "lake-1"
        return [
            {
                "lake_id": lake_id,
                "generalized_zone": "North lake area",
                "public_state": "patrolling",
                "observed_bucket": "2026-07-30T12:00:00Z",
                "published_at": "2026-07-30T12:05:00Z",
            }
        ]


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(public_api.router)
    public_api.get_public_repository = lambda: PublicRepository()
    return TestClient(app)


def _assert_no_forbidden_keys(value: object) -> None:
    forbidden = {
        "latitude", "longitude", "altitude", "heading", "velocity", "route",
        "hardware_ref", "serial_number", "battery", "health", "maintenance_state",
        "connectivity_state", "station_address", "evidence_ref", "thermal_clip_ref",
        "subject_data", "response_tactics",
    }
    if isinstance(value, dict):
        assert not (set(value) & forbidden)
        for child in value.values():
            _assert_no_forbidden_keys(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_forbidden_keys(child)


def test_public_endpoints_return_only_sanitized_projection_fields():
    client = _client()

    lakes = client.get("/api/public/lakes")
    alerts = client.get("/api/public/lakes/lake-1/alerts")
    patrols = client.get("/api/public/lakes/lake-1/patrol-presence")

    assert lakes.status_code == alerts.status_code == patrols.status_code == 200
    response = {"lakes": lakes.json(), "alerts": alerts.json(), "patrols": patrols.json()}
    _assert_no_forbidden_keys(response)
    assert response["alerts"][0]["approximate_area_label"] == "North lake area"


def test_public_endpoints_do_not_require_an_operational_bearer_token():
    response = _client().get("/api/public/lakes")

    assert response.status_code == 200
