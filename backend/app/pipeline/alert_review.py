"""Service-only durable alert review; review never dispatches responders."""
from functools import lru_cache
from app.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from app.supabase_transport import create_server_client as create_client


class AlertReviewUnavailable(RuntimeError):
    pass


class SupabaseAlertReviewRepository:
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            raise AlertReviewUnavailable("Alert review service is unavailable")
        self._client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    def review(self, lake_id: str, alert_id: str, actor: str) -> dict | None:
        try:
            result = self._client.rpc("review_operational_alert", {
                "p_lake_id": lake_id, "p_alert_id": alert_id, "p_actor": actor,
            }).execute().data
            if isinstance(result, list):
                result = result[0] if result else None
            return result if isinstance(result, dict) and result else None
        except Exception as exc:
            raise AlertReviewUnavailable("Alert review service is unavailable") from exc

    def reviewed_alerts(self, lake_id: str) -> dict[str, str]:
        try:
            rows = self._client.table("operational_alerts").select("alert_id,reviewed_at").eq("lake_id", lake_id).eq("source", "real").not_.is_("reviewed_at", "null").execute().data or []
            return {row["alert_id"]: row["reviewed_at"] for row in rows}
        except Exception as exc:
            raise AlertReviewUnavailable("Alert review service is unavailable") from exc


@lru_cache(maxsize=1)
def get_alert_review_repository():
    return SupabaseAlertReviewRepository()
