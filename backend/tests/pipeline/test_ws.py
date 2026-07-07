import pytest

from app.pipeline.ws import ConnectionHub


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
