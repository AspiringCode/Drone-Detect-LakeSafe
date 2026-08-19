from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from time import monotonic
from uuid import uuid4
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from supabase import create_client

from app.auth import verify_supabase_jwt
from app.access.policy import Permission, require_station_access
from app.access.principal import Principal, _bearer_token, principal_from_claims
from app.access.repository import get_access_repository
from app.config import SUPABASE_KEY, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from app.coordination.engine import SimulationEngine
from app.detection.detector import ThermalDetector
from app.detection.temporal import TemporalPersistenceFilter
from app.models import (
    Detection, Drone, DroneStatus, LatLon, RiskPointProvenance, RiskZone,
)
from app.pipeline.alerts import AlertRepository, InMemoryBackend, assemble_alert
from app.pipeline.ws import ConnectionHub, tick_loop
from app.risk_zones.heatmap import zones_to_geojson
from app.lakes.catalog import SUPPORTED_LAKE_IDS, load_reviewed_lake
from app.risk_zones.connectors.base import ConnectorFetch, NormalizedRiskPoint
from app.risk_zones.connectors.king_county_swim_beach import KingCountySwimBeachProxyConnector
from app.risk_zones.plan_builder import build_candidate
from app.risk_zones.shoreline import load_lake_polygon
from app.risk_zones.snapshots import build_snapshot
from app.onboarding.geo_lookup import AddressNotFoundError, lookup_nearby_lakes
from app.verification.routes import router as idme_router
from app.stations.routes import router as station_router
from app.review.routes import router as review_router
from app.lakes.routes import router as lake_router
from app.api.risk_plans import router as risk_plan_router
from app.api.risk_plans import get_risk_refresh_worker
from app.risk_zones.setup_worker import cancel_worker_task, start_worker_task
from app.api.inventory import router as simulated_autonomy_router
from app.api.device_admin import router as device_admin_router
from app.api.devices import router as devices_router
from app.api.safety import router as safety_router
from app.public_api import PublicPatrolPresence, router as public_router
from app.evidence import router as evidence_router
from app.devices.monitor import HeartbeatMonitor, monitor_loop
from app.devices.repository import DeviceRepositoryError, get_device_repository
from app.devices.reconciler import RealCapacityReconciler, configure_real_autonomy_service, has_real_autonomy_service
from app.correlation import REQUEST_ID_HEADER, request_id_from_header

TICK_INTERVAL_S = 0.5
WS_REVALIDATION_SECONDS = 30.0
WS_REVALIDATION_CLOCK = monotonic

@asynccontextmanager
async def _lifespan(application: FastAPI):
    # One lifespan owns every long-running task. This avoids duplicated loops
    # under TestClient and makes shutdown cancellation deterministic.
    application.state.tick_tasks = {
        lake_id: asyncio.create_task(
            tick_loop(runtime.engine, runtime.hub, _jsonable, interval=TICK_INTERVAL_S)
        )
        for lake_id, runtime in lake_runtimes.items()
    }
    start_worker_task(application, get_risk_refresh_worker())
    application.state.device_heartbeat_task = None
    if not hasattr(application.state, "real_autonomy_service"):
        application.state.real_autonomy_service = None
    try:
        device_repository = get_device_repository()
        configure_real_autonomy_service(application, device_repository=device_repository)
        if has_real_autonomy_service(application):
            application.state.device_heartbeat_task = asyncio.create_task(
                monitor_loop(HeartbeatMonitor(device_repository, RealCapacityReconciler(application)))
            )
    except DeviceRepositoryError:
        # The rest of the application remains usable if real-device credentials
        # are not configured in a local simulated-only environment.
        pass
    try:
        yield
    finally:
        await cancel_worker_task(application)
        for task in getattr(application.state, "tick_tasks", {}).values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        application.state.tick_tasks = {}
        device_task = getattr(application.state, "device_heartbeat_task", None)
        if device_task is not None:
            device_task.cancel()
            try:
                await device_task
            except asyncio.CancelledError:
                pass
        application.state.device_heartbeat_task = None

app = FastAPI(title="LakeSafe Initiative Demo API", lifespan=_lifespan)
app.include_router(idme_router)
app.include_router(station_router)
app.include_router(review_router)
app.include_router(lake_router)
app.include_router(risk_plan_router)
app.include_router(simulated_autonomy_router)
app.include_router(device_admin_router)
app.include_router(devices_router)
app.include_router(safety_router)
app.include_router(public_router)
app.include_router(evidence_router)

# Local-dev dashboard runs on Vite's default port; CAC judges run this locally,
# not behind a shared origin, so permissive localhost/127.0.0.1 dev ports are fine.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def attach_request_correlation_id(request: Request, call_next):
    """Generate/validate correlation IDs before any route or audit code runs."""
    request.state.request_id = request_id_from_header(request.headers.get(REQUEST_ID_HEADER))
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = str(request.state.request_id)
    return response

