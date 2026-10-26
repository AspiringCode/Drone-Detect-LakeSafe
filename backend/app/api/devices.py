"""Device-only endpoints.  These accept signed bytes before JSON exists."""

from __future__ import annotations

import json
import logging
from datetime import datetime,timezone

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from app.devices import live_alerts, live_commands
from app.devices.auth import DeviceAuthenticationError, verify_device_request
from app.devices.heartbeat import HeartbeatService, Position
from app.devices.acknowledgements import AcknowledgementService, AcknowledgementError
from app.devices.repository import DeviceRepositoryError, get_device_repository
from app.devices.patrol_repository import get_patrol_repository
from app.devices.investigations import get_investigation_repository
from app.devices import live_positions
from app.models import Detection, Drone, DroneStatus, LatLon
from app.pipeline.alerts import assemble_alert

router = APIRouter(prefix="/api/devices", tags=["real-devices"])
logger = logging.getLogger(__name__)


class DetectionPayload(BaseModel):
    """A drone-confirmed thermal person detection; position is required because an alert without one is useless."""

    model_config = ConfigDict(extra="forbid")
    confidence: float = Field(ge=0, le=1)
    bbox: tuple[float, float, float, float]
    detected_at: AwareDatetime
    position: Position


@router.post("/{drone_id}/heartbeat", status_code=status.HTTP_202_ACCEPTED)
async def heartbeat(
    drone_id: str,
    request: Request,
    x_device_timestamp: str | None = Header(default=None),
    x_device_sequence: str | None = Header(default=None),
    x_device_signature: str | None = Header(default=None),
) -> dict:
    raw_body = await request.body()
    try:
        if x_device_sequence is None or not x_device_sequence.isascii() or not x_device_sequence.isdecimal():
            raise DeviceAuthenticationError()
        sequence = int(x_device_sequence)
        # Signature/replay validation must happen before content parsing.
        repository = get_device_repository()
        principal = verify_device_request(drone_id, x_device_timestamp, sequence, x_device_signature, raw_body, repository, claim_sequence=False)
    except (DeviceAuthenticationError, DeviceRepositoryError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Device authentication failed") from exc
    try:
        payload = json.loads(raw_body)
        HeartbeatService(repository).record(principal, payload)
    except (json.JSONDecodeError, ValidationError, DeviceRepositoryError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Heartbeat payload is invalid") from exc
    try:
        patrols = get_patrol_repository().pending(principal)
        commands = []
        for command in patrols:
            try:
                from app.api.device_admin import MissionRequest, _assigned_drone, prepare_mission
                drone = _assigned_drone(principal.station_id, principal.drone_id)
                _, _, _, fingerprint = prepare_mission(principal.station_id, drone, MissionRequest(
                    zone_id=command["zone_id"], home_lat=command["home"]["lat"],
                    home_lon=command["home"]["lon"], altitude_m=command["altitude_m"],
                ))
                if fingerprint != command["mission_hash"]:
                    raise ValueError("mission changed")
            except (HTTPException, ValueError, KeyError, TypeError):
                get_patrol_repository().reject(principal, command["command_id"], "Mission layout or drone assignment changed; review again")
                continue
            commands.append(command)
    except DeviceRepositoryError as exc:
        raise HTTPException(503, "Patrol delivery is unavailable") from exc
    try:
        investigations = get_investigation_repository().pending(principal)
    except DeviceRepositoryError as exc:
        raise HTTPException(503, 'Investigation delivery is unavailable') from exc
    # Safety outbox commands take precedence over patrol/investigation intents.
    safety_commands = live_commands.pending(principal.drone_id)
    return {"received_sequence": sequence, "commands": safety_commands or [*commands, *investigations]}


@router.post("/{drone_id}/detections", status_code=status.HTTP_202_ACCEPTED)
async def report_detection(
    drone_id: str,
    request: Request,
    x_device_timestamp: str | None = Header(default=None),
    x_device_sequence: str | None = Header(default=None),
    x_device_signature: str | None = Header(default=None),
) -> dict:
    raw_body = await request.body()
    try:
        if x_device_sequence is None or not x_device_sequence.isascii() or not x_device_sequence.isdecimal():
            raise DeviceAuthenticationError()
        sequence = int(x_device_sequence)
        repository = get_device_repository()
        # No database RPC consumes the sequence here, so claim it during verification.
        principal = verify_device_request(drone_id, x_device_timestamp, sequence, x_device_signature, raw_body, repository, claim_sequence=True)
    except (DeviceAuthenticationError, DeviceRepositoryError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Device authentication failed") from exc
    try:
        payload = DetectionPayload.model_validate_json(raw_body)
        if abs((datetime.now(timezone.utc)-payload.detected_at).total_seconds())>30:
            raise ValueError('Detection is stale')
    except (ValidationError,ValueError) as exc:
        raise HTTPException(status_code=422, detail="Detection payload is invalid") from exc
    try:
        inventory = repository.real_inventory(principal.drone_id)
    except DeviceRepositoryError as exc:
        raise HTTPException(status_code=503, detail="Device gateway is unavailable") from exc
    lake_id = inventory.get("lake_id") if isinstance(inventory, dict) else None
    if not isinstance(lake_id, str):
        raise HTTPException(status_code=409, detail="Drone is not attached to a lake")
    detection = Detection(0, payload.bbox, payload.confidence, payload.detected_at, source="real")
    drone = Drone(principal.drone_id, LatLon(payload.position.lat, payload.position.lon), 0.0, DroneStatus.INVESTIGATING, None, source="real")
    # The drone's persistence filter already confirmed it; operational alerts only, never the public feed.
    alert = assemble_alert(detection, drone, confirmed=False, clip_ref=None, detected_at=payload.detected_at)
    persisted = True
    try:
        repository.save_real_alert(principal.station_id, lake_id, alert)
    except DeviceRepositoryError:
        # A person in the water outranks the audit trail: still show it live, but say it was not saved.
        persisted = False
        logger.warning("real alert %s for lake %s was shown live but not saved", alert.alert_id, lake_id)
    live_alerts.record(lake_id, alert)
    if persisted:
        try:
            get_investigation_repository().begin(lake_id,alert,live_positions.snapshot(lake_id))
        except DeviceRepositoryError:
            logger.warning('Investigation could not be started for alert %s', alert.alert_id)
    return {"received_sequence": sequence, "alert_id": alert.alert_id, "persisted": persisted}


class InvestigationAcknowledgement(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: str = Field(pattern='^(accepted|rejected)$')
    detail: str | None = Field(default=None,max_length=500)


@router.post('/{drone_id}/investigation-commands/{command_id}/acknowledgements',status_code=202)
async def acknowledge_investigation(drone_id: str,command_id: str,request: Request,
    x_device_timestamp: str | None=Header(default=None),x_device_sequence: str | None=Header(default=None),
    x_device_signature: str | None=Header(default=None)):
    raw = await request.body()
    try:
        if x_device_sequence is None or not x_device_sequence.isascii() or not x_device_sequence.isdecimal():
            raise DeviceAuthenticationError()
        principal = verify_device_request(drone_id,x_device_timestamp,int(x_device_sequence),x_device_signature,raw,
            get_device_repository(),claim_sequence=False)
    except (DeviceAuthenticationError,DeviceRepositoryError,TypeError,ValueError) as exc:
        raise HTTPException(401,'Device authentication failed') from exc
    try:
        value=InvestigationAcknowledgement.model_validate_json(raw)
        if not get_investigation_repository().acknowledge(principal,command_id,value.status,value.detail):
            raise ValueError('Invalid acknowledgement')
    except (ValidationError,ValueError,DeviceRepositoryError) as exc:
        raise HTTPException(422,'Investigation acknowledgement is invalid') from exc
    return {'received_sequence':principal.sequence}


@router.post("/{drone_id}/commands/{command_id}/acknowledgements", status_code=status.HTTP_202_ACCEPTED)
async def acknowledge_command(
    drone_id: str, command_id: str, request: Request,
    x_device_timestamp: str | None = Header(default=None),
    x_device_sequence: str | None = Header(default=None),
    x_device_signature: str | None = Header(default=None),
) -> dict:
    raw_body = await request.body()
    try:
        if x_device_sequence is None or not x_device_sequence.isascii() or not x_device_sequence.isdecimal():
            raise DeviceAuthenticationError()
        sequence = int(x_device_sequence)
        repository = get_device_repository()
        # Authenticate the raw bytes before parsing. Sequence consumption is
        # atomic with acknowledgement insertion in the database RPC.
        principal = verify_device_request(drone_id, x_device_timestamp, sequence, x_device_signature, raw_body, repository, claim_sequence=False)
    except (DeviceAuthenticationError, DeviceRepositoryError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Device authentication failed") from exc
    try:
        payload = json.loads(raw_body)
        AcknowledgementService(repository).record(principal, command_id, payload.get("plan_id"), payload["desired_state_version"], payload["status"], payload.get("detail"))
    except (json.JSONDecodeError, KeyError, TypeError, ValidationError, ValueError, AcknowledgementError, DeviceRepositoryError) as exc:
        raise HTTPException(status_code=422, detail="Acknowledgement payload is invalid") from exc
    live_commands.discard(principal.drone_id, command_id)
    return {"received_sequence": sequence}


class PatrolAcknowledgement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=1, max_length=120)
    status: str = Field(pattern=r"^(accepted|rejected)$")
    detail: str | None = Field(default=None, max_length=500)


@router.post("/{drone_id}/patrol-commands/{command_id}/acknowledgements", status_code=status.HTTP_202_ACCEPTED)
async def acknowledge_patrol(
    drone_id: str, command_id: str, request: Request,
    x_device_timestamp: str | None = Header(default=None),
    x_device_sequence: str | None = Header(default=None),
    x_device_signature: str | None = Header(default=None),
) -> dict:
    raw_body = await request.body()
    try:
        if x_device_sequence is None or not x_device_sequence.isascii() or not x_device_sequence.isdecimal():
            raise DeviceAuthenticationError()
        sequence = int(x_device_sequence)
        principal = verify_device_request(drone_id, x_device_timestamp, sequence, x_device_signature,
            raw_body, get_device_repository(), claim_sequence=False)
    except (DeviceAuthenticationError, DeviceRepositoryError, TypeError, ValueError) as exc:
        raise HTTPException(401, "Device authentication failed") from exc
    try:
        value = PatrolAcknowledgement.model_validate_json(raw_body)
    except ValidationError as exc:
        raise HTTPException(422, "Patrol acknowledgement payload is invalid") from exc
    if value.command_id != command_id:
        raise HTTPException(422, "Signed command does not match the acknowledgement path")
    try:
        saved = get_patrol_repository().acknowledge(principal, command_id, value.status, value.detail)
    except DeviceRepositoryError as exc:
        raise HTTPException(503, "Patrol acknowledgement could not be saved") from exc
    if not saved:
        raise HTTPException(409, "Patrol acknowledgement is stale, expired or does not match the drone")
    return {"received_sequence": sequence}
