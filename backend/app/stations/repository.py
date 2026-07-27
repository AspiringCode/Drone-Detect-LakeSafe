from __future__ import annotations

from dataclasses import asdict
from functools import lru_cache
import re
from typing import Protocol

from app.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from app.stations.models import (
    AuditEventCreate, IdMeVerification, InvitationCreate, JoinRequest, JoinRequestCreate,
    JoinReviewCreate, LakeCreate, LakeRecord, StationMembership,
    StationRequest, StationRequestCreate, StationReviewCreate,
    VerificationSession, VerificationSessionCreate,
)


class WorkflowConflict(RuntimeError):
    """A workflow was missing, expired, consumed, or no longer transitionable."""


class WorkflowRepository(Protocol):
    def create_verification_session(self, value: VerificationSessionCreate) -> None: ...
    def consume_verification_session(self, state_hash: str) -> VerificationSession: ...
    def upsert_idme_verification(self, value: IdMeVerification) -> None: ...
    def idme_subject_owner(self, provider_subject: str) -> str | None: ...
    def create_station_request(self, value: StationRequestCreate) -> StationRequest: ...
    def create_join_request(self, value: JoinRequestCreate) -> JoinRequest: ...
    def create_invitation(self, value: InvitationCreate) -> None: ...
    def accept_invitation(self, token_hash: str, user_id: str, email: str) -> StationMembership: ...
    def review_station_request(self, value: StationReviewCreate) -> StationMembership | None: ...
    def review_join_request(self, value: JoinReviewCreate) -> StationMembership | None: ...
    def create_lake(self, value: LakeCreate) -> LakeRecord: ...
    def append_audit(self, value: AuditEventCreate) -> None: ...


class SupabaseWorkflowRepository:
    """Service-role-only adapter for transaction-backed station workflows."""

    def __init__(self, client=None) -> None:
        if client is None:
            if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
                raise RuntimeError("Supabase service credentials are not configured")
            from supabase import create_client
            client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        self._client = client

    def create_verification_session(self, value: VerificationSessionCreate) -> None:
        _require_sha256(value.state_hash)
        _require_sha256(value.nonce_hash)
        _require_sha256(value.verifier_hash)
        self._client.table("verification_sessions").insert(_payload(value)).execute()

    def consume_verification_session(self, state_hash: str) -> VerificationSession:
        _require_sha256(state_hash)
        return VerificationSession.from_record(self._rpc_one("consume_verification_session", {"p_state_hash": state_hash}, "Verification session is invalid, expired, or already consumed"))

    def upsert_idme_verification(self, value: IdMeVerification) -> None:
        self._rpc_one("upsert_idme_verification", {
            "p_user_id": value.user_id, "p_provider_subject": value.provider_subject,
            "p_legal_name": value.legal_name, "p_agency_name": value.agency_name,
            "p_verified_at": value.verified_at.isoformat(),
            "p_expires_at": value.expires_at.isoformat() if value.expires_at else None,
        }, "Unable to record ID.me verification")

    def idme_subject_owner(self, provider_subject: str) -> str | None:
        record = self._client.table("officer_verifications").select("user_id").eq(
            "provider", "id_me"
        ).eq("provider_subject", provider_subject).maybe_single().execute().data
        return str(record["user_id"]) if record else None

    def create_station_request(self, value: StationRequestCreate) -> StationRequest:
        return StationRequest.from_record(self._rpc_one("create_station_request", {
            "p_requested_by": value.requested_by, "p_requested_name": value.requested_name,
            "p_requested_address": value.requested_address,
        }, "Unable to create station request"))

    def create_join_request(self, value: JoinRequestCreate) -> JoinRequest:
        return JoinRequest.from_record(self._rpc_one("create_station_join_request", {
            "p_station_id": value.station_id, "p_user_id": value.user_id,
        }, "Unable to create join request"))

    def create_invitation(self, value: InvitationCreate) -> None:
        _require_sha256(value.token_hash)
        self._rpc_one("create_station_invitation", {
            "p_station_id": value.station_id, "p_actor_user_id": value.acting_admin_user_id,
            "p_token_hash": value.token_hash,
            "p_intended_email": value.intended_email.strip().casefold(),
            "p_expires_at": value.expires_at.isoformat(),
        }, "Unable to create station invitation")

    def accept_invitation(self, token_hash: str, user_id: str, email: str) -> StationMembership:
        _require_sha256(token_hash)
        record = self._rpc_one("accept_station_invitation", {"p_token_hash": token_hash, "p_user_id": user_id, "p_email": email.strip().casefold()}, "Invitation is invalid, expired, or already used")
        return StationMembership.from_record(record)

    def review_station_request(self, value: StationReviewCreate) -> StationMembership | None:
        record = self._rpc_one("review_station_request", {
            "p_station_request_id": value.station_request_id,
            "p_reviewer_user_id": value.reviewer_user_id,
            "p_decision": value.decision, "p_note": value.note,
        }, "Station request cannot be reviewed", allow_empty=True)
        return StationMembership.from_record(record) if record else None

    def review_join_request(self, value: JoinReviewCreate) -> StationMembership | None:
        record = self._rpc_one("review_station_join_request", {
            "p_station_join_request_id": value.station_join_request_id,
            "p_reviewer_user_id": value.reviewer_user_id,
            "p_decision": value.decision, "p_roles": list(value.roles),
        }, "Join request cannot be reviewed", allow_empty=True)
        return StationMembership.from_record(record) if record else None

    def create_lake(self, value: LakeCreate) -> LakeRecord:
        return LakeRecord.from_record(self._rpc_one("create_station_lake", {
            "p_lake_id": value.lake_id, "p_station_id": value.station_id,
            "p_name": value.name, "p_centroid_lat": value.centroid_lat,
            "p_centroid_lon": value.centroid_lon, "p_shoreline_geojson": value.shoreline_geojson,
            "p_created_by": value.created_by, "p_data_source_status": value.data_source_status,
        }, "Unable to create lake"))

    def append_audit(self, value: AuditEventCreate) -> None:
        self._client.table("audit_events").insert(_payload(value)).execute()

    def _rpc_one(self, name: str, parameters: dict, message: str, *, allow_empty: bool = False) -> dict | None:
        result = self._client.rpc(name, parameters).execute()
        data = result.data
        if isinstance(data, list):
            data = data[0] if data else None
        if data == {} and allow_empty:
            return None
        if not data:
            raise WorkflowConflict(message)
        return data


def _payload(value, **overrides) -> dict:
    data = asdict(value)
    data.update(overrides)
    return {key: item.isoformat() if hasattr(item, "isoformat") else item for key, item in data.items()}


def _require_sha256(value: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Expected a canonical lowercase SHA-256 hash")


@lru_cache(maxsize=1)
def get_workflow_repository() -> SupabaseWorkflowRepository:
    return SupabaseWorkflowRepository()
