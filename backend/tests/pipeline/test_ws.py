import pytest

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
