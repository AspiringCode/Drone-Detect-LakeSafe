"""Narrow command transport interface.

Adapters own their transport boundary.  This phase exposes only the simulated
adapter; a real transport must be a separate implementation in a later phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.autonomy.outbox import CommandEnvelope


class TransportIsolationError(RuntimeError):
    """A command was offered to a transport that must not carry it."""


@dataclass(frozen=True)
class AdapterReceipt:
    inventory_id: str
    desired_state_version: int
    command_id: str | None


class FleetAdapter(Protocol):
    def publish(self, command: CommandEnvelope) -> AdapterReceipt: ...


__all__ = ["AdapterReceipt", "FleetAdapter", "TransportIsolationError"]
