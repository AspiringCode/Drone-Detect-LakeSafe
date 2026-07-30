"""Service-only persistence for real device credentials."""

from __future__ import annotations

from functools import lru_cache

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
