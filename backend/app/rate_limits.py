"""Database-backed limits for privileged mutations.

Limits are never process-local: multiple API workers must observe the same
station/action bucket.  A missing durable limiter is a fail-closed condition.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from fastapi import HTTPException, Request

from app.access.principal import Principal
from app.audit import AuditEvent, AuditUnavailable, get_audit_writer
from app.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from app.correlation import get_request_id


class RateLimitUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int


class _RpcClient(Protocol):
    def rpc(self, name: str, parameters: dict): ...


class RateLimitRepository:
    def __init__(self, client: _RpcClient | None = None) -> None:
        if client is None:
            if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
                raise RateLimitUnavailable("Durable rate limiting is unavailable")
            from supabase import create_client
            client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        self._client = client

    def claim(self, *, scope: str, subject: str, limit: int, window_seconds: int) -> RateLimitResult:
        try:
            data = self._client.rpc("claim_rate_limit", {
                "p_scope": scope, "p_subject": subject,
                "p_limit": limit, "p_window_seconds": window_seconds,
            }).execute().data
        except Exception as exc:
            raise RateLimitUnavailable("Durable rate limiting is unavailable") from exc
        if isinstance(data, list):
            data = data[0] if data else None
        if not isinstance(data, dict) or not isinstance(data.get("allowed"), bool):
            raise RateLimitUnavailable("Durable rate limiting returned an invalid response")
        retry_after = data.get("retry_after_seconds", 0)
        if not isinstance(retry_after, int) or retry_after < 0:
            raise RateLimitUnavailable("Durable rate limiting returned an invalid retry window")
        return RateLimitResult(data["allowed"], retry_after)


@lru_cache(maxsize=1)
def get_rate_limit_repository() -> RateLimitRepository:
    return RateLimitRepository()


# These intentionally conservative limits protect state-changing surfaces while
# still allowing normal operator workflows.  Scope includes the action and the
# subject is station + authenticated actor, so one station cannot exhaust another.
PRIVILEGED_LIMITS: dict[str, tuple[int, int]] = {
    "verification.start": (5, 3600),
    "station.invitation.create": (20, 3600),
    "station.join.review": (40, 3600),
    "station.review": (40, 3600),
    "lake.create": (10, 3600),
    "lake.refresh": (12, 3600),
    "inventory.simulated.register": (12, 3600),
    "inventory.circulation.change": (30, 3600),
    "inventory.real.register": (12, 3600),
    "inventory.real.retire": (20, 3600),
    "safety.autonomy": (5, 60),
    "safety.safe_return": (5, 60),
}


def _subject(principal: Principal, station_id: str | None) -> str:
    return f"station:{station_id or 'platform'}:user:{principal.user_id}"


def _audit_denied(*, principal: Principal, request: Request, scope: str, station_id: str | None, lake_id: str | None) -> None:
    try:
        get_audit_writer().record(AuditEvent(
            actor_user_id=principal.user_id, request_id=get_request_id(request),
            action=f"rate_limit.{scope}", decision="denied", reason="privileged action rate limit exceeded",
            station_id=station_id, lake_id=lake_id,
            source_context={"component": "durable_rate_limit", "scope": scope},
        ))
    except AuditUnavailable as exc:
        # A denial without an immutable audit decision is not an acceptable
        # security outcome; callers must retry rather than receive an unlogged 429.
        raise HTTPException(status_code=503, detail="Security audit service is unavailable") from exc


def require_rate_limit(scope: str, principal: Principal, request: Request, *, station_id: str | None = None, lake_id: str | None = None) -> None:
    """Claim a durable action slot or raise a fail-closed HTTP response."""
    try:
        limit, window_seconds = PRIVILEGED_LIMITS[scope]
    except KeyError as exc:
        raise RuntimeError(f"No privileged rate-limit policy for {scope}") from exc
    try:
        result = get_rate_limit_repository().claim(
            scope=scope, subject=_subject(principal, station_id), limit=limit, window_seconds=window_seconds
        )
    except RateLimitUnavailable as exc:
        raise HTTPException(status_code=503, detail="Privileged action rate limit is unavailable") from exc
    if result.allowed:
        return
    _audit_denied(principal=principal, request=request, scope=scope, station_id=station_id, lake_id=lake_id)
    raise HTTPException(
        status_code=429, detail="Privileged action rate limit exceeded",
        headers={"Retry-After": str(max(1, result.retry_after_seconds))},
    )


__all__ = ["PRIVILEGED_LIMITS", "RateLimitRepository", "RateLimitResult", "RateLimitUnavailable", "get_rate_limit_repository", "require_rate_limit"]
