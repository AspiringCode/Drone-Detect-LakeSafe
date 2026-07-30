"""Durable command envelope and publish worker boundary."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Protocol


CommandType = Literal["apply_assignment", "return_to_reserve", "safety_hold"]
CommandStatus = Literal["pending", "claimed", "acknowledged", "failed"]


class StaleDesiredState(RuntimeError):
    """A command attempts to move a drone's desired state backward."""


@dataclass(frozen=True)
class CommandEnvelope:
    idempotency_key: str
    inventory_id: str
    station_id: str
    lake_id: str
    desired_state_version: int
    command_type: CommandType
    assignment_id: str | None
    payload: dict
    command_id: str | None = None
    status: CommandStatus = "pending"

    def __post_init__(self) -> None:
        if self.desired_state_version < 1:
            raise ValueError("desired state versions start at one")
        if not self.idempotency_key:
            raise ValueError("commands require an idempotency key")
        if (self.command_type == "apply_assignment") != (self.assignment_id is not None):
            raise ValueError("apply_assignment commands require an assignment")


class OutboxRepository(Protocol):
    def claim_pending(self, limit: int) -> tuple[CommandEnvelope, ...]: ...
    def acknowledge(self, command_id: str) -> bool: ...
    def release(self, command_id: str) -> bool: ...


class OutboxPublisher:
    """Publishes only claimed rows; failed adapters return rows to pending."""

    def __init__(self, repository: OutboxRepository, adapter, *, batch_size: int = 20) -> None:
        self._repository = repository
        self._adapter = adapter
        self._batch_size = batch_size

    def publish_pending(self) -> tuple[str, ...]:
        acknowledged: list[str] = []
        for command in self._repository.claim_pending(self._batch_size):
            if not command.command_id:
                raise RuntimeError("claimed commands must have IDs")
            try:
                publish = getattr(self._adapter, "publish", self._adapter)
                receipt = publish(command)
            except Exception:
                self._repository.release(command.command_id)
                continue
            if getattr(receipt, "device_ack_required", False):
                # A real gateway merely accepted the network request. The
                # signed device acknowledgement endpoint owns activation.
                continue
            if self._repository.acknowledge(command.command_id):
                acknowledged.append(command.command_id)
        return tuple(acknowledged)


__all__ = ["CommandEnvelope", "OutboxPublisher", "StaleDesiredState"]
