"""Expiry monitor for real-device capacity."""

from __future__ import annotations

from datetime import datetime, timezone
import asyncio
from typing import Protocol

from app.config import REAL_HEARTBEAT_TTL_SECONDS
from app.devices.heartbeat import LakeReconciler


class HeartbeatExpiryRepository(Protocol):
    def expire_stale_eligible_real(self, now: datetime, ttl_seconds: int) -> tuple[str, ...]: ...


class HeartbeatMonitor:
    def __init__(self, repository: HeartbeatExpiryRepository, autonomy: LakeReconciler, *, ttl_seconds: int = REAL_HEARTBEAT_TTL_SECONDS) -> None:
        self._repository = repository
        self._autonomy = autonomy
        self._ttl_seconds = ttl_seconds

    def scan(self, now: datetime | None = None) -> tuple[str, ...]:
        lake_ids = tuple(dict.fromkeys(self._repository.expire_stale_eligible_real(now or datetime.now(timezone.utc), self._ttl_seconds)))
        self.drain_reconciliations()
        return lake_ids

    def drain_reconciliations(self) -> tuple[str, ...]:
        completed: list[str] = []
        for item in self._repository.claim_real_capacity_reconciliations():
            try:
                self._autonomy.reconcile_lake(item["lake_id"], item["trigger"])
                if self._repository.complete_real_capacity_reconciliation(item):
                    completed.append(item["lake_id"])
            except Exception:
                self._repository.release_real_capacity_reconciliation(item)
        return tuple(completed)


async def monitor_loop(monitor: HeartbeatMonitor, *, interval_seconds: float = 5.0) -> None:
    """Run expiry checks without letting one transient gateway error kill it."""
    while True:
        try:
            monitor.scan()
        except Exception:
            # The next signed heartbeat or scan will recover capacity.  Details
            # belong in server telemetry, never in a device response.
            pass
        await asyncio.sleep(interval_seconds)
