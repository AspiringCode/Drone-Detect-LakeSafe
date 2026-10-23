from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

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


class Secrets:
    def __init__(self, values: dict[str, bytes] | None = None) -> None:
        self.values = values or {"gateway-key-ref": b"actual-server-secret"}

    def resolve(self, reference: str) -> bytes | None:
        return self.values.get(reference)


class Inventory:
    def __init__(self) -> None:
        self.rows = {"d1": {"source": "real", "station_id": "station-1", "lake_id": "lake-1", "credential_state": "active"}}

    def real_inventory(self, drone_id: str):
        return self.rows.get(drone_id)

    def lake_station_id(self, lake_id: str):
        return "station-1" if lake_id == "lake-1" else None


def test_real_adapter_rejects_simulated_inventory():
    from app.autonomy.adapters.real import RealAdapter, TransportIsolationError

    gateway = Gateway()
    adapter = RealAdapter(Inventory(), gateway, gateway_url="https://gateway.test", signing_key_ref="gateway-key-ref", secret_provider=Secrets())
    with pytest.raises(TransportIsolationError):
        adapter.publish(command_for(source="simulated"))
    assert gateway.calls == []


def test_real_adapter_signs_and_publishes_real_command_only():
    from app.autonomy.adapters.real import RealAdapter

    gateway = Gateway()
    adapter = RealAdapter(Inventory(), gateway, gateway_url="https://gateway.test", signing_key_ref="gateway-key-ref", secret_provider=Secrets())
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
    publisher = OutboxPublisher(repository, RealAdapter(Inventory(), gateway, gateway_url="https://gateway.test", signing_key_ref="gateway-key-ref", secret_provider=Secrets()))
    assert publisher.publish_pending() == ()
    assert len(gateway.calls) == 1
    assert repository.acknowledged_version("d1") == 0


def test_known_key_reference_cannot_be_used_as_signing_secret():
    from app.hardware_gateway import HmacGatewaySigner

    with pytest.raises(ValueError):
        HmacGatewaySigner("gateway-key-ref")


def test_ack_database_contract_checks_version_before_acknowledging_command():
    sql = (Path(__file__).parents[3] / "supabase" / "migrations" / "0025_real_outbox_claim_scope.sql").read_text().lower()
    function = sql.split("create or replace function public.record_real_command_acknowledgement", 1)[1]
    assert "p_version integer" in function
    assert "v_version <> p_version" in function
    assert function.index("v_version <> p_version") < function.index("insert into public.command_acknowledgements")
    assert function.index("v_version <> p_version") < function.index("status='acknowledged'")
    assert "acknowledged_state_version" in function
    assert function.index("from public.drone_inventory") < function.index("insert into public.command_acknowledgements")
    assert function.index("v_acknowledged > p_version") < function.index("insert into public.command_acknowledgements")


def test_real_claim_database_contract_is_source_and_lake_station_scoped():
    sql = (Path(__file__).parents[3] / "supabase" / "migrations" / "0025_real_outbox_claim_scope.sql").read_text().lower()
    assert "p_station_id uuid" in sql and "p_lake_id text" in sql
    assert "inventory.source = 'real'" in sql
    assert "command.station_id = p_station_id" in sql and "command.lake_id = p_lake_id" in sql
    assert "inventory.station_id = command.station_id" in sql
    assert "inventory.lake_id = command.lake_id" in sql


def test_repository_claims_real_commands_with_exact_station_and_lake():
    from app.autonomy.repository import SupabaseAutonomyRepository

    class Result:
        data = []

    class Client:
        def __init__(self): self.call = None
        def rpc(self, name, payload):
            self.call = (name, payload)
            return self
        def execute(self): return Result()

    client = Client()
    assert SupabaseAutonomyRepository(client).claim_real_pending("station-1", "lake-1", 7) == ()
    assert client.call == ("claim_real_autonomy_outbox", {"p_station_id": "station-1", "p_lake_id": "lake-1", "p_limit": 7})


