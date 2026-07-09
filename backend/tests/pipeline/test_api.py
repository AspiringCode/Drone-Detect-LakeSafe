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
