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
        for lake_id in lake_ids:
            self._autonomy.reconcile_lake(lake_id, "heartbeat_expired")
        return lake_ids


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
