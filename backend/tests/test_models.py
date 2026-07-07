from datetime import datetime

from app.models import Alert, Detection, Drone, DroneStatus, LatLon, RiskZone


def test_drone_defaults_to_simulated():
    d = Drone("d1", LatLon(47.58, -122.09), 1.0, DroneStatus.IDLE, None)
    assert d.source == "simulated"


def test_riskzone_carries_proxy_flag():
    z = RiskZone("z1", LatLon(47.58, -122.09), [], 0.5, {"depth": 0.5}, is_proxy=True)
    assert z.is_proxy is True


def test_alert_latency_optional():
    a = Alert(
        "a1",
        datetime.utcnow(),
        LatLon(47.58, -122.09),
        "thermal-cv",
        "d1",
        None,
        confirmed=False,
        source="real",
        latency_ms=None,
    )
    assert a.latency_ms is None


def test_detection_carries_explicit_source():
    det = Detection(
        0,
        (10.0, 10.0, 4.0, 4.0),
        0.9,
        datetime.utcnow(),
        source="simulated",
    )
    assert det.source == "simulated"
