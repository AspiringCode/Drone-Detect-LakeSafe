import base64
import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import shape
from shapely.ops import unary_union

from app.coordination.assignment import haversine_m
from app.main import app, lake_runtimes, simulated_fleet
from app.risk_zones.shoreline import load_lake_polygon


LAKE_ID = "lake-sammamish"
SUPPORTED_LAKE_IDS = ("lake-sammamish", "lake-pine", "lake-beaver")


def _read_headers(monkeypatch):
    monkeypatch.setattr("app.main.verify_supabase_jwt", lambda token: {"sub": "owner", "aal": "aal2", "amr": [{"method": "totp", "timestamp": time.time()}]})
    return {"Authorization": "Bearer signed-token"}


class FakeAccessRepository:
    def load_principal_state(self, user_id):
        station_id = "station-1" if user_id == "owner" else "station-2"
        roles = ["viewer", "station_admin", "safety_supervisor"] if user_id == "owner" else ["viewer"]
        return {"account_class": "officer", "verification_status": "verified", "memberships": [{
            "station_id": station_id, "station_name": "Demo", "membership_status": "active", "roles": roles,
        }]}

    def lake_station_id(self, lake_id):
        return "station-1" if lake_id in SUPPORTED_LAKE_IDS else None


@pytest.fixture(autouse=True)
def fake_access_repository(monkeypatch):
    monkeypatch.setattr("app.main.get_access_repository", lambda: FakeAccessRepository())
    monkeypatch.setattr("app.main.get_alert_review_repository", lambda: SimpleNamespace(reviewed_alerts=lambda _: {}))


@pytest.fixture
def running_simulation():
    runtime = lake_runtimes[LAKE_ID]
    runtime.engine.set_fleet(simulated_fleet(runtime))
    yield runtime
    runtime.engine.set_fleet([])


@pytest.mark.parametrize("lake_id", SUPPORTED_LAKE_IDS)
def test_get_riskmap_returns_feature_collection_for_each_local_runtime(monkeypatch, lake_id):
    client = TestClient(app)
    response = client.get(f"/api/lakes/{lake_id}/riskmap", headers=_read_headers(monkeypatch))
    assert response.status_code == 200
    assert response.json()["type"] == "FeatureCollection"


@pytest.mark.parametrize("path", [
    f"/api/lakes/{LAKE_ID}/riskmap",
    f"/api/lakes/{LAKE_ID}/drones",
    f"/api/lakes/{LAKE_ID}/alerts",
])
def test_operational_read_routes_reject_anonymous_clients(path):
    assert TestClient(app).get(path).status_code == 401


def test_demo_trigger_creates_alert_retrievable(monkeypatch, running_simulation):
    monkeypatch.setattr("app.main.verify_supabase_jwt", lambda token: {"sub": "owner", "aal": "aal2"})
    client = TestClient(app)
    response = client.post(f"/api/lakes/{LAKE_ID}/demo/trigger", headers={"Authorization": "Bearer signed-token"})
    assert response.status_code == 200
    alert_id = response.json()["alert_id"]
    alerts = client.get(f"/api/lakes/{LAKE_ID}/alerts", headers={"Authorization": "Bearer signed-token"}).json()
    assert any(alert["alert_id"] == alert_id for alert in alerts)


def test_positions_ws_receives_state_with_source(monkeypatch, running_simulation):
    monkeypatch.setattr("app.main.verify_supabase_jwt", lambda token: {"sub": "owner", "aal": "aal2"})
    client = TestClient(app)
    with client.websocket_connect(f"/ws/operations/lakes/{LAKE_ID}", subprotocols=["bearer.signed-token"]) as ws:
        payload = ws.receive_json()
    assert payload["drones"]
    assert "source" in payload["drones"][0]


def test_startup_launches_background_tick_task_that_stays_alive():
    with TestClient(app) as client:
        tasks = getattr(client.app.state, "tick_tasks", {})
        assert set(tasks) == set(SUPPORTED_LAKE_IDS) | {"test-drone-field"}
        assert all(not task.done() for task in tasks.values())


