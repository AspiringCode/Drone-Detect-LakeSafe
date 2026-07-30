"""Safety policy state for autonomous real fleets, never flight steering."""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from datetime import datetime, timezone
from typing import Literal, Protocol

from app.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from app.stations.models import AuditEventCreate
from app.stations.repository import get_workflow_repository


RealAutonomyState = Literal["paused", "pending_ack", "active", "degraded", "safe_return_requested", "gateway_unavailable"]


@dataclass(frozen=True)
class RealFleetStatus:
    autonomy: RealAutonomyState
    active_assignments: tuple[str, ...] = ()
    pending_assignments: tuple[str, ...] = ()
    last_acknowledged_versions: dict[str, int] | None = None

    def as_dict(self) -> dict:
        return {
            "autonomy": self.autonomy,
            "active_assignments": self.active_assignments,
            "pending_assignments": self.pending_assignments,
            "last_acknowledged_versions": self.last_acknowledged_versions or {},
        }


def classify_real_fleet_status(current: RealFleetStatus, *, expired_drone_ids: tuple[str, ...], safe_return_required: bool) -> RealFleetStatus:
    """Expire only unacknowledged capacity; never claim its desired state active."""
    expired = set(expired_drone_ids)
    pending = tuple(drone_id for drone_id in current.pending_assignments if drone_id not in expired)
    if safe_return_required and expired:
        return replace(current, autonomy="safe_return_requested", pending_assignments=pending)
    if expired:
        return replace(current, autonomy="degraded", pending_assignments=pending)
    if pending and current.autonomy == "active":
        return replace(current, autonomy="pending_ack")
    return replace(current, pending_assignments=pending)


def mark_gateway_unavailable(current: RealFleetStatus) -> RealFleetStatus:
    return replace(current, autonomy="gateway_unavailable")


def request_safe_return(current: RealFleetStatus) -> RealFleetStatus:
    return replace(current, autonomy="safe_return_requested")


class SafetyRepository(Protocol):
    def lake_belongs_to_station(self, station_id: str, lake_id: str) -> bool: ...
    def real_fleet_status(self, station_id: str, lake_id: str) -> dict: ...
    def set_real_autonomy(self, station_id: str, lake_id: str, enabled: bool, reason: str, actor_user_id: str) -> dict: ...
    def request_safe_return(self, station_id: str, lake_id: str, reason: str, actor_user_id: str) -> dict: ...
    def append_audit(self, event: AuditEventCreate) -> None: ...


class SupabaseSafetyRepository:
    """Service-only repository. Database functions own policy and outbox writes."""

    def __init__(self, client=None) -> None:
        if client is None:
            if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
                raise RuntimeError("Real fleet safety service is unavailable")
            from supabase import create_client
            client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        self._client = client

    def lake_belongs_to_station(self, station_id: str, lake_id: str) -> bool:
        row = self._client.table("lakes").select("station_id").eq("lake_id", lake_id).maybe_single().execute().data
        return isinstance(row, dict) and str(row.get("station_id")) == station_id

    def real_fleet_status(self, station_id: str, lake_id: str) -> dict:
        """Return operational state only; hardware identities and secrets stay server-side."""
        try:
            policy = self._client.table("real_fleet_safety_policies").select(
                "autonomy_state"
            ).eq("station_id", station_id).eq("lake_id", lake_id).maybe_single().execute().data
            fleet_policy = self._client.table("station_fleet_policies").select(
                "minimum_battery_percent"
            ).eq("station_id", station_id).maybe_single().execute().data
            inventory = self._client.table("drone_inventory").select(
                "inventory_id,desired_state_version,acknowledged_state_version,health,connectivity,maintenance_due,battery_percent"
            ).eq("station_id", station_id).eq("lake_id", lake_id).eq("source", "real").execute().data or []
            ids = [str(row["inventory_id"]) for row in inventory if isinstance(row, dict) and row.get("inventory_id")]
            heartbeats = self._client.table("drone_heartbeats").select("drone_id,received_at").in_("drone_id", ids).order("received_at", desc=True).execute().data if ids else []
        except Exception as exc:
            raise RuntimeError("Real fleet status is unavailable") from exc
        newest: dict[str, datetime] = {}
        for row in heartbeats or []:
            if not isinstance(row, dict) or not isinstance(row.get("drone_id"), str) or not isinstance(row.get("received_at"), str):
                continue
            try:
                received = datetime.fromisoformat(row["received_at"].replace("Z", "+00:00"))
            except ValueError:
                continue
            newest.setdefault(row["drone_id"], received)
        now = datetime.now(timezone.utc)
        ages = [max(0, int((now - received).total_seconds())) for received in newest.values()]
        desired = max((int(row.get("desired_state_version") or 0) for row in inventory if isinstance(row, dict)), default=0)
        acknowledged = max((int(row.get("acknowledged_state_version") or 0) for row in inventory if isinstance(row, dict)), default=0)
        minimum_battery = int(fleet_policy.get("minimum_battery_percent") or 30) if isinstance(fleet_policy, dict) else 30
        eligible = bool(inventory) and all(
            row.get("health") == "healthy" and row.get("connectivity") == "connected"
            and not bool(row.get("maintenance_due")) and int(row.get("battery_percent") or 0) >= minimum_battery
            and str(row.get("inventory_id")) in newest
            for row in inventory if isinstance(row, dict)
        )
        state = policy.get("autonomy_state") if isinstance(policy, dict) else "paused"
        if state not in {"paused", "pending_ack", "active", "degraded", "safe_return_requested", "gateway_unavailable"}:
            state = "paused"
        return {
            "station_id": station_id, "lake_id": lake_id, "source": "real", "autonomy": state,
            "heartbeat_age_seconds": min(ages) if ages else None, "eligible": eligible if inventory else None,
            "desired_state_version": desired, "acknowledged_state_version": acknowledged,
            "active_assignments": [], "pending_assignments": [],
        }

    def set_real_autonomy(self, station_id: str, lake_id: str, enabled: bool, reason: str, actor_user_id: str) -> dict:
        return self._one("set_real_fleet_autonomy", {
            "p_station_id": station_id, "p_lake_id": lake_id, "p_enabled": enabled,
            "p_reason": reason, "p_actor_user_id": actor_user_id,
        })

    def request_safe_return(self, station_id: str, lake_id: str, reason: str, actor_user_id: str) -> dict:
        return self._one("request_real_fleet_safe_return", {
            "p_station_id": station_id, "p_lake_id": lake_id,
            "p_reason": reason, "p_actor_user_id": actor_user_id,
        })

    def append_audit(self, event: AuditEventCreate) -> None:
        get_workflow_repository().append_audit(event)

    def _one(self, name: str, values: dict) -> dict:
        data = self._client.rpc(name, values).execute().data
        if isinstance(data, list):
            data = data[0] if data else None
        if not isinstance(data, dict):
            raise RuntimeError("Real fleet safety change cannot be applied")
        return data


@lru_cache(maxsize=1)
def get_safety_repository() -> SupabaseSafetyRepository:
    return SupabaseSafetyRepository()


__all__ = ["RealFleetStatus", "SafetyRepository", "SupabaseSafetyRepository", "classify_real_fleet_status", "get_safety_repository", "mark_gateway_unavailable", "request_safe_return"]
