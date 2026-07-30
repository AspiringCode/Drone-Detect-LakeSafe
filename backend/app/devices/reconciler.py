"""Bridge from durable real-capacity jobs to the autonomy service."""

from __future__ import annotations


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
    """Only start consumers when the actual reconciliation pipeline exists."""
    return callable(getattr(getattr(application, "state", None), "real_autonomy_service", None) and getattr(application.state.real_autonomy_service, "reconcile_lake", None))
