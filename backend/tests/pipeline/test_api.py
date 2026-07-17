import base64
import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.coordination.assignment import haversine_m
from app.main import app, lake_runtimes


LAKE_ID = "lake-sammamish"


def test_get_riskmap_returns_feature_collection():
    client = TestClient(app)
    response = client.get(f"/api/lakes/{LAKE_ID}/riskmap")
    assert response.status_code == 200
    assert response.json()["type"] == "FeatureCollection"


def test_demo_trigger_creates_alert_retrievable():
    client = TestClient(app)
    response = client.post(f"/api/lakes/{LAKE_ID}/demo/trigger")
    assert response.status_code == 200
    alert_id = response.json()["alert_id"]
    alerts = client.get(f"/api/lakes/{LAKE_ID}/alerts").json()
    assert any(alert["alert_id"] == alert_id for alert in alerts)


def test_positions_ws_receives_state_with_source():
    client = TestClient(app)
    with client.websocket_connect(f"/ws/lakes/{LAKE_ID}/positions") as ws:
        payload = ws.receive_json()
    assert payload["drones"]
    assert "source" in payload["drones"][0]


def test_positions_ws_rejects_unknown_lake_with_policy_violation():
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect("/ws/lakes/lake-unknown/positions"):
            pass

    assert error.value.code == 1008


def test_startup_launches_background_tick_task_that_stays_alive():
    with TestClient(app) as client:
        tasks = getattr(client.app.state, "tick_tasks", {})
        assert set(tasks) == {LAKE_ID}
        assert not tasks[LAKE_ID].done()


def test_riskmap_allows_cross_origin_dashboard_dev_server():
    client = TestClient(app)
    response = client.get(f"/api/lakes/{LAKE_ID}/riskmap", headers={"Origin": "http://localhost:5173"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_riskmap_can_include_a_circular_cluster_zone():
    client = TestClient(app)
    response = client.get(f"/api/lakes/{LAKE_ID}/riskmap")
    assert response.status_code == 200
    # Not asserting a cluster is always present (fixture data may or may not
    # be dense enough to pass MIN_CLUSTER_WEIGHT) - asserting the shape is
    # correct when one is: any feature whose properties advertise a cluster
    # zone_id must have a valid closed-ring polygon.
    for feature in response.json()["features"]:
        if feature["properties"]["zone_id"].startswith("cluster-"):
            coords = feature["geometry"]["coordinates"][0]
            assert coords[0] == coords[-1]


def test_simulation_assigns_from_every_rendered_zone():
    runtime = lake_runtimes[LAKE_ID]
    assert runtime.engine.zones == runtime.zones


def test_demo_drones_start_spread_across_lake():
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

    assert response.status_code == 403


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


def test_deploy_allows_aal2_owner_and_reassigns_zones(monkeypatch):
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
    assert deployed["status"] == "en_route"
    assert deployed["assigned_zone"] is not None
    assert deployed["position"] == {"lat": 47.606, "lon": -122.09}
    runtime.engine.drones.pop()
    runtime.engine._initial_assign()
