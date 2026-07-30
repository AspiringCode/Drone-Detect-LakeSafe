"""Ordered device acknowledgement validation, with no manual flight surface."""

from __future__ import annotations

from typing import Literal, Protocol

from app.devices.auth import DevicePrincipal


class AcknowledgementError(RuntimeError): pass
class AcknowledgementMismatch(AcknowledgementError): pass
class StaleAcknowledgement(AcknowledgementError): pass

AckStatus = Literal["accepted", "rejected", "completed"]


class AcknowledgementRepository(Protocol):
    def command_for_ack(self, command_id: str) -> dict | None: ...
    def insert_acknowledgement(self, drone_id: str, command_id: str, sequence: int, status: str, detail: str | None) -> bool: ...
    def advance_acknowledged_version(self, drone_id: str, version: int, command_id: str) -> bool: ...


class AcknowledgementService:
    def __init__(self, repository: AcknowledgementRepository) -> None:
        self._repository = repository

    def record(self, principal: DevicePrincipal, command_id: str, plan_id: str, desired_state_version: int, status: AckStatus, detail: str | None) -> None:
        if principal.sequence is None or status not in {"accepted", "rejected", "completed"}:
            raise AcknowledgementMismatch("invalid acknowledgement")
        command = self._repository.command_for_ack(command_id)
        if not isinstance(command, dict):
            raise AcknowledgementMismatch("unknown command")
        if (command.get("drone_id") != principal.drone_id or command.get("station_id") != principal.station_id
                or command.get("plan_id") != plan_id or command.get("desired_state_version") != desired_state_version):
            raise AcknowledgementMismatch("acknowledgement does not match command")
        if not self._repository.insert_acknowledgement(principal.drone_id, command_id, principal.sequence, status, detail):
            raise StaleAcknowledgement("duplicate or stale acknowledgement")
        # Rejected command is recorded but never becomes active.  Accepted and
        # completed states advance only through a monotonic database update.
        if status in {"accepted", "completed"} and not self._repository.advance_acknowledged_version(principal.drone_id, desired_state_version, command_id):
            raise StaleAcknowledgement("acknowledged state cannot move backward")

