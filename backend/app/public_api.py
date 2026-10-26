"""Sanitized, anonymous LakeSafe projections.

This module is deliberately separate from operational routes.  It only reads
the public projection tables and its DTOs reject extra fields so an accidental
join cannot disclose operational telemetry through the public API.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from fastapi import APIRouter, HTTPException
from httpx import HTTPError
from postgrest.exceptions import APIError
from pydantic import BaseModel, ConfigDict, model_validator
from supabase import SupabaseException, create_client

from app.config import SUPABASE_KEY, SUPABASE_URL

router = APIRouter(prefix="/api/public", tags=["public"])


class PublicLake(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lake_id: str
    name: str
    approximate_center_geohash: str | None
    public_status: str
    refreshed_at: datetime
    map_bounds: tuple[float, float, float, float] | None = None


class PublicAlert(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lake_id: str
    category: str
    approximate_area_label: str
    public_status: str
    occurred_at: datetime
    published_at: datetime


class PublicPatrolPresence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lake_id: str
    generalized_zone: str
    public_state: str
    observed_bucket: datetime
    published_at: datetime

    @model_validator(mode="after")
    def enforce_minimum_publication_delay(self) -> "PublicPatrolPresence":
        """Fail closed if an un-delayed patrol record reaches any public path."""
        if self.observed_bucket.tzinfo is None or self.observed_bucket.utcoffset() is None:
            raise ValueError("observed_bucket must include a timezone")
        if self.published_at.tzinfo is None or self.published_at.utcoffset() is None:
            raise ValueError("published_at must include a timezone")
        if self.published_at < self.observed_bucket + timedelta(minutes=5):
            raise ValueError("public patrol presence must be delayed by at least five minutes")
        return self


class PublicProjectionRepository(Protocol):
    def list_lakes(self) -> list[dict[str, object]]: ...
    def list_alerts(self, lake_id: str) -> list[dict[str, object]]: ...
    def list_patrol_presence(self, lake_id: str) -> list[dict[str, object]]: ...


class SupabasePublicProjectionRepository:
    """Projection-only repository. Never add operational table queries here."""

    def __init__(self) -> None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("Public data service is unavailable")
        self._client = create_client(SUPABASE_URL, SUPABASE_KEY)

    def list_lakes(self) -> list[dict[str, object]]:
        return self._rows(self._client.table("public_lakes").select(
            "lake_id,name,approximate_center_geohash,public_status,refreshed_at,map_bounds"
        ).eq('public_visible',True).order("name").execute().data)

    def list_alerts(self, lake_id: str) -> list[dict[str, object]]:
        if not self._visible(lake_id): return []
        return self._rows(self._client.table("public_alerts").select(
            "lake_id,category,approximate_area_label,public_status,occurred_at,published_at"
        ).eq("lake_id", lake_id).order("published_at", desc=True).execute().data)

    def list_patrol_presence(self, lake_id: str) -> list[dict[str, object]]:
        if not self._visible(lake_id): return []
        return self._rows(self._client.table("public_patrol_presence").select(
            "lake_id,generalized_zone,public_state,observed_bucket,published_at"
        ).eq("lake_id", lake_id).order("published_at", desc=True).execute().data)

    def _visible(self,lake_id):
        return bool(self._client.table('public_lakes').select('lake_id').eq('lake_id',lake_id).eq('public_visible',True).limit(1).execute().data)

    @staticmethod
    def _rows(data: object) -> list[dict[str, object]]:
        return [dict(row) for row in (data or [])]


def get_public_repository() -> PublicProjectionRepository:
    return SupabasePublicProjectionRepository()


def _repository() -> PublicProjectionRepository:
    try:
        return get_public_repository()
    except (RuntimeError, ValueError, HTTPError, APIError, SupabaseException) as exc:
        raise HTTPException(status_code=503, detail="Public data is temporarily unavailable") from exc


@router.get("/lakes", response_model=list[PublicLake])
def public_lakes() -> list[PublicLake]:
    try:
        rows = _repository().list_lakes()
    except (HTTPError, APIError, SupabaseException) as exc:
        raise HTTPException(status_code=503, detail="Public data is temporarily unavailable") from exc
    return [PublicLake.model_validate(row) for row in rows]


@router.get("/lakes/{lake_id}/alerts", response_model=list[PublicAlert])
def public_alerts(lake_id: str) -> list[PublicAlert]:
    try:
        rows = _repository().list_alerts(lake_id)
    except (HTTPError, APIError, SupabaseException) as exc:
        raise HTTPException(status_code=503, detail="Public data is temporarily unavailable") from exc
    return [PublicAlert.model_validate(row) for row in rows]


@router.get("/lakes/{lake_id}/patrol-presence", response_model=list[PublicPatrolPresence])
def public_patrol_presence(lake_id: str) -> list[PublicPatrolPresence]:
    try:
        rows = _repository().list_patrol_presence(lake_id)
    except (HTTPError, APIError, SupabaseException) as exc:
        raise HTTPException(status_code=503, detail="Public data is temporarily unavailable") from exc
    return [
        PublicPatrolPresence.model_validate(row)
        for row in rows
    ]
