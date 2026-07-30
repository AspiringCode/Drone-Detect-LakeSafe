"""Isolated, server-only transport for authenticated real-device commands."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Protocol

from app.autonomy.adapters.base import AdapterReceipt, TransportIsolationError
from app.autonomy.outbox import CommandEnvelope
from app.hardware_gateway import HmacGatewaySigner


class RealInventoryRepository(Protocol):
    def real_inventory(self, drone_id: str) -> dict | None: ...


class RealAdapter:
    def __init__(self, repository: RealInventoryRepository, gateway, *, gateway_url: str, signing_key_ref: str) -> None:
        if not gateway_url:
            raise ValueError("real gateway URL is not configured")
        self._repository, self._gateway, self._gateway_url = repository, gateway, gateway_url
        self._signer = HmacGatewaySigner(signing_key_ref)

    def publish(self, command: CommandEnvelope) -> AdapterReceipt:
        if command.payload.get("source") != "real":
            raise TransportIsolationError("real transport accepts real command envelopes only")
        inventory = self._repository.real_inventory(command.inventory_id)
        if not isinstance(inventory, dict) or inventory.get("source") != "real":
            raise TransportIsolationError("real transport requires real inventory")
        if inventory.get("credential_state") != "active" or inventory.get("station_id") != command.station_id or inventory.get("lake_id") != command.lake_id:
            raise TransportIsolationError("real command does not match active station-owned inventory")
        expires_at = command.payload.get("expires_at")
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        except ValueError as exc:
            raise TransportIsolationError("real command envelope requires expiry") from exc
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise TransportIsolationError("real command envelope has expired")
        payload = json.dumps({
            "command_id": command.command_id, "drone_id": command.inventory_id,
            "station_id": command.station_id, "lake_id": command.lake_id,
            "desired_state_version": command.desired_state_version,
            "command_type": command.command_type, "payload": command.payload,
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self._gateway.publish(self._gateway_url, payload, self._signer.sign(payload))
        # Gateway acceptance means published only; the device acknowledgement
        # endpoint performs the authoritative active-state transition.
        return AdapterReceipt(command.inventory_id, command.desired_state_version, command.command_id, device_ack_required=True)


__all__ = ["RealAdapter", "TransportIsolationError"]
