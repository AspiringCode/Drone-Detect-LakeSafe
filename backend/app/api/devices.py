"""Device-only endpoints.  These accept signed bytes before JSON exists."""

from __future__ import annotations

import json

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import ValidationError

from app.devices.auth import DeviceAuthenticationError, verify_device_request
from app.devices.heartbeat import HeartbeatService
from app.devices.repository import DeviceRepositoryError, get_device_repository

router = APIRouter(prefix="/api/devices", tags=["real-devices"])


class _RepositoryReconciler:
    """Capacity reconciliation hook installed by the real-autonomy worker."""
    def __init__(self, repository) -> None:
        self._repository = repository

    def reconcile_lake(self, lake_id: str, trigger: str, expected_plan_id=None) -> None:
        # Task 3 installs the real command transport beneath this worker.  Do
        # not enqueue from a claimed job: that would turn one transition into
        # a self-perpetuating queue.
        self._repository.reconcile_real_capacity(lake_id, trigger)


def get_heartbeat_autonomy(repository):
    return _RepositoryReconciler(repository)


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
        HeartbeatService(repository, get_heartbeat_autonomy(repository)).record(principal, payload)
    except (json.JSONDecodeError, ValidationError, DeviceRepositoryError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Heartbeat payload is invalid") from exc
    return {"received_sequence": sequence}
