"""Service-only persistence for real device credentials."""

from __future__ import annotations

from functools import lru_cache
from datetime import datetime

from app.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from app.devices.auth import DeviceAuthRepository


class DeviceRepositoryError(RuntimeError):
    pass


class SupabaseDeviceRepository(DeviceAuthRepository):
    def __init__(self, client=None) -> None:
        if client is None:
            if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
                raise DeviceRepositoryError("Device gateway is unavailable")
            from supabase import create_client
            client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        self._client = client

    def active_credential(self, drone_id: str) -> dict | None:
        try:
            return self._client.table("drone_credentials").select(
                "credential_id,drone_id,station_id,public_key,credential_state"
            ).eq("drone_id", drone_id).eq("credential_state", "active").maybe_single().execute().data
        except Exception as exc:
            raise DeviceRepositoryError("Device gateway is unavailable") from exc

    def claim_sequence(self, drone_id: str, sequence: int) -> bool:
        try:
            data = self._client.rpc("claim_drone_sequence", {"p_drone_id": drone_id, "p_sequence": sequence}).execute().data
            return data is True
        except Exception as exc:
            raise DeviceRepositoryError("Device gateway is unavailable") from exc

    def register_real(self, station_id: str, manufacturer: str, serial: str, public_key: str, actor_user_id: str) -> dict:
        return self._one("register_real_drone", {"p_station_id": station_id, "p_manufacturer": manufacturer, "p_serial": serial, "p_public_key": public_key, "p_actor_user_id": actor_user_id})

    def retire_real(self, station_id: str, drone_id: str, actor_user_id: str) -> dict:
        return self._one("retire_real_drone", {"p_station_id": station_id, "p_drone_id": drone_id, "p_actor_user_id": actor_user_id})

    def record_heartbeat(self, principal, heartbeat, received_at: datetime) -> dict:
        return self._one("record_real_heartbeat", {
            "p_drone_id": principal.drone_id, "p_station_id": principal.station_id,
            "p_credential_id": principal.credential_id, "p_battery_percent": heartbeat.battery_percent,
            "p_sequence": principal.sequence,
            "p_health": heartbeat.health, "p_connected": heartbeat.connected,
            "p_received_at": received_at.isoformat(),
        })

    def expire_stale_eligible_real(self, now: datetime, ttl_seconds: int) -> tuple[str, ...]:
        try:
            data = self._client.rpc("expire_stale_real_capacity", {"p_now": now.isoformat(), "p_ttl_seconds": ttl_seconds}).execute().data or []
            return tuple(str(row["lake_id"]) for row in data if isinstance(row, dict) and isinstance(row.get("lake_id"), str))
        except Exception as exc:
            raise DeviceRepositoryError("Device gateway is unavailable") from exc

    def request_real_capacity_reconciliation(self, lake_id: str, trigger: str) -> None:
        try:
            self._client.rpc("request_real_capacity_reconciliation", {"p_lake_id": lake_id, "p_trigger": trigger}).execute()
        except Exception as exc:
            raise DeviceRepositoryError("Device gateway is unavailable") from exc

    def reconcile_real_capacity(self, lake_id: str, trigger: str) -> None:
        try:
            self._client.rpc("reconcile_real_capacity", {"p_lake_id": lake_id, "p_trigger": trigger}).execute()
        except Exception as exc:
            raise DeviceRepositoryError("Real capacity reconciliation is unavailable") from exc

    def claim_real_capacity_reconciliations(self, limit: int = 20, lease_seconds: int = 30) -> tuple[dict, ...]:
        try:
            return tuple(self._client.rpc("claim_real_capacity_reconciliations", {"p_limit": limit, "p_lease_seconds": lease_seconds}).execute().data or [])
        except Exception as exc:
            raise DeviceRepositoryError("Device gateway is unavailable") from exc

    def complete_real_capacity_reconciliation(self, item: dict) -> bool:
        try:
            return self._client.rpc("complete_real_capacity_reconciliation", {"p_reconciliation_id": item["reconciliation_id"], "p_claim_token": item["claim_token"], "p_generation": item["generation"]}).execute().data is True
        except Exception as exc:
            raise DeviceRepositoryError("Device gateway is unavailable") from exc

    def release_real_capacity_reconciliation(self, item: dict) -> bool:
        try:
            return self._client.rpc("release_real_capacity_reconciliation", {"p_reconciliation_id": item["reconciliation_id"], "p_claim_token": item["claim_token"]}).execute().data is True
        except Exception as exc:
            raise DeviceRepositoryError("Device gateway is unavailable") from exc

    def _one(self, name: str, params: dict) -> dict:
        try:
            data = self._client.rpc(name, params).execute().data
        except Exception as exc:
            raise DeviceRepositoryError("Device inventory cannot be changed") from exc
        if isinstance(data, list): data = data[0] if data else None
        if not isinstance(data, dict): raise DeviceRepositoryError("Device inventory cannot be changed")
        return data


@lru_cache(maxsize=1)
def get_device_repository() -> SupabaseDeviceRepository:
    return SupabaseDeviceRepository()
