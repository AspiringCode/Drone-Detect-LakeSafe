from __future__ import annotations


class ConnectionHub:
    def __init__(self) -> None:
        self.clients: set = set()

    async def connect(self, websocket) -> None:
        await websocket.accept()
        self.clients.add(websocket)

    def disconnect(self, websocket) -> None:
        self.clients.discard(websocket)

    async def broadcast(self, state: dict) -> None:
        stale = []
        for client in list(self.clients):
            try:
                await client.send_json(state)
            except Exception:
                stale.append(client)
        for client in stale:
            self.disconnect(client)
