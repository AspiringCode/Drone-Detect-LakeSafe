"""Device-only endpoints.  These accept signed bytes before JSON exists."""

from __future__ import annotations

import json

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import ValidationError

from app.devices.auth import DeviceAuthenticationError, verify_device_request
from app.devices.heartbeat import HeartbeatService
from app.devices.acknowledgements import AcknowledgementService, AcknowledgementError
from app.devices.repository import DeviceRepositoryError, get_device_repository

router = APIRouter(prefix="/api/devices", tags=["real-devices"])


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
