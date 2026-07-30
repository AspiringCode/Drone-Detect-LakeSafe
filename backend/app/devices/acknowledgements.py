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
    def insert_acknowledgement(self, drone_id: str, command_id: str, sequence: int, plan_id: str | None, version: int, status: str, detail: str | None) -> bool: ...


class AcknowledgementService:
    def __init__(self, repository: AcknowledgementRepository) -> None:
        self._repository = repository

    def record(self, principal: DevicePrincipal, command_id: str, plan_id: str | None, desired_state_version: int, status: AckStatus, detail: str | None) -> None:
        if principal.sequence is None or status not in {"accepted", "rejected", "completed"}:
            raise AcknowledgementMismatch("invalid acknowledgement")
        command = self._repository.command_for_ack(command_id)
        if not isinstance(command, dict):
            raise AcknowledgementMismatch("unknown command")
        command_type = command.get("command_type", "apply_assignment")
        plan_matches = command.get("plan_id") == plan_id if command_type == "apply_assignment" else (command.get("plan_id") is None and plan_id is None)
        if (command.get("drone_id") != principal.drone_id or command.get("station_id") != principal.station_id
                or not plan_matches or command.get("desired_state_version") != desired_state_version
                or command_type not in {"apply_assignment", "return_to_reserve", "safety_hold"}):
            raise AcknowledgementMismatch("acknowledgement does not match command")
        if not self._repository.insert_acknowledgement(principal.drone_id, command_id, principal.sequence, plan_id, desired_state_version, status, detail):
            raise StaleAcknowledgement("duplicate or stale acknowledgement")
        # The repository records and (for accepted/completed status) advances
        # state in one transaction. Rejected commands never become active.
