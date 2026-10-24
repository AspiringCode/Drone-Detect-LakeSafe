"""Backend-only persistence boundary for simulated fleet inventory."""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from app.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL


class InventoryWorkflowConflict(RuntimeError):
    """Inventory does not exist, is unsafe, or cannot transition."""


class InventoryRepository(Protocol):
    def register_simulated_inventory(self, station_id: str, count: int) -> list[dict]: ...
    def set_simulated_circulation(self, station_id: str, inventory_id: str, lake_id: str, eligible: bool, reason: str, actor_user_id: str, reconciliation_id: str) -> dict: ...
    def fleet(self, station_id: str, lake_id: str | None = None) -> list[dict]: ...


class SupabaseInventoryRepository:
    """Uses service-only SQL RPCs; no client can mutate inventory directly."""

    def __init__(self, client=None) -> None:
        if client is None:
            if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
                raise RuntimeError("Supabase service credentials are not configured")
            from app.supabase_transport import create_server_client as create_client
            client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        self._client = client

    def register_simulated_inventory(self, station_id: str, count: int) -> list[dict]:
        result = self._rpc("register_simulated_inventory", {"p_station_id": station_id, "p_count": count}, "Simulated inventory cannot be registered")
        if not isinstance(result, list) or not all(isinstance(item, dict) for item in result):
            raise InventoryWorkflowConflict("Simulated inventory cannot be registered")
        return result

    def set_simulated_circulation(self, station_id: str, inventory_id: str, lake_id: str, eligible: bool, reason: str, actor_user_id: str, reconciliation_id: str) -> dict:
        return self._one("request_simulated_circulation", {
            "p_station_id": station_id, "p_inventory_id": inventory_id,
            "p_lake_id": lake_id, "p_eligible": eligible, "p_reason": reason,
            "p_actor_user_id": actor_user_id, "p_reconciliation_id": reconciliation_id,
        }, "Simulated circulation cannot be changed")

    def fleet(self, station_id: str, lake_id: str | None = None) -> list[dict]:
        if lake_id is None:
            raise InventoryWorkflowConflict("A lake-scoped fleet is required")
        try:
            lake = self._client.table("lakes").select("station_id").eq("lake_id", lake_id).maybe_single().execute().data
        except Exception as exc:
            raise InventoryWorkflowConflict("Fleet cannot be loaded") from exc
        if not isinstance(lake, dict) or str(lake.get("station_id")) != station_id:
            raise InventoryWorkflowConflict("Lake does not belong to station")
        query = self._client.table("drone_inventory").select(
            "inventory_id,station_id,lake_id,source,lifecycle,battery_percent,health,connectivity,maintenance_due,desired_state_version,acknowledged_state_version"
        ).eq("station_id", station_id).eq("source", "simulated").order("created_at")
        query = query.eq("lake_id", lake_id)
        try:
            return query.execute().data or []
        except Exception as exc:
            raise InventoryWorkflowConflict("Fleet cannot be loaded") from exc

    def _one(self, name: str, params: dict, message: str) -> dict:
        data = self._rpc(name, params, message)
        if isinstance(data, list):
            data = data[0] if data else None
        if not isinstance(data, dict):
            raise InventoryWorkflowConflict(message)
        return data

    def _rpc(self, name: str, params: dict, message: str):
        try:
            return self._client.rpc(name, params).execute().data
        except Exception as exc:
            # Database constraints are deliberately not reflected to callers:
            # allowance, ownership, and transition failures all become 409.
            raise InventoryWorkflowConflict(message) from exc


@lru_cache(maxsize=1)
def get_inventory_repository() -> SupabaseInventoryRepository:
    return SupabaseInventoryRepository()
