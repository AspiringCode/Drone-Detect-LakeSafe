from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated

from fastapi import Header, HTTPException

from app.auth import verify_supabase_jwt
from app.access.repository import ACCESS_REPOSITORY_ERRORS


class StationRole(StrEnum):
    VIEWER = "viewer"
    DISPATCHER = "dispatcher"
    SAFETY_SUPERVISOR = "safety_supervisor"
    STATION_ADMIN = "station_admin"


@dataclass(frozen=True)
class StationMembership:
    station_id: str
    station_name: str
    status: str
    roles: frozenset[StationRole]


@dataclass(frozen=True)
class Principal:
    user_id: str
    email: str | None
    aal: str | None
    account_class: str
    verification_status: str | None
    memberships: tuple[StationMembership, ...]
    amr: tuple[dict[str, object], ...] = ()


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token is required")
    return authorization.removeprefix("Bearer ")


def principal_from_claims(claims: dict[str, object], repository) -> Principal:
    user_id = claims.get("sub")
    if not isinstance(user_id, str):
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    try:
        profile = repository.load_principal_state(user_id)
    except ACCESS_REPOSITORY_ERRORS as exc:
        raise HTTPException(status_code=503, detail="Account data is temporarily unavailable") from exc
    if profile is None:
        # A valid token without a server-side profile is never operational.
        return Principal(user_id, None, None, "civilian", None, ())
    memberships = tuple(
        StationMembership(
            station_id=str(row["station_id"]),
            station_name=str(row.get("station_name") or "Station"),
            status=str(row.get("membership_status") or ""),
            roles=frozenset(StationRole(role) for role in row.get("roles", []) if role in StationRole._value2member_map_),
        )
        for row in profile.get("memberships", [])
    )
    raw_amr = claims.get("amr")
    amr = tuple(item for item in raw_amr if isinstance(item, dict)) if isinstance(raw_amr, list) else ()
    return Principal(
        user_id=user_id,
        # Supabase signs the email claim.  It is needed for invitation-address
        # matching; profile state intentionally does not duplicate auth email.
        email=claims.get("email") if isinstance(claims.get("email"), str) else None,
        aal=claims.get("aal") if isinstance(claims.get("aal"), str) else None,
        account_class=str(profile.get("account_class") or "civilian"),
        verification_status=profile.get("verification_status") if isinstance(profile.get("verification_status"), str) else None,
        memberships=memberships,
        amr=amr,
    )


def get_principal(
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    # Imported lazily so test doubles can replace the repository provider and
    # no credentials are needed until a protected request is made.
    from app.access.repository import get_access_repository

    claims = verify_supabase_jwt(_bearer_token(authorization))
    try:
        repository = get_access_repository()
    except ACCESS_REPOSITORY_ERRORS as exc:
        raise HTTPException(status_code=503, detail="Account data is temporarily unavailable") from exc
    return principal_from_claims(claims, repository)