def test_riskmap_allows_cross_origin_dashboard_dev_server(monkeypatch):
    client = TestClient(app)
    response = client.get(f"/api/lakes/{LAKE_ID}/riskmap", headers={"Origin": "http://localhost:5173", **_read_headers(monkeypatch)})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_riskmap_returns_nonempty_closed_tessellated_cell_rings(monkeypatch):
    client = TestClient(app)
    response = client.get(f"/api/lakes/{LAKE_ID}/riskmap", headers=_read_headers(monkeypatch))
    assert response.status_code == 200
    features = response.json()["features"]
    assert features
    for feature in features:
        assert feature["properties"]["zone_id"].startswith("cell-")
        coords = feature["geometry"]["coordinates"][0]
        assert coords[0] == coords[-1]


def test_sammamish_riskmap_geojson_preserves_official_shoreline_holes(monkeypatch):
    response = TestClient(app).get(
        f"/api/lakes/{LAKE_ID}/riskmap", headers=_read_headers(monkeypatch)
    )
    cells = [shape(feature["geometry"]) for feature in response.json()["features"]]

    assert unary_union(cells).symmetric_difference(
        load_lake_polygon(LAKE_ID)
    ).area == pytest.approx(0, abs=1e-12)


def test_simulation_assigns_from_every_rendered_zone():
    runtime = lake_runtimes[LAKE_ID]
    assert runtime.engine.zones == runtime.zones


def test_demo_drones_start_spread_across_lake(running_simulation):
    drones = lake_runtimes[LAKE_ID].engine.drones
    pairwise_distances = [
        haversine_m(left.pos, right.pos)
        for index, left in enumerate(drones)
        for right in drones[index + 1 :]
    ]
    assert min(pairwise_distances) >= 500.0


def test_unknown_lake_returns_404():
    response = TestClient(app).get("/api/lakes/lake-unknown/riskmap")
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/lakes/lake-unknown/riskmap"),
        ("get", "/api/lakes/lake-unknown/drones"),
        ("get", "/api/lakes/lake-unknown/alerts"),
        ("post", "/api/lakes/lake-unknown/demo/trigger"),
        ("post", "/api/lakes/lake-unknown/alerts/alert-1/escalate"),
        ("post", "/api/lakes/lake-unknown/drones/deploy"),
    ],
)
def test_all_lake_scoped_http_endpoints_return_404_for_unknown_lakes(method, path):
    response = getattr(TestClient(app), method)(path)
    assert response.status_code == 404


def test_deploy_rejects_non_owner(monkeypatch):
    monkeypatch.setattr("app.main.verify_supabase_jwt", lambda token: {"sub": "not-owner", "aal": "aal2"})
    monkeypatch.setattr(
        "app.main.get_lake_deployment_metadata",
        lambda lake_id: {"org_id": "org-demo", "owner_user_id": "owner", "drone_inventory_cap": 10},
    )

    response = TestClient(app).post(
        f"/api/lakes/{LAKE_ID}/drones/deploy", headers={"Authorization": "Bearer signed-token"}
    )

    assert response.status_code == 404


def test_deploy_rejects_owner_without_aal2(monkeypatch):
    monkeypatch.setattr("app.main.verify_supabase_jwt", lambda token: {"sub": "owner", "aal": "aal1"})
    monkeypatch.setattr(
        "app.main.get_lake_deployment_metadata",
        lambda lake_id: {"org_id": "org-demo", "owner_user_id": "owner", "drone_inventory_cap": 10},
    )

    response = TestClient(app).post(
        f"/api/lakes/{LAKE_ID}/drones/deploy", headers={"Authorization": "Bearer signed-token"}
    )

    assert response.status_code == 403


