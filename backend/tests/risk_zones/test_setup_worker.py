from __future__ import annotations

from app.risk_zones.setup_worker import RiskRefreshWorker


class Repository:
    def __init__(self) -> None:
        self.queued = ["lake-1"]
        self.due = ["lake-2"]
        self.completed: list[str] = []
        self.failed: list[tuple[str, str]] = []

    def claim_queued_lakes(self, limit: int):
        values, self.queued = self.queued[:limit], self.queued[limit:]
        return tuple(values)

    def claim_due_source_lakes(self, limit: int):
        values, self.due = self.due[:limit], self.due[limit:]
        return tuple(values)

    def complete_refresh(self, lake_id: str) -> None:
        self.completed.append(lake_id)

    def fail_refresh(self, lake_id: str, reason: str) -> None:
        self.failed.append((lake_id, reason))


def test_queued_lake_gets_an_initial_plan() -> None:
    repository = Repository()
    built: list[str] = []
    worker = RiskRefreshWorker(repository, lambda lake_id: built.append(lake_id))

    assert worker.run_once() == ("lake-1", "lake-2")
    assert built == ["lake-1", "lake-2"]
    assert repository.completed == ["lake-1", "lake-2"]


def test_failed_refresh_keeps_work_for_a_later_attempt_without_raising() -> None:
    repository = Repository()
    worker = RiskRefreshWorker(repository, lambda lake_id: (_ for _ in ()).throw(ValueError("source unavailable")))

    assert worker.run_once() == ()
    assert repository.failed == [("lake-1", "source unavailable"), ("lake-2", "source unavailable")]
