"""Claimed, idempotent background setup for risk snapshots and zone plans."""

from __future__ import annotations

import asyncio
import logging
import inspect
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from shapely import wkt

from app.lakes.catalog import SUPPORTED_LAKE_IDS, load_reviewed_lake
from app.risk_zones.connectors.king_county import KingCountyIncidentConnector
from app.risk_zones.connectors.king_county_swim_beach import KingCountySwimBeachProxyConnector
from app.risk_zones.plan_builder import RiskDataUnavailable, build_candidate
from app.risk_zones.plan_service import PlanBuildResult, PlanConflict
from app.risk_zones.snapshots import build_fallback_snapshot, build_snapshot

logger = logging.getLogger(__name__)


class RefreshClaim(tuple):
    __slots__ = ()
    def __new__(cls, lake_id: str, claim_token: str | None = None):
        return tuple.__new__(cls, (lake_id, claim_token))
    @property
    def lake_id(self): return self[0]
    @property
    def claim_token(self): return self[1]


def _claim(value) -> RefreshClaim:
    if isinstance(value, dict):
        return RefreshClaim(str(value["lake_id"]), str(value.get("claim_token") or "") or None)
    return RefreshClaim(str(value))


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
        if key not in {
            KingCountyIncidentConnector.connector_key,
            KingCountySwimBeachProxyConnector.connector_key,
        }:
            raise RiskDataUnavailable("unrecognized_reviewed_connector")
        domain = source.get("domain")
        if not isinstance(domain, str):
            raise RiskDataUnavailable("invalid_reviewed_connector")
        if key == KingCountyIncidentConnector.connector_key:
            dataset_id = source.get("dataset_id")
            if not isinstance(dataset_id, str):
                raise RiskDataUnavailable("invalid_reviewed_connector")
            connector = KingCountyIncidentConnector(dataset_id)
        elif key == KingCountySwimBeachProxyConnector.connector_key:
            if domain != KingCountySwimBeachProxyConnector.domain:
                raise RiskDataUnavailable("invalid_reviewed_connector")
            configuration = source.get("source_configuration")
            if not isinstance(configuration, dict):
                raise RiskDataUnavailable("invalid_reviewed_connector")
            locators = configuration.get("locators")
            observations_dataset_id = configuration.get("observations_dataset_id", "mbzm-4r9y")
            sites_dataset_id = configuration.get("sites_dataset_id", "e9bt-i75a")
            if (
                not isinstance(locators, list) or not all(isinstance(locator, str) for locator in locators)
                or observations_dataset_id != "mbzm-4r9y" or sites_dataset_id != "e9bt-i75a"
            ):
                raise RiskDataUnavailable("invalid_reviewed_connector")
            try:
                connector = KingCountySwimBeachProxyConnector(
                    tuple(locators), observations_dataset_id, sites_dataset_id
                )
            except ValueError as error:
                raise RiskDataUnavailable("invalid_reviewed_connector") from error
        return connector.fetch(boundary_wkt, since, self._client_factory(domain))

    @staticmethod
    def _lookback_days(source: dict) -> int:
        if source.get("connector_key") == KingCountySwimBeachProxyConnector.connector_key:
            return 365
        return 30

    def rebuild_lake(self, lake_id: str, claim_token: str | None = None) -> PlanBuildResult:
        if claim_token is not None and not self._repository.claim_is_current(lake_id, claim_token):
            raise RuntimeError("risk refresh claim is no longer current")
        context = self._repository.rebuild_context(lake_id)
        if not context or context.get("lake_id") != lake_id:
            raise RiskDataUnavailable("lake_not_found")
        boundary_wkt = context["shoreline_wkt"]
        shoreline = wkt.loads(boundary_wkt)
        now = self._now()
        sources = tuple(context.get("sources") or ())
        since = now - timedelta(days=min((self._lookback_days(source) for source in sources), default=30))
        if not sources and context.get("data_source_status") == "fallback_coverage":
            snapshot = build_fallback_snapshot(lake_id, context["station_id"], boundary_wkt, since, now)
        else:
            fetches = []
            for source in sources:
                try:
                    if (
                        lake_id in SUPPORTED_LAKE_IDS
                        and source.get("connector_key") == KingCountySwimBeachProxyConnector.connector_key
                    ):
                        configuration = source.get("source_configuration")
                        configured_locators = configuration.get("locators") if isinstance(configuration, dict) else None
                        if configured_locators != list(load_reviewed_lake(lake_id).locators):
                            raise ValueError("schema drift: locator is not reviewed for this lake")
                    fetches.append(self._fetch(
                        source, boundary_wkt, now - timedelta(days=self._lookback_days(source))
                    ))
                except RiskDataUnavailable as error:
                    fetches.append(ValueError(str(error)))
                    break
                except Exception as error:
                    fetches.append(error)
                    break
            snapshot = build_snapshot(lake_id, context["station_id"], tuple(fetches), boundary_wkt, since, now)
        if snapshot.status == "ready":
            has_proxy_source = any(
                source.get("connector_key") == KingCountySwimBeachProxyConnector.connector_key
                for source in sources
            )
            proxy_times = [
                point.occurred_at
                for point in snapshot.points
                if point.category == "access_environment_proxy" and point.is_proxy
                and point.occurred_at is not None
            ]
            source_fresh_through = (
                max(proxy_times, default=None)
                if has_proxy_source
                else max((point.occurred_at for point in snapshot.points if point.occurred_at is not None), default=None)
            )
        else:
            source_fresh_through = None
        snapshot_id = self._repository.persist_snapshot(snapshot, source_fresh_through, claim_token)
        if snapshot.status != "ready":
            raise RiskDataUnavailable(snapshot.failure_reason or "risk_snapshot_unavailable")
        candidate = replace(
            build_candidate(
                snapshot, shoreline, int(context.get("patrol_capacity") or 0),
                int(context.get("safety_reserve") or 0), context.get("prior_plan_id"),
            ),
            snapshot_id=snapshot_id,
        )
        if claim_token is not None and not self._repository.claim_is_current(lake_id, claim_token):
            raise RuntimeError("risk refresh claim is no longer current")
        self._repository.persist_candidate(candidate, claim_token)
        if not self._repository.activate_candidate(lake_id, candidate.plan_id, context.get("prior_plan_id"), claim_token):
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
        self._rebuild_accepts_token = len(inspect.signature(rebuild_lake).parameters) >= 2

    def run_once(self) -> tuple[str, ...]:
        queued = tuple(_claim(value) for value in self._repository.claim_queued_lakes(self._batch_size))
        due = tuple(_claim(value) for value in self._repository.claim_due_source_lakes(self._batch_size))
        completed: list[str] = []
        # A lake can be both manually queued and source-due. Build it once.
        claims_by_lake: dict[str, list[RefreshClaim]] = {}
        for claim in (*queued, *due):
            claims_by_lake.setdefault(claim.lake_id, []).append(claim)
        for lake_id, lake_claims in claims_by_lake.items():
            completed_claim = False
            try:
                self._rebuild_lake(lake_id, lake_claims[0].claim_token) if self._rebuild_accepts_token else self._rebuild_lake(lake_id)
                for claim in lake_claims:
                    if claim.claim_token is None:
                        result = self._repository.complete_refresh(lake_id)
                    else:
                        result = self._repository.complete_refresh(lake_id, claim.claim_token)
                    if result is False:
                        continue
                    completed_claim = True
            except Exception as exc:  # retain the prior active plan, record a safe failure
                logger.warning("risk refresh failed for lake %s: %s", lake_id, exc)
                for claim in lake_claims:
                    if claim.claim_token is None:
                        self._repository.fail_refresh(lake_id, str(exc)[:500] or exc.__class__.__name__)
                    else:
                        self._repository.fail_refresh(lake_id, claim.claim_token, str(exc)[:500] or exc.__class__.__name__)
            else:
                if completed_claim:
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
