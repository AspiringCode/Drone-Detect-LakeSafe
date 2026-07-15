from __future__ import annotations

import asyncio
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.coordination.engine import SimulationEngine
from app.detection.detector import ThermalDetector
from app.detection.temporal import TemporalPersistenceFilter
from app.models import Detection, Drone, DroneStatus, LatLon
from app.pipeline.alerts import AlertRepository, InMemoryBackend, assemble_alert
from app.pipeline.ws import ConnectionHub, tick_loop
from app.risk_zones.heatmap import zones_to_geojson
from app.risk_zones.hybrid import compute_hybrid_zones
from app.risk_zones.scoring import compute_risk_zones

TICK_INTERVAL_S = 0.5

app = FastAPI(title="LakeSafe Initiative Demo API")

# Local-dev dashboard runs on Vite's default port; CAC judges run this locally,
# not behind a shared origin, so permissive localhost/127.0.0.1 dev ports are fine.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

zones = compute_hybrid_zones(grid_n=3, use_fixture=True)
drones = [
    Drone(f"d{i}", LatLon(47.579 + i * 0.0002, -122.091), 1.0, DroneStatus.IDLE, None)
    for i in range(5)
]
engine = SimulationEngine(drones, zones[:5], shore_stations=[])
alert_backend = InMemoryBackend()
alerts = AlertRepository(alert_backend)
hub = ConnectionHub()


def _jsonable(value):
    if is_dataclass(value):
        return {k: _jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def current_state() -> dict:
    return _jsonable(engine.step(0.1))


@app.get("/api/riskmap")
def get_riskmap():
    return zones_to_geojson(zones)


@app.get("/api/drones")
def get_drones():
    return current_state()


@app.get("/api/alerts")
def get_alerts():
    return _jsonable(alert_backend.list())


@app.post("/api/demo/trigger")
def demo_trigger():
    at = zones[0].centroid
    engine.trigger_detection(zones[0].zone_id, at=at)
    state = engine.step(30.0)
    drone = state["drones"][0]
    detected_at = datetime.now(timezone.utc)
    detection = Detection(0, (10.0, 10.0, 5.0, 5.0), 0.9, detected_at, source="simulated")
    alert = assemble_alert(detection, drone, confirmed=bool(state.get("confirmed")), clip_ref=None, detected_at=detected_at)
    alerts.save(alert)
    return _jsonable(alert)


@app.post("/api/alerts/{alert_id}/escalate")
def escalate_alert(alert_id: str):
    return {"alert_id": alert_id, "escalated": True}


@app.websocket("/ws/positions")
async def positions_ws(websocket: WebSocket):
    await hub.connect(websocket)
    try:
        await websocket.send_json(current_state())
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(websocket)


@app.on_event("startup")
async def _start_tick_loop() -> None:
    app.state.tick_task = asyncio.create_task(
        tick_loop(engine, hub, _jsonable, interval=TICK_INTERVAL_S)
    )


@app.on_event("shutdown")
async def _stop_tick_loop() -> None:
    task = getattr(app.state, "tick_task", None)
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
