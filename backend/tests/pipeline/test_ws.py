import pytest
from fastapi.testclient import TestClient

from app.main import app, lake_runtimes, publish_public_patrol_presence, public_patrol_payload
from app.pipeline.ws import ConnectionHub, tick_loop


@pytest.mark.anyio
async def test_connection_hub_broadcasts_to_clients():
    class Client:
        def __init__(self):
            self.sent = None

        async def send_json(self, payload):
            self.sent = payload

    hub = ConnectionHub()
    client = Client()
    hub.clients.add(client)
    await hub.broadcast({"drones": [{"source": "simulated"}]})
    assert client.sent["drones"][0]["source"] == "simulated"


@pytest.mark.anyio
async def test_tick_loop_advances_engine_and_broadcasts_every_iteration():
    class FakeEngine:
        def __init__(self):
            self.calls = 0

        def step(self, dt):
            self.calls += 1
            return {"drones": [{"source": "simulated"}], "t": self.calls * dt}

    hub = ConnectionHub()
    broadcasts = []

    async def fake_broadcast(state):
        broadcasts.append(state)

    hub.broadcast = fake_broadcast  # type: ignore[method-assign]

    engine = FakeEngine()
    await tick_loop(engine, hub, jsonify=lambda s: s, interval=0.001, iterations=3)

    assert engine.calls == 3
    assert len(broadcasts) == 3
    assert broadcasts[-1]["t"] == pytest.approx(3 * 0.001)


@pytest.mark.anyio
async def test_tick_loop_broadcasts_the_jsonified_state():
    class FakeEngine:
        def step(self, dt):
            return {"raw": "state"}

    hub = ConnectionHub()
    broadcasts = []

    async def fake_broadcast(state):
        broadcasts.append(state)

    hub.broadcast = fake_broadcast  # type: ignore[method-assign]

    await tick_loop(
        FakeEngine(),
        hub,
        jsonify=lambda s: {"wrapped": s},
        interval=0.001,
        iterations=1,
    )

    assert broadcasts == [{"wrapped": {"raw": "state"}}]


def test_operational_websocket_requires_subprotocol_token():
    with pytest.raises(Exception):
        with TestClient(app).websocket_connect("/ws/operations/lakes/lake-sammamish") as ws:
            ws.receive_json()

    with pytest.raises(Exception):
        with TestClient(app).websocket_connect(
            "/ws/operations/lakes/lake-sammamish?token=never-in-a-url",
            subprotocols=["bearer.token"],
        ) as ws:
            ws.receive_json()


def test_operational_websocket_closes_when_verification_is_revoked(monkeypatch):
    class RevokedRepository:
        def load_principal_state(self, user_id):
            return {"account_class": "officer", "verification_status": "revoked", "memberships": [{
                "station_id": "station-1", "station_name": "Demo", "membership_status": "active", "roles": ["viewer"],
            }]}

        def lake_station_id(self, lake_id): return "station-1"

    monkeypatch.setattr("app.main.get_access_repository", lambda: RevokedRepository())
    monkeypatch.setattr("app.main.verify_supabase_jwt", lambda token: {"sub": "user", "aal": "aal2"})
    with pytest.raises(Exception):
        with TestClient(app).websocket_connect("/ws/operations/lakes/lake-sammamish", subprotocols=["bearer.token"]) as ws:
            ws.receive_json()


def test_message_sending_client_is_revalidated_and_closed_after_deadline(monkeypatch):
    class Repository:
        def __init__(self): self.calls = 0

        def load_principal_state(self, user_id):
            self.calls += 1
            return {"account_class": "officer", "verification_status": "verified" if self.calls == 1 else "revoked", "memberships": [{
                "station_id": "station-1", "station_name": "Demo", "membership_status": "active", "roles": ["viewer"],
            }]}

        def lake_station_id(self, lake_id): return "station-1"

    repository = Repository()
    clock_values = iter([0.0, 0.0, 0.0, 29.0, 29.0, 31.0, 31.0])
    monkeypatch.setattr("app.main.get_access_repository", lambda: repository)
    monkeypatch.setattr("app.main.verify_supabase_jwt", lambda token: {"sub": "user", "aal": "aal2"})
    monkeypatch.setattr("app.main.WS_REVALIDATION_CLOCK", lambda: next(clock_values))
    with TestClient(app).websocket_connect("/ws/operations/lakes/lake-sammamish", subprotocols=["bearer.token"]) as ws:
        ws.receive_json()
        ws.send_text("keepalive")
        ws.send_text("keepalive")
        ws.send_text("keepalive")
        with pytest.raises(Exception) as error:
            ws.receive_json()
    assert getattr(error.value, "code", None) == 1008
    assert repository.calls == 2


def test_public_websocket_accepts_no_token_and_rejects_url_credentials():
    with TestClient(app).websocket_connect("/ws/public/lakes/lake-sammamish") as ws:
        ws.send_text("keepalive")

    with pytest.raises(Exception):
        with TestClient(app).websocket_connect(
            "/ws/public/lakes/lake-sammamish?access_token=never-in-a-url"
        ) as ws:
            ws.receive_text()


def test_public_websocket_payload_is_exactly_the_projection_dto():
    payload = public_patrol_payload({
        "lake_id": "lake-sammamish",
        "generalized_zone": "north basin",
        "public_state": "patrolling",
        "observed_bucket": "2026-07-30T12:00:00Z",
        "published_at": "2026-07-30T12:05:00Z",
    })

    assert set(payload) == {
        "lake_id", "generalized_zone", "public_state", "observed_bucket", "published_at",
    }
    assert "battery" not in payload

    with pytest.raises(Exception):
        public_patrol_payload({**payload, "latitude": 47.6})


@pytest.mark.anyio
async def test_public_hub_broadcasts_only_validated_projection_payloads():
    class Client:
        sent = None

        async def send_json(self, payload):
            self.sent = payload

    client = Client()
    hub = lake_runtimes["lake-sammamish"].public_hub
    hub.clients.add(client)
    try:
        await publish_public_patrol_presence("lake-sammamish", {
            "lake_id": "lake-sammamish",
            "generalized_zone": "north basin",
            "public_state": "patrolling",
            "observed_bucket": "2026-07-30T12:00:00Z",
            "published_at": "2026-07-30T12:05:00Z",
        })
    finally:
        hub.clients.discard(client)

    assert set(client.sent) == {
        "lake_id", "generalized_zone", "public_state", "observed_bucket", "published_at",
    }


@pytest.mark.anyio
async def test_public_hub_rejects_fresh_patrol_presence_before_broadcast():
    class Client:
        sent = None

        async def send_json(self, payload):
            self.sent = payload

    client = Client()
    hub = lake_runtimes["lake-sammamish"].public_hub
    hub.clients.add(client)
    try:
        with pytest.raises(ValueError, match="at least five minutes"):
            await publish_public_patrol_presence("lake-sammamish", {
                "lake_id": "lake-sammamish",
                "generalized_zone": "north basin",
                "public_state": "patrolling",
                "observed_bucket": "2026-07-30T12:00:00Z",
                "published_at": "2026-07-30T12:00:00Z",
            })
    finally:
        hub.clients.discard(client)

    assert client.sent is None
