"""Device-only endpoints.  These accept signed bytes before JSON exists."""

from __future__ import annotations

import json

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from app.devices import live_alerts
from app.devices.auth import DeviceAuthenticationError, verify_device_request
from app.devices.heartbeat import HeartbeatService, Position
from app.devices.acknowledgements import AcknowledgementService, AcknowledgementError
from app.devices.repository import DeviceRepositoryError, get_device_repository
from app.models import Detection, Drone, DroneStatus, LatLon
from app.pipeline.alerts import assemble_alert

router = APIRouter(prefix="/api/devices", tags=["real-devices"])


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
    return {"received_sequence": sequence}


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
    except ValidationError as exc:
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
    alert = assemble_alert(detection, drone, confirmed=True, clip_ref=None, detected_at=payload.detected_at)
    live_alerts.record(lake_id, alert)
    return {"received_sequence": sequence, "alert_id": alert.alert_id}


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
    return {"received_sequence": sequence}
