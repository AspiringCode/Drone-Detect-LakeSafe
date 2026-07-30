from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.audit import AuditEvent, AuditUnavailable, AuditWriter, record_high_impact


class _Result:
    data = {"audit_event_id": "audit-1"}


class _Insert:
    def __init__(self, client):
        self._client = client

    def insert(self, payload):
        self._client.payload = payload
        return self

    def execute(self):
        if self._client.fail:
            raise RuntimeError("database unavailable")
        return _Result()


class _ServiceClient:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.table_name = None
        self.payload = None

    def table(self, name):
        self.table_name = name
        return _Insert(self)


def _event(*, decision: str = "allowed") -> AuditEvent:
    return AuditEvent(
        actor_user_id="00000000-0000-0000-0000-000000000001",
        request_id=uuid4(),
        action="real_fleet.autonomy",
        decision=decision,
        reason="weather warning",
        station_id="00000000-0000-0000-0000-000000000002",
        lake_id="lake-1",
        source_context={"source": "real"},
    )


@pytest.mark.parametrize("decision", ["allowed", "denied", "failed"])
def test_writer_persists_every_security_decision_with_required_context(decision: str):
    client = _ServiceClient()
    AuditWriter(client).record(_event(decision=decision))
    assert client.table_name == "audit_events"
    assert client.payload["decision"] == decision
    assert client.payload["actor_user_id"] == "00000000-0000-0000-0000-000000000001"
    assert client.payload["station_id"] == "00000000-0000-0000-0000-000000000002"
    assert client.payload["lake_id"] == "lake-1"
    assert client.payload["request_id"]


def test_event_requires_exactly_one_actor():
    with pytest.raises(ValidationError, match="exactly one actor"):
        AuditEvent(
            actor_user_id=None,
            actor_device_id=None,
            request_id=uuid4(),
            action="station.create",
            decision="denied",
            reason="missing authority",
        )


def test_audit_write_failure_stops_high_impact_mutation():
    called = False

    def mutation():
        nonlocal called
        called = True
        return {"changed": True}

    with pytest.raises(AuditUnavailable):
        record_high_impact(AuditWriter(_ServiceClient(fail=True)), _event(), mutation)
    assert not called
