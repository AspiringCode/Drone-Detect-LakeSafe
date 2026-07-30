"""Bridge from durable real-capacity jobs to the autonomy service."""

from __future__ import annotations

from app.config import REAL_GATEWAY_SIGNING_KEY_REF, REAL_GATEWAY_URL
from app.hardware_gateway import EnvironmentSecretProvider, HttpRealGatewayClient


class RealCapacityReconciler:
    """Invoke the configured autonomy service; never acknowledge a wake-up."""

    def __init__(self, application) -> None:
        self._application = application

    def reconcile_lake(self, lake_id: str, trigger: str, expected_plan_id: str | None = None) -> object:
        service = getattr(self._application.state, "real_autonomy_service", None)
        if service is None or not callable(getattr(service, "reconcile_lake", None)):
            raise RuntimeError("real autonomy reconciliation service is unavailable")
        return service.reconcile_lake(lake_id, trigger, expected_plan_id)


def has_real_autonomy_service(application) -> bool:
    """Only start consumers when the real-only transport is configured."""
    if not REAL_GATEWAY_URL or not REAL_GATEWAY_SIGNING_KEY_REF:
        return False
    return callable(getattr(getattr(application, "state", None), "real_autonomy_service", None) and getattr(application.state.real_autonomy_service, "reconcile_lake", None))


class RealAutonomyPublisher:
    """Publishes precomputed real commands; it never accepts steering input."""

    def __init__(self, publisher) -> None:
        self._publisher = publisher

    def reconcile_lake(self, lake_id: str, trigger: str, expected_plan_id: str | None = None) -> tuple[str, ...]:
        del lake_id, trigger, expected_plan_id
        return self._publisher.publish_pending()


def configure_real_autonomy_service(application, *, device_repository, secret_provider=None, gateway=None, autonomy_repository=None) -> bool:
    """Install the real-only publisher only after all server secrets resolve."""
    application.state.real_autonomy_service = None
    if not REAL_GATEWAY_URL or not REAL_GATEWAY_SIGNING_KEY_REF:
        return False
    provider = secret_provider or EnvironmentSecretProvider(configured_reference=REAL_GATEWAY_SIGNING_KEY_REF)
    if provider.resolve(REAL_GATEWAY_SIGNING_KEY_REF) is None:
        return False
    try:
        from app.autonomy.adapters.real import RealAdapter
        from app.autonomy.outbox import OutboxPublisher
        from app.autonomy.repository import SupabaseAutonomyRepository
        repository = autonomy_repository or SupabaseAutonomyRepository(device_repository._client)
        adapter = RealAdapter(
            device_repository, gateway or HttpRealGatewayClient(), gateway_url=REAL_GATEWAY_URL,
            signing_key_ref=REAL_GATEWAY_SIGNING_KEY_REF, secret_provider=provider,
        )
        application.state.real_autonomy_service = RealAutonomyPublisher(OutboxPublisher(repository, adapter))
    except (AttributeError, RuntimeError, ValueError):
        application.state.real_autonomy_service = None
        return False
    return True