def test_real_autonomy_publisher_stays_dormant_without_a_resolved_secret(monkeypatch):
    from fastapi import FastAPI
    from app.devices import reconciler

    monkeypatch.setattr(reconciler, "REAL_GATEWAY_URL", "https://gateway.test")
    monkeypatch.setattr(reconciler, "REAL_GATEWAY_SIGNING_KEY_REF", "gateway-key-ref")
    app = FastAPI()
    assert reconciler.configure_real_autonomy_service(app, device_repository=Inventory(), secret_provider=Secrets({})) is False
    assert getattr(app.state, "real_autonomy_service", None) is None


def test_resolved_real_gateway_starts_real_only_publisher(monkeypatch):
    from fastapi import FastAPI
    from app.autonomy.repository import InMemoryAutonomyRepository
    from app.devices import reconciler

    monkeypatch.setattr(reconciler, "REAL_GATEWAY_URL", "https://gateway.test")
    monkeypatch.setattr(reconciler, "REAL_GATEWAY_SIGNING_KEY_REF", "gateway-key-ref")
    app, gateway = FastAPI(), Gateway()
    outbox = InMemoryAutonomyRepository(station_id="station-1")
    outbox.enqueue(command_for())
    assert reconciler.configure_real_autonomy_service(app, device_repository=Inventory(), secret_provider=Secrets(), gateway=gateway, autonomy_repository=outbox) is True
    assert app.state.real_autonomy_service.reconcile_lake("lake-1", "heartbeat_recovery") == ("c5",)
    assert len(gateway.calls) == 1
    assert outbox.acknowledged_version("d1") == 0


def test_heartbeat_gateway_puts_published_commands_in_the_drone_mailbox(monkeypatch):
    from fastapi import FastAPI
    from app.autonomy.repository import InMemoryAutonomyRepository
    from app.devices import live_commands, reconciler

    monkeypatch.setattr(reconciler, "REAL_GATEWAY_URL", "heartbeat")
    monkeypatch.setattr(reconciler, "REAL_GATEWAY_SIGNING_KEY_REF", "gateway-key-ref")
    monkeypatch.setattr(live_commands, "_mailbox", {})
    app = FastAPI()
    outbox = InMemoryAutonomyRepository(station_id="station-1")
    outbox.enqueue(command_for())
    assert reconciler.configure_real_autonomy_service(app, device_repository=Inventory(), secret_provider=Secrets(), autonomy_repository=outbox) is True
    assert app.state.real_autonomy_service.reconcile_lake("lake-1", "heartbeat_recovery") == ("c5",)
    [command] = live_commands.pending("d1")
    assert (command["command_id"], command["ack"]) == ("c5", True)


class AckRepository:
    def __init__(self) -> None:
        self.acks: list[tuple] = []
        self.versions: dict[str, int] = {}
        self.sequences: set[int] = set()

    def command_for_ack(self, command_id: str):
        if command_id == "return-6":
            return {"command_id": command_id, "drone_id": "d1", "station_id": "station-1", "lake_id": "lake-1", "plan_id": None, "desired_state_version": 6, "command_type": "return_to_reserve", "status": "claimed"}
        if command_id == "c4":
            return {"command_id": command_id, "drone_id": "d1", "station_id": "station-1", "lake_id": "lake-1", "plan_id": "p1", "desired_state_version": 4, "status": "claimed"}
        return {"command_id": command_id, "drone_id": "d1", "station_id": "station-1", "lake_id": "lake-1", "plan_id": "p2", "desired_state_version": 5, "status": "claimed"}

    def insert_acknowledgement(self, drone_id, command_id, sequence, plan_id, version, status, detail):
        if sequence in self.sequences:
            return False
        if version < self.versions.get(drone_id, 0):
            return False
        self.sequences.add(sequence)
        self.acks.append((drone_id, command_id, sequence, status, detail))
        if status in {"accepted", "completed"}:
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


