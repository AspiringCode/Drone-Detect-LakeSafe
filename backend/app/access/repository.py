from __future__ import annotations

from functools import lru_cache
from datetime import datetime, timezone

from httpx import HTTPError
from postgrest.exceptions import APIError
from supabase import SupabaseException

from app.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL


class AccessRepositoryError(RuntimeError):
    """Account infrastructure is temporarily unavailable."""


ACCESS_REPOSITORY_ERRORS = (RuntimeError, HTTPError, APIError, ValueError, SupabaseException)


class SupabaseAccessRepository:
    """Reads authorization facts with the backend-only service credential."""

    def __init__(self) -> None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            raise RuntimeError("Supabase service credentials are not configured")
        from app.supabase_transport import create_server_client as create_client

        self.client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    def load_principal_state(self, user_id: str) -> dict | None:
        profile_response = self.client.table("profiles").select("account_class, display_name").eq("user_id", user_id).maybe_single().execute()
        profile = profile_response.data if profile_response is not None else None
        if not profile:
            return None
        verification_response = self.client.table("officer_verifications").select("status, expires_at, revoked_at").eq("user_id", user_id).maybe_single().execute()
        verification = (verification_response.data if verification_response is not None else None) or {}
        verification_status = verification.get("status")
        expiry = verification.get("expires_at")
        if verification.get("revoked_at") or (isinstance(expiry, str) and datetime.fromisoformat(expiry.replace("Z", "+00:00")) <= datetime.now(timezone.utc)):
            verification_status = "expired"
        memberships = self.client.table("station_memberships").select("station_id,status,stations(name,status),station_membership_roles(role)").eq("user_id", user_id).execute().data or []
        judge_response = self.client.table("cac_judge_access").select("expires_at").eq("user_id", user_id).maybe_single().execute()
        judge_access = judge_response.data if judge_response is not None else None
        judge_expiry = judge_access.get("expires_at") if judge_access else None
        judge_demo_access = isinstance(judge_expiry, str) and datetime.fromisoformat(judge_expiry.replace("Z", "+00:00")) > datetime.now(timezone.utc)
        normalized = []
        for membership in memberships:
            station = membership.get("stations") or {}
            normalized.append({
                "station_id": membership["station_id"],
                "station_name": station.get("name"),
                "membership_status": membership.get("status") if station.get("status") == "active" else "inactive_station",
                "roles": [item["role"] for item in membership.get("station_membership_roles") or []],
            })
        return {
            "email": None,
            "account_class": profile.get("account_class"),
            "verification_status": verification_status,
            "memberships": normalized,
            "judge_demo_access": judge_demo_access,
        }

    def lake_station_id(self, lake_id: str) -> str | None:
        response = self.client.table("lakes").select("station_id").eq("lake_id", lake_id).maybe_single().execute()
        record = response.data if response is not None else None
        return str(record["station_id"]) if record else None


@lru_cache(maxsize=1)
def get_access_repository() -> SupabaseAccessRepository:
    try:
        return SupabaseAccessRepository()
    except ACCESS_REPOSITORY_ERRORS as exc:
        raise AccessRepositoryError("Account data is temporarily unavailable") from exc