def test_deploy_rejects_invalid_jwt_signature(monkeypatch):
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", "test-secret")
    encode = lambda value: base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()
    token = f"{encode({'alg': 'HS256'})}.{encode({'sub': 'owner', 'exp': 4102444800})}.c2lnbmF0dXJl"

    response = TestClient(app).post(
        f"/api/lakes/{LAKE_ID}/drones/deploy", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401


def test_deploy_rejects_malformed_jwt_signature(monkeypatch):
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", "test-secret")
    encode = lambda value: base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()
    token = f"{encode({'alg': 'HS256'})}.{encode({'sub': 'owner', 'exp': 4102444800})}.a"

    response = TestClient(app, raise_server_exceptions=False).post(
        f"/api/lakes/{LAKE_ID}/drones/deploy", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401


def test_deploy_rejects_when_inventory_cap_reached(monkeypatch):
    runtime = lake_runtimes[LAKE_ID]
    monkeypatch.setattr("app.main.verify_supabase_jwt", lambda token: {"sub": "owner", "aal": "aal2"})
    monkeypatch.setattr(
        "app.main.get_lake_deployment_metadata",
        lambda lake_id: {
            "org_id": "org-demo",
            "owner_user_id": "owner",
            "drone_inventory_cap": len(runtime.engine.drones),
        },
    )

    response = TestClient(app).post(
        f"/api/lakes/{LAKE_ID}/drones/deploy", headers={"Authorization": "Bearer signed-token"}
    )

    assert response.status_code == 409


def test_deploy_allows_aal2_owner_when_tessellated_zones_are_fully_staffed(monkeypatch, running_simulation):
    runtime = lake_runtimes[LAKE_ID]
    before = len(runtime.engine.drones)
    monkeypatch.setattr("app.main.verify_supabase_jwt", lambda token: {"sub": "owner", "aal": "aal2"})
    monkeypatch.setattr(
        "app.main.get_lake_deployment_metadata",
        lambda lake_id: {"org_id": "org-demo", "owner_user_id": "owner", "drone_inventory_cap": before + 1},
    )

    response = TestClient(app).post(
        f"/api/lakes/{LAKE_ID}/drones/deploy", headers={"Authorization": "Bearer signed-token"}
    )

    assert response.status_code == 201
    deployed = response.json()
    assert deployed["status"] == "idle"
    assert deployed["assigned_zone"] is None
    assert deployed["position"] == {"lat": 47.55686175, "lon": -122.07109931}


def test_operational_routes_deny_civilian_and_inactive_access(monkeypatch):
    class RestrictedRepository(FakeAccessRepository):
        def load_principal_state(self, user_id):
            state = super().load_principal_state(user_id)
            state["account_class"] = "civilian"
            return state

    monkeypatch.setattr("app.main.get_access_repository", lambda: RestrictedRepository())
    monkeypatch.setattr("app.main.verify_supabase_jwt", lambda token: {"sub": "owner", "aal": "aal2"})
    response = TestClient(app).post(f"/api/lakes/{LAKE_ID}/demo/trigger", headers={"Authorization": "Bearer signed-token"})
    assert response.status_code == 403


def test_cross_station_operation_is_not_disclosed(monkeypatch):
    monkeypatch.setattr("app.main.verify_supabase_jwt", lambda token: {"sub": "not-owner", "aal": "aal2"})
    response = TestClient(app).post(f"/api/lakes/{LAKE_ID}/drones/deploy", headers={"Authorization": "Bearer signed-token"})
    assert response.status_code == 404


class FakeLakeDevices:
    def __init__(self, drones=()):
        self.drones = list(drones)

    def real_on_lake(self, lake_id):
        return self.drones


@pytest.fixture
def lake(monkeypatch):
    """Lake Sammamish with fake registered drones; its session state is reset afterwards."""
    runtime = lake_runtimes[LAKE_ID]
    original = runtime.zones
    devices = FakeLakeDevices()
    monkeypatch.setattr("app.main.get_device_repository", lambda: devices)
    yield runtime, devices, TestClient(app), _read_headers(monkeypatch)
    runtime.zones, runtime.real_zones, runtime.real_assignments = original, None, {}
    runtime.engine.set_fleet([], original)


def _post(client, headers, path, **body):
    return client.post(f"/api/lakes/{LAKE_ID}/{path}", headers=headers, **({"json": body} if body else {}))


def test_simulation_starts_with_one_drone_and_grows_one_at_a_time(lake):
    runtime, _, client, headers = lake
    assert runtime.engine.drones == []
    assert _post(client, headers, "demo/trigger").status_code == 409
    assert _post(client, headers, "simulation/drones").status_code == 409  # nothing to add to yet
    started = _post(client, headers, "simulation/start").json()
    assert started["simulated_drones"] == 1 and started["waiting_drones"] == 0
    added = _post(client, headers, "simulation/drones").json()
    # the new drone waits ashore until the lake is re-divided
    assert added["simulated_drones"] == 2 and added["waiting_drones"] == 1
    assert [drone.drone_id for drone in runtime.engine.drones] == [f"{LAKE_ID}-d0", f"{LAKE_ID}-d1"]
    divided = _post(client, headers, "zones/regenerate").json()
    assert divided["zones"] == 2 and divided["waiting_drones"] == 0
    assert len({drone.assigned_zone for drone in runtime.engine.drones}) == 2
    assert _post(client, headers, "simulation/stop").json()["simulated_drones"] == 0
    assert TestClient(app).post(f"/api/lakes/{LAKE_ID}/simulation/start").status_code == 401


def test_regenerate_gives_each_registered_drone_its_own_zone(lake):
    runtime, devices, client, headers = lake
    devices.drones = [{"inventory_id": "real-1"}, {"inventory_id": "real-2"}]
    _post(client, headers, "simulation/start", real_drones="replan")
    _post(client, headers, "simulation/drones")
    result = _post(client, headers, "zones/regenerate").json()
    assert result["zones"] == 4  # two simulated drones plus two registered drones
    simulated = {drone.assigned_zone for drone in runtime.engine.drones}
    real = set(runtime.real_assignments.values())
    assert len(simulated) == 2 and len(real) == 2 and not simulated & real
    listed = client.get(f"/api/lakes/{LAKE_ID}/registered-drones", headers=headers).json()["drones"]
    assert {drone["zone_id"] for drone in listed} == real


def test_starting_can_leave_real_drones_on_their_current_zones(lake):
    runtime, devices, client, headers = lake
    devices.drones = [{"inventory_id": "real-1"}]
    client.get(f"/api/lakes/{LAKE_ID}/registered-drones", headers=headers)
    before = (list(runtime.zones), dict(runtime.real_assignments))
    started = _post(client, headers, "simulation/start", real_drones="keep").json()
    assert started["real_drones_unaffected"] is True
    assert runtime.engine.drones[0].assigned_zone not in before[1].values()
    _post(client, headers, "simulation/drones")
    assert _post(client, headers, "zones/regenerate").json()["zones"] == 2  # simulated drones only
    # the simulation's own layout is named apart from the zones real drones keep flying
    assert {drone.assigned_zone for drone in runtime.engine.drones} == {"sim-cell-0", "sim-cell-1"}
    # real drones keep flying the layout they had before the session
    assert (runtime.real_zones, runtime.real_assignments) == before
    _post(client, headers, "simulation/stop")
    assert runtime.zones == before[0] and runtime.real_zones is None


def test_starting_can_replan_real_drones_with_the_simulation(lake):
    runtime, devices, client, headers = lake
    devices.drones = [{"inventory_id": "real-1"}]
    started = _post(client, headers, "simulation/start", real_drones="replan").json()
    assert started["zones"] == 2 and started["real_drones_unaffected"] is False
    assert runtime.real_assignments["real-1"] != runtime.engine.drones[0].assigned_zone


def test_registered_drones_lists_real_drones_assigned_to_the_lake(lake):
    _, devices, client, headers = lake
    devices.drones = [{"inventory_id": "real-1", "serial": "SN-1", "credential_state": "active", "last_heartbeat_at": None}]
    [drone] = client.get(f"/api/lakes/{LAKE_ID}/registered-drones", headers=headers).json()["drones"]
    assert drone["serial"] == "SN-1" and drone["last_heartbeat_at"] is None and "credential_state" not in drone
    assert drone["zone_id"] is not None