def test_safe_return_ack_allows_no_plan_but_keeps_exact_drone_and_version_binding():
    from app.devices.acknowledgements import AcknowledgementService, AcknowledgementMismatch

    service = AcknowledgementService(AckRepository())
    principal = DevicePrincipal("d1", "station-1", "credential-1", 8)
    service.record(principal, "return-6", None, 6, "accepted", None)
    with pytest.raises(AcknowledgementMismatch):
        service.record(DevicePrincipal("d1", "station-1", "credential-1", 9), "return-6", None, 5, "accepted", None)


def test_device_api_accepts_valid_safe_return_ack_without_plan_id(monkeypatch):
    from app.api import devices

    private = Ed25519PrivateKey.generate()
    public_key = base64.urlsafe_b64encode(private.public_key().public_bytes_raw()).rstrip(b"=").decode()

    class Repository(AckRepository):
        def active_credential(self, drone_id):
            return {"drone_id": drone_id, "station_id": "station-1", "credential_id": "credential-1", "public_key": public_key}
        def claim_sequence(self, drone_id, sequence): return True

    repository = Repository()
    app = FastAPI(); app.include_router(devices.router)
    monkeypatch.setattr(devices, "get_device_repository", lambda: repository)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = b'{"desired_state_version":6,"status":"accepted"}'
    signature = base64.urlsafe_b64encode(private.sign(canonical_request_bytes("d1", timestamp, 10, body))).rstrip(b"=").decode()
    response = TestClient(app).post("/api/devices/d1/commands/return-6/acknowledgements", content=body, headers={
        "X-Device-Timestamp": timestamp, "X-Device-Sequence": "10", "X-Device-Signature": signature,
    })
    assert response.status_code == 202


def test_real_claim_database_contract_filters_due_unexpired_commands_and_increments_attempts():
    sql = (Path(__file__).parents[3] / "supabase" / "migrations" / "0027_real_delivery_retry_and_safe_return_ack.sql").read_text().lower()
    claim = sql.split("create or replace function public.claim_real_autonomy_outbox", 1)[1]
    assert "expires_at is null or command.expires_at > now()" in claim
    assert "next_attempt_at is null or command.next_attempt_at <= now()" in claim
    assert "delivery_attempts=command.delivery_attempts+1" in claim


def test_real_publisher_expires_before_claim_and_schedules_reduced_capacity_reconciliation():
    from app.devices.reconciler import RealAutonomyPublisher

    class DeliveryRepository:
        def __init__(self): self.claimed = False
        def expire_real_delivery(self, station_id, lake_id):
            assert (station_id, lake_id) == ("station-1", "lake-1")
            return ("d2",)
        def claim_real_pending(self, station_id, lake_id, limit):
            self.claimed = True
            return ()

    class Lakes(Inventory):
        def __init__(self): super().__init__(); self.reconciliations = []
        def request_real_capacity_reconciliation(self, lake_id, trigger): self.reconciliations.append((lake_id, trigger))

    deliveries, lakes = DeliveryRepository(), Lakes()
    assert RealAutonomyPublisher(deliveries, Gateway(), lakes).reconcile_lake("lake-1", "timer") == ()
    assert deliveries.claimed is True
    assert lakes.reconciliations == [("lake-1", "real_command_expired")]


def test_real_publisher_uses_real_release_path_after_gateway_failure():
    from app.devices.reconciler import RealAutonomyPublisher

    class DeliveryRepository:
        def expire_real_delivery(self, station_id, lake_id): return ()
        def claim_real_pending(self, station_id, lake_id, limit): return (command_for(),)
        def release_real(self, command_id): self.command_id = command_id; return True

    class FailingGateway:
        def publish(self, command): raise RuntimeError("gateway offline")

    deliveries = DeliveryRepository()
    RealAutonomyPublisher(deliveries, FailingGateway(), Inventory()).reconcile_lake("lake-1", "timer")
    assert deliveries.command_id == "c5"
