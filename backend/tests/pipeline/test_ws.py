import pytest
from fastapi.testclient import TestClient

from app.main import app
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
        with TestClient(app).websocket_connect("/ws/lakes/lake-sammamish/positions") as ws:
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
        with TestClient(app).websocket_connect("/ws/lakes/lake-sammamish/positions", subprotocols=["bearer.token"]) as ws:
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
    monkeypatch.setattr("app.main.get_access_repository", lambda: repository)
    monkeypatch.setattr("app.main.verify_supabase_jwt", lambda token: {"sub": "user", "aal": "aal2"})
    monkeypatch.setattr("app.main.WS_REVALIDATION_SECONDS", 0.0)
    with TestClient(app).websocket_connect("/ws/lakes/lake-sammamish/positions", subprotocols=["bearer.token"]) as ws:
        ws.receive_json()
        ws.send_text("keepalive")
        with pytest.raises(Exception) as error:
            ws.receive_json()
    assert getattr(error.value, "code", None) == 1008
