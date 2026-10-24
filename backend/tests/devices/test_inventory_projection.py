from types import SimpleNamespace

import pytest

from app.devices.repository import SupabaseDeviceRepository


@pytest.mark.parametrize("state", ["active", "revoked"])
@pytest.mark.parametrize("wrapped", [False, True])
def test_inventory_preserves_credential_state_for_patrol_authorization(state, wrapped):
    credential = {"manufacturer": "Test", "serial": "FLOW-TEST", "credential_state": state}
    class Query:
        def table(self, *_): return self
        def select(self, *_): return self
        def eq(self, *_): return self
        def neq(self, *_): return self
        def order(self, *_): return self
        def execute(self): return SimpleNamespace(data=[{"inventory_id": "test-drone", "drone_credentials": [credential] if wrapped else credential}])
    [drone] = SupabaseDeviceRepository(Query()).list_real("station-1")
    assert drone["credential_state"] == state
    assert drone["serial"] == "FLOW-TEST"
    assert "drone_credentials" not in drone
