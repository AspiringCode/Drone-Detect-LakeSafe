from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.access.principal import Principal
from app.correlation import REQUEST_ID_HEADER, get_request_id, request_id_from_header
from app.rate_limits import RateLimitRepository, RateLimitUnavailable, require_rate_limit


class _Result:
    def __init__(self, data): self.data = data


class _Call:
    def __init__(self, data): self._data = data
    def execute(self): return _Result(self._data)


class _Client:
    def __init__(self, data): self.data = data; self.name = None; self.parameters = None
    def rpc(self, name, parameters):
        self.name, self.parameters = name, parameters
        return _Call(self.data)


def _principal() -> Principal:
    return Principal("00000000-0000-0000-0000-000000000001", None, "aal2", "officer", "verified", ())


def test_claim_uses_backend_only_atomic_rpc_and_station_scoped_subject():
    client = _Client({"allowed": False, "retry_after_seconds": 42})
    result = RateLimitRepository(client).claim(scope="safety.autonomy", subject="station:a:user:u", limit=5, window_seconds=60)
    assert result.allowed is False and result.retry_after_seconds == 42
    assert client.name == "claim_rate_limit"
    assert client.parameters == {"p_scope": "safety.autonomy", "p_subject": "station:a:user:u", "p_limit": 5, "p_window_seconds": 60}


def test_invalid_rpc_response_fails_closed():
    with pytest.raises(RateLimitUnavailable):
        RateLimitRepository(_Client({"allowed": "yes"})).claim(scope="safety.autonomy", subject="s", limit=1, window_seconds=1)


def test_request_id_accepts_only_canonical_uuid_and_is_returned(monkeypatch):
    app = FastAPI()

    @app.middleware("http")
    async def correlation(request: Request, call_next):
        request.state.request_id = request_id_from_header(request.headers.get(REQUEST_ID_HEADER))
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = str(request.state.request_id)
        return response

    @app.get("/")
    def root(request: Request): return {"request_id": str(get_request_id(request))}

    supplied = "00000000-0000-0000-0000-000000000099"
    response = TestClient(app).get("/", headers={REQUEST_ID_HEADER: supplied})
    assert response.headers[REQUEST_ID_HEADER] == supplied == response.json()["request_id"]
    invalid = TestClient(app).get("/", headers={REQUEST_ID_HEADER: "not-a-uuid"})
    assert invalid.headers[REQUEST_ID_HEADER] != "not-a-uuid"
    assert UUID(invalid.headers[REQUEST_ID_HEADER])


def test_denied_limit_returns_retry_after_and_audits(monkeypatch):
    app = FastAPI()

    @app.middleware("http")
    async def correlation(request: Request, call_next):
        request.state.request_id = request_id_from_header(None)
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = str(request.state.request_id)
        return response

    class Limiter:
        def claim(self, **kwargs):
            from app.rate_limits import RateLimitResult
            return RateLimitResult(False, 8)

    events = []
    class Audit:
        def record(self, event): events.append(event)

    import app.rate_limits as limits
    monkeypatch.setattr(limits, "get_rate_limit_repository", lambda: Limiter())
    monkeypatch.setattr(limits, "get_audit_writer", lambda: Audit())

    @app.post("/safety")
    def safety(request: Request):
        require_rate_limit("safety.autonomy", _principal(), request, station_id="station-a", lake_id="lake-a")
        return {"ok": True}

    response = TestClient(app).post("/safety")
    assert response.status_code == 429 and response.headers["Retry-After"] == "8"
    assert events[-1].decision == "denied"
    assert events[-1].request_id == UUID(response.headers[REQUEST_ID_HEADER])
