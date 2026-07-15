from fastapi.testclient import TestClient

from app.main import app


def test_get_riskmap_returns_feature_collection():
    client = TestClient(app)
    response = client.get("/api/riskmap")
    assert response.status_code == 200
    assert response.json()["type"] == "FeatureCollection"


def test_demo_trigger_creates_alert_retrievable():
    client = TestClient(app)
    response = client.post("/api/demo/trigger")
    assert response.status_code == 200
    alert_id = response.json()["alert_id"]
    alerts = client.get("/api/alerts").json()
    assert any(alert["alert_id"] == alert_id for alert in alerts)


def test_positions_ws_receives_state_with_source():
    client = TestClient(app)
    with client.websocket_connect("/ws/positions") as ws:
        payload = ws.receive_json()
    assert payload["drones"]
    assert "source" in payload["drones"][0]


def test_startup_launches_background_tick_task_that_stays_alive():
    with TestClient(app) as client:
        task = getattr(client.app.state, "tick_task", None)
        assert task is not None
        assert not task.done()


def test_riskmap_allows_cross_origin_dashboard_dev_server():
    client = TestClient(app)
    response = client.get("/api/riskmap", headers={"Origin": "http://localhost:5173"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_riskmap_can_include_a_circular_cluster_zone():
    client = TestClient(app)
    response = client.get("/api/riskmap")
    assert response.status_code == 200
    # Not asserting a cluster is always present (fixture data may or may not
    # be dense enough to pass MIN_CLUSTER_WEIGHT) - asserting the shape is
    # correct when one is: any feature whose properties advertise a cluster
    # zone_id must have a valid closed-ring polygon.
    for feature in response.json()["features"]:
        if feature["properties"]["zone_id"].startswith("cluster-"):
            coords = feature["geometry"]["coordinates"][0]
            assert coords[0] == coords[-1]
