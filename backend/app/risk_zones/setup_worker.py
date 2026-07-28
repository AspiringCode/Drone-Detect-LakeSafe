"""Claimed, idempotent background setup for risk snapshots and zone plans."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


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
