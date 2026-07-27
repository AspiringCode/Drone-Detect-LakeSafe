from __future__ import annotations

import asyncio
from typing import Any, Callable


class ConnectionHub:
    def __init__(self) -> None:
        self.clients: set = set()

    async def connect(self, websocket, *, subprotocol: str | None = None) -> None:
        await websocket.accept(subprotocol=subprotocol)
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


async def tick_loop(
    engine: Any,
    hub: ConnectionHub,
    jsonify: Callable[[Any], Any],
    interval: float = 0.5,
    iterations: int | None = None,
) -> None:
    """Advance the simulation and broadcast state every `interval` seconds.

    `iterations=None` runs until cancelled (production, launched as a
    background task at app startup). A finite `iterations` lets tests drive
    a bounded, deterministic number of ticks without real-time sleeps mattering.
    """
    count = 0
    while iterations is None or count < iterations:
        state = engine.step(interval)
        await hub.broadcast(jsonify(state))
        count += 1
        if iterations is None or count < iterations:
            await asyncio.sleep(interval)
