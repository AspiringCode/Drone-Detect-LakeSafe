"""Claimed, idempotent background setup for risk snapshots and zone plans."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from shapely import wkt

from app.risk_zones.connectors.king_county import KingCountyIncidentConnector
from app.risk_zones.plan_builder import RiskDataUnavailable, build_candidate
from app.risk_zones.plan_service import PlanBuildResult, PlanConflict
from app.risk_zones.snapshots import build_fallback_snapshot, build_snapshot

logger = logging.getLogger(__name__)


class _SodapyClient:
    """Narrow live client adapter; it never substitutes a fixture on failure."""

    def __init__(self, domain: str) -> None:
        from sodapy import Socrata
        self._client = Socrata(domain, None, timeout=15)

    def get(self, dataset_id: str, **query):
        return self._client.get(dataset_id, **query)


class RiskPlanSetupService:
    """Concrete reviewed-source snapshot/build/persist/activate pipeline."""

    def __init__(self, repository, *, now: Callable[[], datetime] | None = None, client_factory=_SodapyClient) -> None:
        self._repository = repository
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._client_factory = client_factory

    def _fetch(self, source: dict, boundary_wkt: str, since: datetime):
        key = source.get("connector_key")
        if key != KingCountyIncidentConnector.connector_key:
            raise RiskDataUnavailable("unrecognized_reviewed_connector")
        dataset_id = source.get("dataset_id")
        domain = source.get("domain")
        if not isinstance(dataset_id, str) or not isinstance(domain, str):
            raise RiskDataUnavailable("invalid_reviewed_connector")
        connector = KingCountyIncidentConnector(dataset_id)
        return connector.fetch(boundary_wkt, since, self._client_factory(domain))

    def rebuild_lake(self, lake_id: str) -> PlanBuildResult:
        context = self._repository.rebuild_context(lake_id)
        if not context or context.get("lake_id") != lake_id:
            raise RiskDataUnavailable("lake_not_found")
        boundary_wkt = context["shoreline_wkt"]
        shoreline = wkt.loads(boundary_wkt)
        now = self._now()
        since = now - timedelta(days=30)
        sources = tuple(context.get("sources") or ())
        if not sources and context.get("data_source_status") == "fallback_coverage":
            snapshot = build_fallback_snapshot(lake_id, context["station_id"], boundary_wkt, since, now)
        else:
            fetches = tuple(self._fetch(source, boundary_wkt, since) for source in sources)
            snapshot = build_snapshot(lake_id, context["station_id"], fetches, boundary_wkt, since, now)
        source_fresh_through = now if snapshot.status == "ready" else None
        snapshot_id = self._repository.persist_snapshot(snapshot, source_fresh_through)
        if snapshot.status != "ready":
            raise RiskDataUnavailable(snapshot.failure_reason or "risk_snapshot_unavailable")
        candidate = replace(
            build_candidate(
                snapshot, shoreline, int(context.get("patrol_capacity") or 0),
                int(context.get("safety_reserve") or 0), context.get("prior_plan_id"),
            ),
            snapshot_id=snapshot_id,
        )
        self._repository.persist_candidate(candidate)
        if not self._repository.activate_candidate(lake_id, candidate.plan_id, context.get("prior_plan_id")):
            raise PlanConflict("active plan changed; candidate was not activated")
        return PlanBuildResult(
            candidate.plan_id, sum(cell.kind == "hotspot" for cell in candidate.cells), len(candidate.cells), "active",
        )


class RiskRefreshWorker:
    """Process claimed lake work without ever replacing a prior plan on failure.

    The repository claims jobs in the database using ``FOR UPDATE SKIP LOCKED``.
    The builder is responsible for persisting snapshots/candidates atomically;
    exceptions therefore only mark this attempt failed and leave the prior
    active plan untouched.
    """

    def __init__(self, repository, rebuild_lake: Callable[[str], object], *, batch_size: int = 25) -> None:
        self._repository = repository
        self._rebuild_lake = rebuild_lake
        self._batch_size = batch_size

    def run_once(self) -> tuple[str, ...]:
        queued = tuple(self._repository.claim_queued_lakes(self._batch_size))
        due = tuple(self._repository.claim_due_source_lakes(self._batch_size))
        completed: list[str] = []
        # A lake can be both manually queued and source-due. Build it once.
        for lake_id in dict.fromkeys((*queued, *due)):
            try:
                self._rebuild_lake(lake_id)
                self._repository.complete_refresh(lake_id)
            except Exception as exc:  # retain the prior active plan, record a safe failure
                logger.warning("risk refresh failed for lake %s: %s", lake_id, exc)
                self._repository.fail_refresh(lake_id, str(exc)[:500] or exc.__class__.__name__)
            else:
                completed.append(lake_id)
        return tuple(completed)

    async def run_forever(self, interval_seconds: float = 30.0) -> None:
        while True:
            self.run_once()
            await asyncio.sleep(interval_seconds)


def start_worker_task(app, worker: RiskRefreshWorker | None, *, interval_seconds: float = 30.0):
    """Start at most one loop per FastAPI application lifespan."""
    existing = getattr(app.state, "risk_refresh_task", None)
    if existing is not None and not existing.done():
        return existing
    if worker is None:
        app.state.risk_refresh_task = None
        return None
    task = asyncio.create_task(worker.run_forever(interval_seconds))
    app.state.risk_refresh_task = task
    return task


async def cancel_worker_task(app) -> None:
    task = getattr(app.state, "risk_refresh_task", None)
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    app.state.risk_refresh_task = None
