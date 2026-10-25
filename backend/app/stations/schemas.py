from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StationRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    address: str | None = Field(default=None, max_length=320)


class InvitationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    expires_at: datetime | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().casefold()
        if "@" not in value:
            raise ValueError("A valid email is required")
        return value


class InvitationAcceptInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=43, max_length=256)


class JoinDecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str
    roles: tuple[str, ...] = ("viewer",)

    @field_validator("decision")
    @classmethod
    def valid_decision(cls, value: str) -> str:
        if value not in {"approved", "rejected"}:
            raise ValueError("Unsupported decision")
        return value

    @field_validator("roles")
    @classmethod
    def valid_roles(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        supported = {"viewer", "dispatcher", "safety_supervisor", "station_admin"}
        if not value or any(role not in supported for role in value):
            raise ValueError("Unsupported station role")
        return tuple(sorted(set(value)))


class MemberChangeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    roles: tuple[str, ...]
    status: str = "active"

    @field_validator("roles")
    @classmethod
    def valid_roles(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return JoinDecisionInput.valid_roles(value)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in {"active", "suspended", "revoked"}:
            raise ValueError("Unsupported membership status")
        return value
