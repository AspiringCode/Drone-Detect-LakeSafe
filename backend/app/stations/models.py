from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


VerificationSessionStatus = Literal["pending", "consumed", "expired", "failed"]
ReviewDecision = Literal["approved", "rejected"]
MembershipStatus = Literal["invited", "active", "suspended", "revoked"]


@dataclass(frozen=True)
class VerificationSessionCreate:
    state_hash: str
    nonce_hash: str
    verifier_hash: str
    user_id: str
    expires_at: datetime


@dataclass(frozen=True)
class VerificationSession:
    verification_session_id: str
    state_hash: str
    nonce_hash: str
    verifier_hash: str
    user_id: str
    status: VerificationSessionStatus
    expires_at: datetime

    @classmethod
    def from_record(cls, value: dict) -> "VerificationSession":
        return cls(
            verification_session_id=str(value["verification_session_id"]),
            state_hash=str(value["state_hash"]),
            nonce_hash=str(value["nonce_hash"]),
            verifier_hash=str(value["verifier_hash"]),
            user_id=str(value["user_id"]),
            status=value["status"],
            expires_at=_as_datetime(value["expires_at"]),
        )


@dataclass(frozen=True)
class IdMeVerification:
    user_id: str
    provider_subject: str
    legal_name: str
    agency_name: str
    verified_at: datetime
    expires_at: datetime | None


@dataclass(frozen=True)
class StationRequestCreate:
    requested_by: str
    requested_name: str
    requested_address: str | None = None


@dataclass(frozen=True)
class StationRequest:
    station_request_id: str
    requested_by: str
    requested_name: str
    requested_address: str | None
    status: str

    @classmethod
    def from_record(cls, value: dict) -> "StationRequest":
        return cls(str(value["station_request_id"]), str(value["requested_by"]), str(value["requested_name"]), value.get("requested_address"), str(value["status"]))


@dataclass(frozen=True)
class JoinRequestCreate:
    station_id: str
    user_id: str


@dataclass(frozen=True)
class JoinRequest:
    station_join_request_id: str
    station_id: str
    user_id: str
    status: str

    @classmethod
    def from_record(cls, value: dict) -> "JoinRequest":
        return cls(
            str(value["station_join_request_id"]), str(value["station_id"]),
            str(value["user_id"]), str(value["status"]),
        )


@dataclass(frozen=True)
class InvitationCreate:
    station_id: str
    acting_admin_user_id: str
    token_hash: str
    intended_email: str
    expires_at: datetime


@dataclass(frozen=True)
class StationReviewCreate:
    station_request_id: str
    reviewer_user_id: str
    decision: ReviewDecision
    note: str | None = None


@dataclass(frozen=True)
class JoinReviewCreate:
    station_join_request_id: str
    reviewer_user_id: str
    decision: ReviewDecision
    roles: tuple[str, ...] = ("viewer",)


@dataclass(frozen=True)
class StationMembership:
    membership_id: str
    station_id: str
    user_id: str
    status: MembershipStatus
    roles: tuple[str, ...] = ()

    @classmethod
    def from_record(cls, value: dict) -> "StationMembership":
        roles = value.get("roles") or value.get("station_membership_roles") or []
        normalized = tuple(sorted(item["role"] if isinstance(item, dict) else str(item) for item in roles))
        return cls(str(value["membership_id"]), str(value["station_id"]), str(value["user_id"]), value["status"], normalized)


@dataclass(frozen=True)
class LakeCreate:
    lake_id: str
    station_id: str
    name: str
    centroid_lat: float
    centroid_lon: float
    shoreline_geojson: dict
    created_by: str


@dataclass(frozen=True)
class LakeRecord:
    lake_id: str
    station_id: str
    name: str

    @classmethod
    def from_record(cls, value: dict) -> "LakeRecord":
        return cls(str(value["lake_id"]), str(value["station_id"]), str(value["name"]))


@dataclass(frozen=True)
class AuditEventCreate:
    actor_user_id: str | None
    actor_device_id: str | None
    request_id: str
    action: str
    decision: Literal["allowed", "denied", "failed"]
    reason: str
    station_id: str | None = None
    lake_id: str | None = None
    session_reference: str | None = None
    prior_state: dict | None = None
    resulting_state: dict | None = None
    source_context: dict | None = None


def _as_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
