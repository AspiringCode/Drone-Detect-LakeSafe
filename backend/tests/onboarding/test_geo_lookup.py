from __future__ import annotations

import base64
import hashlib
import hmac
import httpx
import json
from pathlib import Path
import time
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


class StubHttpClient:
    def __init__(self, responses: list[object]) -> None:
        self.responses = iter(responses)
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get(self, url: str, **kwargs: object) -> httpx.Response:
        self.calls.append((url, kwargs))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response

    def close(self) -> None:
        pass


def response(url: str, payload: object, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", url)
    return httpx.Response(status_code, json=payload, request=request)


TEST_JWT_SECRET = "onboarding-test-jwt-secret"
MIGRATION_PATH = Path(__file__).parents[3] / "supabase" / "migrations" / "0002_orgs_lakes.sql"


def test_lake_sammamish_seed_is_safe_when_demo_auth_user_is_absent():
    """The optional demo seed must not prevent a fresh Supabase migration."""
    migration = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "from auth.users" in migration.lower()
    assert "demo_owner.id" in migration
    assert "select 'lake-sammamish'" in migration.lower()


def _signed_jwt(secret: str, *, algorithm: str = "HS256") -> str:
    def encode(value: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(
            json.dumps(value, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()

    header = encode({"alg": algorithm, "typ": "JWT"})
    claims = encode({"sub": "8f0a7fa0-3924-4a76-8533-85028fd53917", "exp": time.time() + 3600})
    signature = hmac.new(
        secret.encode(), f"{header}.{claims}".encode(), hashlib.sha256
    ).digest()
    return f"{header}.{claims}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def _app_with_test_jwt_secret(monkeypatch: pytest.MonkeyPatch):
    """Patch the loaded verifier without replacing the shared FastAPI app."""
    import app.auth
    import app.main

    monkeypatch.setattr(app.auth, "SUPABASE_JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setattr(app.auth, "SUPABASE_JWT_ISSUER", None)
    monkeypatch.setattr(app.auth, "SUPABASE_JWT_AUDIENCE", None)

    return app.main


def _organization_payload() -> dict[str, object]:
    return {
        "name": "LakeSafe",
        "station_lat": 47.6,
        "station_lon": -122.1,
        "lake_name": "Lake Sammamish",
        "lake_lat": 47.58,
        "lake_lon": -122.08,
    }


def test_lookup_geocodes_address_and_extracts_lake_centroids(monkeypatch: pytest.MonkeyPatch):
    from app.onboarding import geo_lookup

    client = StubHttpClient([
        response("https://nominatim.openstreetmap.org/search", [{"lat": "47.6000", "lon": "-122.1000"}]),
        response("https://overpass-api.de/api/interpreter", {
            "elements": [
                {"type": "way", "id": 1, "tags": {"name": "Lake Sammamish", "natural": "water"}, "center": {"lat": 47.58, "lon": -122.08}},
                {"type": "node", "id": 2, "tags": {"name": "Small Lake", "natural": "water"}, "lat": 47.61, "lon": -122.11},
            ]
        }),
    ])
    monkeypatch.setattr(geo_lookup.httpx, "Client", lambda **_: client)

    result = geo_lookup.lookup_nearby_lakes("Sammamish, WA")

    assert result.address == "Sammamish, WA"
    assert result.coordinates == geo_lookup.LatLon(latitude=47.6, longitude=-122.1)
    assert [(lake.name, lake.latitude, lake.longitude) for lake in result.lakes] == [
        ("Lake Sammamish", 47.58, -122.08),
        ("Small Lake", 47.61, -122.11),
    ]
    assert client.calls[0][1]["headers"] == {"User-Agent": "LakeSafe-CAC/1.0"}
    assert "around:10000,47.6,-122.1" in client.calls[1][1]["params"]["data"]


def test_lookup_uses_kumi_only_after_primary_overpass_failure(monkeypatch: pytest.MonkeyPatch):
    from app.onboarding import geo_lookup

    client = StubHttpClient([
        response("https://nominatim.openstreetmap.org/search", [{"lat": "47.6", "lon": "-122.1"}]),
        httpx.ConnectError("primary unavailable"),
        response("https://overpass.kumi.systems/api/interpreter", {"elements": []}),
    ])
    monkeypatch.setattr(geo_lookup.httpx, "Client", lambda **_: client)

    assert geo_lookup.lookup_nearby_lakes("Sammamish, WA").lakes == []
    assert [call[0] for call in client.calls][2] == geo_lookup.OVERPASS_KUMI_URL


def test_lookup_raises_not_found_when_nominatim_has_no_result(monkeypatch: pytest.MonkeyPatch):
    from app.onboarding import geo_lookup

    client = StubHttpClient([response("https://nominatim.openstreetmap.org/search", [])])
    monkeypatch.setattr(geo_lookup.httpx, "Client", lambda **_: client)

    with pytest.raises(geo_lookup.AddressNotFoundError):
        geo_lookup.lookup_nearby_lakes("not a real address")


def test_nearby_lakes_endpoint_returns_specified_candidate_contract(monkeypatch: pytest.MonkeyPatch):
    from app.main import app
    from app.onboarding.geo_lookup import LatLon, NearbyLake, NearbyLakeLookup

    monkeypatch.setattr(
        "app.main.lookup_nearby_lakes",
        lambda address: NearbyLakeLookup(address=address, coordinates=LatLon(47.6, -122.1), lakes=[NearbyLake("Lake Sammamish", 47.58, -122.08)]),
    )

    response = TestClient(app).post("/api/onboarding/nearby-lakes", json={"station_name": "LakeSafe", "station_address": "Sammamish, WA"})

    assert response.status_code == 200
    assert response.json() == {
        "station": {"lat": 47.6, "lon": -122.1},
        "candidates": [{"name": "Lake Sammamish", "lat": 47.58, "lon": -122.08}],
    }


def test_organization_endpoint_uses_specified_body_and_never_accepts_a_body_user_id(monkeypatch: pytest.MonkeyPatch):
    from app.main import app

    expected = {"org_id": "org-1", "lake_id": "lake-1"}
    captured: dict[str, object] = {}

    def create(**kwargs: object) -> dict[str, str]:
        captured.update(kwargs)
        return expected

    monkeypatch.setattr("app.main.create_organization_and_lake", create)
    monkeypatch.setattr("app.main.verify_supabase_jwt", lambda token: {"sub": "8f0a7fa0-3924-4a76-8533-85028fd53917"})

    payload = {
        "name": "LakeSafe",
        "station_lat": 47.6,
        "station_lon": -122.1,
        "lake_name": "Lake Sammamish",
        "lake_lat": 47.58,
        "lake_lon": -122.08,
    }
    response = TestClient(app).post(
        "/api/onboarding/organizations", json=payload, headers={"Authorization": "Bearer signed-token"}
    )

    assert response.status_code == 201
    assert response.json() == expected
    assert captured["owner_user_id"] == "8f0a7fa0-3924-4a76-8533-85028fd53917"

    rejected = TestClient(app).post(
        "/api/onboarding/organizations",
        json={**payload, "owner_user_id": "untrusted-user-id"},
        headers={"Authorization": "Bearer signed-token"},
    )
    assert rejected.status_code == 422


def test_organization_endpoint_accepts_a_real_hs256_jwt(monkeypatch: pytest.MonkeyPatch):
    main = _app_with_test_jwt_secret(monkeypatch)
    captured: dict[str, object] = {}

    def create(**kwargs: object) -> dict[str, str]:
        captured.update(kwargs)
        return {"org_id": "org-1", "lake_id": "lake-1"}

    monkeypatch.setattr(main, "create_organization_and_lake", create)

    response = TestClient(main.app).post(
        "/api/onboarding/organizations",
        json=_organization_payload(),
        headers={"Authorization": f"Bearer {_signed_jwt(TEST_JWT_SECRET)}"},
    )

    assert response.status_code == 201
    assert captured["owner_user_id"] == "8f0a7fa0-3924-4a76-8533-85028fd53917"


@pytest.mark.parametrize(
    "token",
    [
        _signed_jwt("wrong-test-jwt-secret"),
        _signed_jwt(TEST_JWT_SECRET, algorithm="RS256"),
    ],
    ids=["invalid-signature", "non-hs256"],
)
def test_organization_endpoint_rejects_jwts_the_real_verifier_does_not_trust(
    monkeypatch: pytest.MonkeyPatch, token: str
):
    main = _app_with_test_jwt_secret(monkeypatch)

    def persistence_must_not_run(**_: object) -> dict[str, str]:
        raise AssertionError("Persistence must not run for rejected bearer tokens")

    monkeypatch.setattr(main, "create_organization_and_lake", persistence_must_not_run)

    response = TestClient(main.app, raise_server_exceptions=False).post(
        "/api/onboarding/organizations",
        json=_organization_payload(),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


@pytest.mark.parametrize("authorization", [None, "Bearer invalid-token"])
def test_organization_endpoint_rejects_missing_or_invalid_bearer_token(
    monkeypatch: pytest.MonkeyPatch, authorization: str | None
):
    from app.main import app

    monkeypatch.setattr(
        "app.main.verify_supabase_jwt",
        lambda token: (_ for _ in ()).throw(HTTPException(status_code=401, detail="Invalid bearer token")),
    )
    headers = {"Authorization": authorization} if authorization is not None else {}
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/onboarding/organizations",
        json={
            "name": "LakeSafe", "station_lat": 47.6, "station_lon": -122.1,
            "lake_name": "Lake Sammamish", "lake_lat": 47.58, "lake_lon": -122.08,
        },
        headers=headers,
    )

    assert response.status_code == 401
