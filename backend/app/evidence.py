"""Server-authorized access to private thermal evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from supabase import create_client

from app.access.policy import Permission, require_station_access
from app.access.principal import Principal, get_principal
from app.audit import AuditEvent, AuditUnavailable, AuditWriter, get_audit_writer
from app.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL


_BUCKET = "thermal-clips"
_MAX_EXPIRY_SECONDS = 60
router = APIRouter(prefix="/api/evidence", tags=["evidence"])


class EvidenceNotFound(LookupError):
    """The evidence cannot be disclosed to this principal."""


class EvidenceForbidden(PermissionError):
    """The caller does not have operational evidence authority."""


@dataclass(frozen=True)
class AuthorizedEvidenceURL:
    url: str
    expires_in: int


class OperationalAlertRepository(Protocol):
    def get_operational_alert(self, alert_id: str) -> dict[str, object] | None: ...


class EvidenceStorage(Protocol):
    def create_signed_url(self, bucket: str, path: str, expires_in: int) -> str: ...


class _AuditSink(Protocol):
    def record(self, event: AuditEvent) -> None: ...


class SupabaseOperationalAlertRepository:
    """Service-only operational alert lookup; never expose its result directly."""

    def __init__(self) -> None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            raise RuntimeError("Evidence service is unavailable")
        self._client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    def get_operational_alert(self, alert_id: str) -> dict[str, object] | None:
        result = self._client.table("operational_alerts").select(
            "alert_id,station_id,lake_id,thermal_clip_ref"
        ).eq("alert_id", alert_id).maybe_single().execute()
        return dict(result.data) if result.data else None


class SupabaseEvidenceStorage:
    """Signs evidence URLs with the backend service credential only."""

    def __init__(self) -> None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            raise RuntimeError("Evidence service is unavailable")
        self._client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    def create_signed_url(self, bucket: str, path: str, expires_in: int) -> str:
        result = self._client.storage.from_(bucket).create_signed_url(path, expires_in)
        data = result.data or {}
        url = data.get("signedURL") or data.get("signedUrl")
        if not isinstance(url, str) or not url:
            raise RuntimeError("Evidence signing did not return a URL")
        return url


class EvidenceService:
    def __init__(
        self,
        alerts: OperationalAlertRepository,
        storage: EvidenceStorage,
        audit: _AuditSink,
    ) -> None:
        self._alerts = alerts
        self._storage = storage
        self._audit = audit

    def _audit_decision(
        self,
        principal: Principal,
        *,
        station_id: str | None,
        lake_id: str | None,
        decision: str,
        reason: str,
    ) -> None:
        self._audit.record(AuditEvent(
            actor_user_id=principal.user_id,
            request_id=uuid4(),
            action="thermal_evidence.read",
            decision=decision,
            reason=reason,
            station_id=station_id,
            lake_id=lake_id,
            source_context={"component": "evidence_service"},
        ))

    def create_authorized_url(
        self, alert_id: str, access_context: Principal
    ) -> AuthorizedEvidenceURL:
        """Return a 60-second link only after station capability validation."""
        if access_context.account_class != "officer":
            self._audit_decision(
                access_context, station_id=None, lake_id=None, decision="denied",
                reason="Civilian accounts cannot access thermal evidence",
            )
            raise EvidenceForbidden("Operational evidence access is required")

        alert = self._alerts.get_operational_alert(alert_id)
        if alert is None:
            self._audit_decision(
                access_context, station_id=None, lake_id=None, decision="denied",
                reason="Thermal evidence was not found",
            )
            raise EvidenceNotFound("Evidence not found")

        station_id = str(alert["station_id"])
        lake_id = str(alert["lake_id"])
        clip_ref = alert.get("thermal_clip_ref")
        try:
            require_station_access(access_context, station_id, Permission.READ_OPERATIONS)
        except HTTPException as exc:
            self._audit_decision(
                access_context, station_id=station_id, lake_id=lake_id, decision="denied",
                reason="Thermal evidence is outside the caller's station access",
            )
            if not any(member.station_id == station_id for member in access_context.memberships):
                raise EvidenceNotFound("Evidence not found") from exc
            raise EvidenceForbidden("Operational evidence access is required") from exc

        if not isinstance(clip_ref, str) or not clip_ref.strip():
            self._audit_decision(
                access_context, station_id=station_id, lake_id=lake_id, decision="denied",
                reason="Thermal evidence was not found",
            )
            raise EvidenceNotFound("Evidence not found")

        url = self._storage.create_signed_url(_BUCKET, clip_ref, _MAX_EXPIRY_SECONDS)
        self._audit_decision(
            access_context, station_id=station_id, lake_id=lake_id, decision="allowed",
            reason="Thermal evidence URL authorized",
        )
        return AuthorizedEvidenceURL(url=url, expires_in=_MAX_EXPIRY_SECONDS)


def get_evidence_service() -> EvidenceService:
    return EvidenceService(
        SupabaseOperationalAlertRepository(), SupabaseEvidenceStorage(), get_audit_writer()
    )


@router.get("/alerts/{alert_id}/thermal", response_model=AuthorizedEvidenceURL)
def thermal_evidence_url(
    alert_id: str,
    principal: Principal = Depends(get_principal),
) -> AuthorizedEvidenceURL:
    try:
        return get_evidence_service().create_authorized_url(alert_id, principal)
    except EvidenceNotFound as exc:
        raise HTTPException(status_code=404, detail="Evidence not found") from exc
    except EvidenceForbidden as exc:
        raise HTTPException(status_code=403, detail="Operational evidence access is required") from exc
    except (AuditUnavailable, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail="Evidence service is unavailable") from exc


__all__ = [
    "AuthorizedEvidenceURL", "EvidenceForbidden", "EvidenceNotFound", "EvidenceService",
    "get_evidence_service", "router",
]