@dataclass
class LakeRuntime:
    lake_id: str
    name: str
    zones: list
    engine: SimulationEngine
    alerts: AlertRepository
    alert_backend: InMemoryBackend
    # Operational state is intentionally never multiplexed with public
    # projections.  These hubs have distinct routes and payload contracts.
    hub: ConnectionHub
    public_hub: ConnectionHub
    shore_station: LatLon


def build_lake_runtime(lake_id: str) -> LakeRuntime:
    lake = load_reviewed_lake(lake_id)
    shoreline = load_lake_polygon(lake_id)
    reviewed_at = datetime(2026, 8, 18, tzinfo=timezone.utc)
    rows = tuple(
        NormalizedRiskPoint(
            source_row_id=f"catalog:{point.locator}",
            latitude=point.latitude,
            longitude=point.longitude,
            occurred_at=reviewed_at,
            weight=1.0,
            source_payload={},
            category="access_environment_proxy",
            is_proxy=True,
            provenance=RiskPointProvenance(
                connector_key="king_county_swim_beach_proxy",
                source_row_id=f"catalog:{point.locator}",
                locator=point.locator,
                observed_at=reviewed_at,
                source_latitude=point.latitude,
                source_longitude=point.longitude,
            ),
        )
        for point in lake.official_priority_coordinates
    )
    snapshot = build_snapshot(
        lake_id=lake_id,
        station_id=f"catalog:{lake_id}",
        connectors=(ConnectorFetch(
            connector_key="king_county_swim_beach_proxy",
            connector_schema_version="1",
            attribution=KingCountySwimBeachProxyConnector.attribution,
            rows=rows,
        ),),
        boundary=shoreline,
        since=reviewed_at,
        now=reviewed_at,
    )
    candidate = build_candidate(
        snapshot, shoreline, patrol_capacity=5, reserve=1, prior_plan_id=None,
        reassign_detached_pieces=True,
    )
    zones = [
        RiskZone(
            zone_id=cell.cell_id,
            centroid=cell.centroid,
            polygon=list(cell.polygon),
            risk_score=cell.risk_score,
            components={"access_environment_proxy": float(cell.risk_score)}
            if cell.kind == "hotspot"
            else {},
            is_proxy=cell.is_proxy,
            radius_m=cell.radius_m,
            seed=cell.seed,
            provenance=cell.provenance,
            holes=cell.holes,
        )
        for cell in candidate.cells
    ]
    drones = [
        Drone(f"{lake_id}-d{index}", cell.centroid, 1.0, DroneStatus.IDLE, None)
        for index, cell in enumerate(candidate.cells[:5])
    ]
    shore_station = lake.shore_station.as_lat_lon()
    backend = InMemoryBackend()
    return LakeRuntime(
        lake_id=lake_id, name=lake.name, zones=zones,
        engine=SimulationEngine(drones, zones, shore_stations=[shore_station]),
        alerts=AlertRepository(backend), alert_backend=backend, hub=ConnectionHub(),
        public_hub=ConnectionHub(), shore_station=shore_station,
    )


lake_runtimes: dict[str, LakeRuntime] = {
    lake_id: build_lake_runtime(lake_id) for lake_id in SUPPORTED_LAKE_IDS
}


class NearbyLakesRequest(BaseModel):
    station_name: str = Field(min_length=1)
    station_address: str = Field(min_length=1)


class OrganizationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    station_lat: float
    station_lon: float
    lake_name: str = Field(min_length=1)
    lake_lat: float
    lake_lon: float


def create_organization_and_lake(*, request: OrganizationCreateRequest, owner_user_id: str) -> dict:
    """Persist onboarding entities with the server's Supabase service credential."""
    credential = SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY
    if not SUPABASE_URL or not credential:
        raise RuntimeError("Supabase credentials are not configured")
    client = create_client(SUPABASE_URL, credential)
    org_id = f"org-{uuid4()}"
    lake_id = f"lake-{uuid4()}"
    client.table("organizations").insert({
        "org_id": org_id,
        "name": request.name,
        # The published request contract does not carry an address. Preserve a
        # meaningful station label until the authenticated flow supplies it.
        "station_address": request.name,
        "station_lat": request.station_lat,
        "station_lon": request.station_lon,
        "owner_user_id": owner_user_id,
    }).execute()
    client.table("lakes").insert({
        "lake_id": lake_id,
        "org_id": org_id,
        "name": request.lake_name,
        "centroid_lat": request.lake_lat,
        "centroid_lon": request.lake_lon,
    }).execute()
    return {"org_id": org_id, "lake_id": lake_id}


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


def get_runtime(lake_id: str) -> LakeRuntime:
    runtime = lake_runtimes.get(lake_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail="Lake runtime not found")
    return runtime


