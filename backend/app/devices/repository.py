"""Service-only persistence for real device credentials."""

from __future__ import annotations

from functools import lru_cache
from datetime import datetime, timezone

from app.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from app.devices.auth import DeviceAuthRepository


class DeviceRepositoryError(RuntimeError):
    pass


class SupabaseDeviceRepository(DeviceAuthRepository):
    def __init__(self, client=None) -> None:
        if client is None:
            if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
                raise DeviceRepositoryError("Device gateway is unavailable")
            from app.supabase_transport import create_server_client as create_client
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

    def list_real(self, station_id: str) -> list[dict]:
        return self._real_inventory("station_id", station_id)

    def real_on_lake(self, lake_id: str) -> list[dict]:
        return self._real_inventory("lake_id", lake_id)

    def _real_inventory(self, column: str, value: str) -> list[dict]:
        try:
            rows = self._client.table("drone_inventory").select(
                "inventory_id,lake_id,lifecycle,battery_percent,health,connectivity,updated_at,drone_credentials(manufacturer,serial,credential_state),drone_heartbeats(received_at)"
            ).eq(column, value).eq("source", "real").neq("lifecycle", "retired").order("created_at").order(
                "received_at", desc=True, foreign_table="drone_heartbeats"
            ).limit(1, foreign_table="drone_heartbeats").execute().data or []
        except Exception as exc:
            raise DeviceRepositoryError("Device inventory is unavailable") from exc
        drones = []
        for row in rows:
            credential = row.pop("drone_credentials", None) or {}
            if isinstance(credential, list):  # one-to-one, but PostgREST may still wrap it
                credential = credential[0] if credential else {}
            # Inventory battery/health columns hold schema defaults until a heartbeat lands, so the UI needs this to tell them apart.
            heartbeats = row.pop("drone_heartbeats", None) or []
            drones.append({**row, "manufacturer": credential.get("manufacturer"), "serial": credential.get("serial"), "credential_state": credential.get("credential_state"),
                           "last_heartbeat_at": heartbeats[0].get("received_at") if heartbeats else None})
        return drones

    def attach_real_to_lake(self, station_id: str, drone_id: str, lake_id: str | None) -> dict:
        # The schema ties lake_id to the circulating lifecycle; detaching returns the drone to available.
        try:
            if lake_id is not None and self.lake_station_id(lake_id) != station_id:
                raise DeviceRepositoryError("Lake is not part of this station")
            rows = self._client.table("drone_inventory").update({
                "lake_id": lake_id, "lifecycle": "circulating" if lake_id else "available", "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("inventory_id", drone_id).eq("station_id", station_id).eq("source", "real").neq("lifecycle", "retired").execute().data
        except DeviceRepositoryError:
            raise
        except Exception as exc:
            raise DeviceRepositoryError("Device inventory cannot be changed") from exc
        if not rows:
            raise DeviceRepositoryError("Real drone not found")
        return {"inventory_id": drone_id, "lake_id": lake_id, "lifecycle": rows[0]["lifecycle"]}

    def save_real_alert(self, station_id: str, lake_id: str, alert) -> None:
        try:
            self._client.table("operational_alerts").insert({
                "alert_id": alert.alert_id, "station_id": station_id, "lake_id": lake_id,
                "occurred_at": alert.created_at.isoformat(),
                "precise_location": f"SRID=4326;POINT({alert.location.lon} {alert.location.lat})",
                "category": alert.detection_mode, "status": "active", "source": "real",
                "hardware_ref": alert.drone_id, "thermal_clip_ref": alert.thermal_clip_ref,
            }).execute()
        except Exception as exc:
            raise DeviceRepositoryError("Alert could not be saved") from exc

    def active_real_alerts(self, lake_id: str, limit: int = 20) -> list:
        """Saved real alerts for one lake, oldest first, so a restarted API shows them again."""
        from shapely import wkb
        from app.models import Alert, LatLon
        try:
            rows = self._client.table("operational_alerts").select(
                "alert_id,occurred_at,precise_location,category,hardware_ref,thermal_clip_ref"
            ).eq("lake_id", lake_id).eq("source", "real").eq("status", "active").order("occurred_at", desc=True).limit(limit).execute().data or []
        except Exception as exc:
            raise DeviceRepositoryError("Alerts are unavailable") from exc
        alerts = []
        for row in reversed(rows):
            point = wkb.loads(bytes.fromhex(row["precise_location"]))  # PostgREST returns PostGIS geometry as EWKB hex
            alerts.append(Alert(row["alert_id"], datetime.fromisoformat(row["occurred_at"]), LatLon(point.y, point.x), row["category"],
                                row.get("hardware_ref") or "unknown", row.get("thermal_clip_ref"), True, "real", None))
        return alerts

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

    def real_inventory(self, drone_id: str) -> dict | None:
        try:
            row = self._client.table("drone_inventory").select("inventory_id,station_id,lake_id,source").eq("inventory_id", drone_id).eq("source", "real").maybe_single().execute().data
            if not isinstance(row, dict):
                return None
            credential = self.active_credential(drone_id)
            return {**row, "credential_state": credential.get("credential_state") if credential else "revoked"}
        except Exception as exc:
            raise DeviceRepositoryError("Device gateway is unavailable") from exc

    def lake_station_id(self, lake_id: str) -> str | None:
        try:
            row = self._client.table("lakes").select("station_id").eq("lake_id", lake_id).maybe_single().execute().data
            return str(row["station_id"]) if isinstance(row, dict) and row.get("station_id") else None
        except Exception as exc:
            raise DeviceRepositoryError("Device gateway is unavailable") from exc

    def command_for_ack(self, command_id: str) -> dict | None:
        try:
            row = self._client.table("command_outbox").select("command_id,inventory_id,station_id,lake_id,desired_state_version,command_type,status,payload").eq("command_id", command_id).maybe_single().execute().data
            if not isinstance(row, dict):
                return None
            payload = row.get("payload") or {}
            return {"command_id": str(row["command_id"]), "drone_id": str(row["inventory_id"]), "station_id": str(row["station_id"]), "lake_id": str(row["lake_id"]), "desired_state_version": int(row["desired_state_version"]), "command_type": row.get("command_type"), "status": row.get("status"), "plan_id": payload.get("plan_id")}
        except Exception as exc:
            raise DeviceRepositoryError("Device gateway is unavailable") from exc

    def insert_acknowledgement(self, drone_id: str, command_id: str, sequence: int, plan_id: str | None, version: int, status: str, detail: str | None) -> bool:
        try:
            return self._client.rpc("record_real_command_acknowledgement", {"p_drone_id": drone_id, "p_command_id": command_id, "p_sequence": sequence, "p_plan_id": plan_id, "p_version": version, "p_status": status, "p_detail": detail}).execute().data is True
        except Exception as exc:
            raise DeviceRepositoryError("Device gateway is unavailable") from exc

    def advance_acknowledged_version(self, drone_id: str, version: int, command_id: str) -> bool:
        try:
            return self._client.rpc("advance_real_command_acknowledgement", {"p_drone_id": drone_id, "p_command_id": command_id, "p_version": version}).execute().data is True
        except Exception as exc:
            raise DeviceRepositoryError("Device gateway is unavailable") from exc

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
