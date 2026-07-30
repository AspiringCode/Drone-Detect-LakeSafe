"""Service-only, append-only security audit writer."""

from __future__ import annotations

from functools import lru_cache
from typing import Callable, Literal, Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL


class AuditUnavailable(RuntimeError):
    """Raised when a security decision cannot be durably recorded."""


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_user_id: str | None = None
    actor_device_id: str | None = None
    session_reference: str | None = Field(default=None, max_length=500)
    station_id: str | None = None
    lake_id: str | None = Field(default=None, max_length=200)
    request_id: UUID
    action: str = Field(min_length=1, max_length=200)
    decision: Literal["allowed", "denied", "failed"]
    reason: str = Field(min_length=1, max_length=1000)
    prior_state: dict | None = None
    resulting_state: dict | None = None
    source_context: dict | None = None

    @field_validator("source_context", mode="before")
    @classmethod
    def _source_context_defaults_to_empty_object(cls, value):
        return {} if value is None else value

    @model_validator(mode="after")
    def _one_actor(self) -> "AuditEvent":
        if (self.actor_user_id is None) == (self.actor_device_id is None):
            raise ValueError("Audit events require exactly one actor")
        return self


class _AuditClient(Protocol):
    def table(self, name: str): ...


class _AuditSink(Protocol):
    def record(self, event: AuditEvent) -> None: ...


class AuditWriter:
    """Uses only the backend service client; clients never write audit events."""

    def __init__(self, client: _AuditClient | None = None) -> None:
        if client is None:
            if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
                raise AuditUnavailable("Security audit service is unavailable")
            from supabase import create_client
            client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        self._client = client

    def record(self, event: AuditEvent) -> None:
        try:
            self._client.table("audit_events").insert(event.model_dump(mode="json")).execute()
        except Exception as exc:
            raise AuditUnavailable("Security audit persistence is unavailable") from exc


T = TypeVar("T")


def record_high_impact(writer: _AuditSink, event: AuditEvent, mutation: Callable[[], T]) -> T:
    """Persist the authorization decision before a non-reversible mutation."""
    writer.record(event)
    return mutation()


@lru_cache(maxsize=1)
def get_audit_writer() -> AuditWriter:
    return AuditWriter()


__all__ = ["AuditEvent", "AuditUnavailable", "AuditWriter", "get_audit_writer", "record_high_impact"]
