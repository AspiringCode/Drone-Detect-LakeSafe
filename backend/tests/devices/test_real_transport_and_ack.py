from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.autonomy.outbox import CommandEnvelope
from app.devices.auth import DevicePrincipal, canonical_request_bytes


def command_for(*, source: str = "real", version: int = 5) -> CommandEnvelope:
    return CommandEnvelope(
        "key-5", "d1", "station-1", "lake-1", version, "apply_assignment", "a1",
        {"source": source, "plan_id": "p2", "zone_plan_cell_id": "cell-1", "expires_at": "2099-01-01T00:00:00Z"},
        "c5", "pending",
    )


class Gateway:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def publish(self, url: str, payload: bytes, signature: str) -> None:
        self.calls.append({"url": url, "payload": payload, "signature": signature})


class Inventory:
    def __init__(self) -> None:
        self.rows = {"d1": {"source": "real", "station_id": "station-1", "lake_id": "lake-1", "credential_state": "active"}}

    def real_inventory(self, drone_id: str):
        return self.rows.get(drone_id)


def test_real_adapter_rejects_simulated_inventory():
    from app.autonomy.adapters.real import RealAdapter, TransportIsolationError

    gateway = Gateway()
    adapter = RealAdapter(Inventory(), gateway, gateway_url="https://gateway.test", signing_key_ref="test-signing-key")
    with pytest.raises(TransportIsolationError):
        adapter.publish(command_for(source="simulated"))
    assert gateway.calls == []


def test_real_adapter_signs_and_publishes_real_command_only():
    from app.autonomy.adapters.real import RealAdapter

    gateway = Gateway()
    adapter = RealAdapter(Inventory(), gateway, gateway_url="https://gateway.test", signing_key_ref="test-signing-key")
    receipt = adapter.publish(command_for())
    assert receipt.command_id == "c5"
    assert gateway.calls[0]["url"] == "https://gateway.test"
    assert json.loads(gateway.calls[0]["payload"])["command_id"] == "c5"
    assert gateway.calls[0]["signature"]


def test_real_transport_publish_does_not_acknowledge_outbox_state():
    from app.autonomy.adapters.real import RealAdapter
    from app.autonomy.outbox import OutboxPublisher
    from app.autonomy.repository import InMemoryAutonomyRepository

    repository, gateway = InMemoryAutonomyRepository(station_id="station-1"), Gateway()
    repository.enqueue(command_for())
    publisher = OutboxPublisher(repository, RealAdapter(Inventory(), gateway, gateway_url="https://gateway.test", signing_key_ref="test-signing-key"))
    assert publisher.publish_pending() == ()
    assert len(gateway.calls) == 1
    assert repository.acknowledged_version("d1") == 0


class AckRepository:
    def __init__(self) -> None:
        self.acks: list[tuple] = []
        self.versions: dict[str, int] = {}
        self.sequences: set[int] = set()

    def command_for_ack(self, command_id: str):
        if command_id == "c4":
            return {"command_id": command_id, "drone_id": "d1", "station_id": "station-1", "lake_id": "lake-1", "plan_id": "p1", "desired_state_version": 4, "status": "claimed"}
        return {"command_id": command_id, "drone_id": "d1", "station_id": "station-1", "lake_id": "lake-1", "plan_id": "p2", "desired_state_version": 5, "status": "claimed"}

    def insert_acknowledgement(self, drone_id, command_id, sequence, status, detail):
        if sequence in self.sequences:
            return False
        self.sequences.add(sequence)
        self.acks.append((drone_id, command_id, sequence, status, detail))
        return True

    def advance_acknowledged_version(self, drone_id, version, command_id):
        if version < self.versions.get(drone_id, 0):
            return False
        self.versions[drone_id] = max(self.versions.get(drone_id, 0), version)
        return True


def test_old_ack_cannot_roll_state_back():
    from app.devices.acknowledgements import AcknowledgementService, StaleAcknowledgement

    service = AcknowledgementService(AckRepository())
    principal = DevicePrincipal("d1", "station-1", "credential-1", 7)
    service.record(principal, "c5", "p2", 5, "accepted", None)
    with pytest.raises(StaleAcknowledgement):
        service.record(principal, "c4", "p1", 4, "accepted", None)


def test_ack_requires_exact_command_ownership_and_version():
    from app.devices.acknowledgements import AcknowledgementService, AcknowledgementMismatch

    service = AcknowledgementService(AckRepository())
    with pytest.raises(AcknowledgementMismatch):
        service.record(DevicePrincipal("d1", "station-1", "credential-1", 7), "c5", "p2", 4, "accepted", None)
