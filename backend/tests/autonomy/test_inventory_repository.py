from __future__ import annotations

import pytest

from app.autonomy.inventory_repository import InventoryWorkflowConflict, SupabaseInventoryRepository


class Rpc:
    def __init__(self, data=None, error: Exception | None = None) -> None:
        self.data = data
        self.error = error

    def execute(self):
        if self.error:
            raise self.error
        return type("Response", (), {"data": self.data})()


class Client:
    def __init__(self, data=None, error: Exception | None = None) -> None:
        self.data = data
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    def rpc(self, name: str, params: dict):
        self.calls.append((name, params))
        return Rpc(self.data, self.error)


def test_repository_uses_lake_scoped_circulation_rpc_and_preserves_reconciliation_id():
    client = Client({"inventory_id": "d1", "reconciliation_id": "r1"})
    result = SupabaseInventoryRepository(client).set_simulated_circulation("s1", "d1", "lake-1", False, "return", "u1", "r1")
    assert result["reconciliation_id"] == "r1"
    assert client.calls == [("request_simulated_circulation", {"p_station_id": "s1", "p_inventory_id": "d1", "p_lake_id": "lake-1", "p_eligible": False, "p_reason": "return", "p_actor_user_id": "u1", "p_reconciliation_id": "r1"})]


def test_repository_translates_database_allowance_and_constraint_errors_to_conflict():
    with pytest.raises(InventoryWorkflowConflict):
        SupabaseInventoryRepository(Client(error=RuntimeError("23514 allowance exceeded"))).register_simulated_inventory("s1", 2)