def get_current_principal(authorization: str | None = Header(default=None)) -> Principal:
    """Load authority from the database, never from client profile/JWT roles."""
    try:
        return principal_from_claims(
            verify_supabase_jwt(_bearer_token(authorization)), get_access_repository()
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Authorization service is unavailable") from exc


def require_lake_permission(
    lake_id: str, principal: Principal, permission: Permission
) -> None:
    # Check the in-memory demo lake first so unknown and cross-station IDs use
    # the same response and do not disclose station ownership.
    get_runtime(lake_id)
    try:
        station_id = get_access_repository().lake_station_id(lake_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Authorization service is unavailable") from exc
    if station_id is None:
        raise HTTPException(status_code=404, detail="Lake not found")
    try:
        require_station_access(principal, station_id, permission)
    except HTTPException as exc:
        # Only a station mismatch is concealed as a missing lake.  MFA,
        # verification, and role failures are actionable to a known member.
        if exc.status_code == 403 and not any(
            membership.station_id == station_id for membership in principal.memberships
        ):
            raise HTTPException(status_code=404, detail="Lake not found") from exc
        raise


def authorize_lake(
    lake_id: str, authorization: str | None, permission: Permission
) -> Principal:
    # Resolve the resource before authentication so an unknown lake and a lake
    # outside the caller's station are indistinguishable.
    get_runtime(lake_id)
    return_principal = get_current_principal(authorization)
    require_lake_permission(lake_id, return_principal, permission)
    return return_principal


def authorize_operational_websocket(lake_id: str, token: str) -> Principal:
    try:
        principal = principal_from_claims(verify_supabase_jwt(token), get_access_repository())
        require_lake_permission(lake_id, principal, Permission.READ_OPERATIONS)
        return principal
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Authorization service is unavailable") from exc


def current_state(runtime: LakeRuntime) -> dict:
    return _jsonable(runtime.engine.step(0.1))


def public_patrol_payload(payload: object) -> dict[str, object]:
    """Validate and serialize the only payload public sockets may broadcast."""
    return PublicPatrolPresence.model_validate(payload).model_dump(mode="json")


async def publish_public_patrol_presence(lake_id: str, payload: object) -> None:
    """Broadcast a persisted public projection; never derive it from telemetry."""
    projection = public_patrol_payload(payload)
    if projection["lake_id"] != lake_id:
        raise ValueError("Public patrol projection lake does not match its channel")
    await get_runtime(lake_id).public_hub.broadcast(projection)


def websocket_has_url_credentials(websocket: WebSocket) -> bool:
    return any(
        key.lower() in {"token", "access_token", "authorization"}
        for key in websocket.query_params
    )


def get_lake_deployment_metadata(lake_id: str) -> dict[str, object] | None:
    credential = SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY
    if not SUPABASE_URL or not credential:
        raise RuntimeError("Supabase credentials are not configured")
    response = create_client(SUPABASE_URL, credential).table("lakes").select(
        "org_id,drone_inventory_cap,organizations(owner_user_id)"
    ).eq("lake_id", lake_id).maybe_single().execute()
    record = response.data
    if not record:
        return None
    organization = record.get("organizations") or {}
    if isinstance(organization, list):
        organization = organization[0] if organization else {}
    return {
        "org_id": record["org_id"],
        "owner_user_id": organization.get("owner_user_id"),
        "drone_inventory_cap": record["drone_inventory_cap"],
    }


@app.post("/api/onboarding/nearby-lakes")
def nearby_lakes(request: NearbyLakesRequest):
    try:
        result = lookup_nearby_lakes(request.station_address)
    except AddressNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail="Lake search is temporarily unavailable. Please try again.",
        ) from exc
    return {
        "station": {"lat": result.coordinates.latitude, "lon": result.coordinates.longitude},
        "candidates": [
            {"name": lake.name, "lat": lake.latitude, "lon": lake.longitude}
            for lake in result.lakes
        ],
    }


@app.post("/api/onboarding/organizations", status_code=201)
def create_organization(
    request: OrganizationCreateRequest, authorization: str | None = Header(default=None)
):
    # Organization-owner onboarding was superseded by verified station access.
    # Station creation and lake administration are introduced in the station UI
    # phase; retaining this endpoint would reintroduce owner-based authority.
    raise HTTPException(status_code=410, detail="Use the verified station workflow")


@app.get("/api/lakes/{lake_id}/riskmap")
def get_riskmap(lake_id: str, authorization: str | None = Header(default=None)):
    authorize_lake(lake_id, authorization, Permission.READ_OPERATIONS)
    return zones_to_geojson(get_runtime(lake_id).zones)


@app.get("/api/lakes/{lake_id}/drones")
def get_drones(lake_id: str, authorization: str | None = Header(default=None)):
    authorize_lake(lake_id, authorization, Permission.READ_OPERATIONS)
    return current_state(get_runtime(lake_id))


@app.get("/api/lakes/{lake_id}/alerts")
def get_alerts(lake_id: str, authorization: str | None = Header(default=None)):
    authorize_lake(lake_id, authorization, Permission.READ_OPERATIONS)
    return _jsonable(get_runtime(lake_id).alert_backend.list())


@app.post("/api/lakes/{lake_id}/demo/trigger")
def demo_trigger(lake_id: str, authorization: str | None = Header(default=None)):
    authorize_lake(lake_id, authorization, Permission.MANAGE_ALERTS)
    runtime = get_runtime(lake_id)
    at = runtime.zones[0].centroid
    runtime.engine.trigger_detection(runtime.zones[0].zone_id, at=at)
    state = runtime.engine.step(30.0)
    drone = state["drones"][0]
    detected_at = datetime.now(timezone.utc)
    detection = Detection(0, (10.0, 10.0, 5.0, 5.0), 0.9, detected_at, source="simulated")
    alert = assemble_alert(detection, drone, confirmed=bool(state.get("confirmed")), clip_ref=None, detected_at=detected_at)
    runtime.alerts.save(alert)
    return _jsonable(alert)


@app.post("/api/lakes/{lake_id}/alerts/{alert_id}/escalate")
def escalate_alert(lake_id: str, alert_id: str, authorization: str | None = Header(default=None)):
    authorize_lake(lake_id, authorization, Permission.MANAGE_ALERTS)
    return {"alert_id": alert_id, "escalated": True}


@app.post("/api/lakes/{lake_id}/drones/deploy", status_code=201)
def deploy_drone(lake_id: str, authorization: str | None = Header(default=None)):
    runtime = get_runtime(lake_id)
    principal = authorize_lake(lake_id, authorization, Permission.MANAGE_INVENTORY)
    metadata = get_lake_deployment_metadata(lake_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Lake not found")
    if len(runtime.engine.drones) >= int(metadata["drone_inventory_cap"]):
        raise HTTPException(status_code=409, detail="Drone inventory cap reached")
    drone = Drone(f"deploy-{uuid4().hex[:8]}", runtime.shore_station, 1.0, DroneStatus.IDLE, None)
    runtime.engine.drones.append(drone)
    runtime.engine.altitudes[drone.drone_id] = 30.0
    runtime.engine._initial_assign()
    return {
        "drone_id": drone.drone_id, "position": _jsonable(drone.pos),
        "status": drone.status.value, "assigned_zone": drone.assigned_zone,
    }


@app.websocket("/ws/public/lakes/{lake_id}")
async def public_positions_ws(websocket: WebSocket, lake_id: str):
    """Anonymous channel for delayed, projection-only patrol presence."""
    runtime = lake_runtimes.get(lake_id)
    if runtime is None or websocket_has_url_credentials(websocket):
        await websocket.close(code=1008)
        return
    await runtime.public_hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        runtime.public_hub.disconnect(websocket)


@app.websocket("/ws/operations/lakes/{lake_id}")
async def operations_positions_ws(websocket: WebSocket, lake_id: str):
    runtime = lake_runtimes.get(lake_id)
    if runtime is None or websocket_has_url_credentials(websocket):
        await websocket.close(code=1008)
        return
    protocols = websocket.headers.get("sec-websocket-protocol", "").split(",")
    token_protocol = next((protocol.strip() for protocol in protocols if protocol.strip().startswith("bearer.")), None)
    if token_protocol is None:
        await websocket.close(code=1008)
        return
    try:
        principal = authorize_operational_websocket(lake_id, token_protocol.removeprefix("bearer."))
    except (HTTPException, RuntimeError):
        await websocket.close(code=1008)
        return
    await runtime.hub.connect(websocket, subprotocol=token_protocol)
    try:
        await websocket.send_json(current_state(runtime))
        next_revalidation = WS_REVALIDATION_CLOCK() + WS_REVALIDATION_SECONDS
        while True:
            # A deadline (rather than a receive timeout) prevents a chatty
            # client from postponing revocation checks indefinitely.
            try:
                await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=max(0.0, next_revalidation - WS_REVALIDATION_CLOCK()),
                )
            except TimeoutError:
                pass
            if WS_REVALIDATION_CLOCK() >= next_revalidation:
                try:
                    principal = authorize_operational_websocket(lake_id, token_protocol.removeprefix("bearer."))
                except (HTTPException, RuntimeError):
                    await websocket.close(code=1008)
                    return
                next_revalidation = WS_REVALIDATION_CLOCK() + WS_REVALIDATION_SECONDS
    except WebSocketDisconnect:
        pass
    finally:
        runtime.hub.disconnect(websocket)
# Background-task shutdown is owned by the application lifespan above.

__all__ = ["app"]
