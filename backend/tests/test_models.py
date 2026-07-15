from datetime import datetime, timezone

from app.models import Alert, Detection, Drone, DroneStatus, LatLon, RiskZone


def test_drone_defaults_to_simulated():
    d = Drone("d1", LatLon(47.58, -122.09), 1.0, DroneStatus.IDLE, None)
    assert d.source == "simulated"


def test_riskzone_carries_proxy_flag():
    z = RiskZone("z1", LatLon(47.58, -122.09), [], 0.5, {"depth": 0.5}, is_proxy=True)
    assert z.is_proxy is True


def test_risk_zone_radius_m_defaults_to_none():
    zone = RiskZone(
        zone_id="z0-0",
        centroid=LatLon(47.58, -122.09),
        polygon=[LatLon(47.58, -122.09)],
        risk_score=0.5,
        components={},
        is_proxy=False,
    )
    assert zone.radius_m is None


def test_risk_zone_accepts_explicit_radius_m():
    zone = RiskZone(
        zone_id="cluster-0",
        centroid=LatLon(47.58, -122.09),
        polygon=[LatLon(47.58, -122.09)],
        risk_score=0.5,
        components={},
        is_proxy=False,
        radius_m=42.0,
    )
    assert zone.radius_m == 42.0


def test_alert_latency_optional():
    a = Alert(
        "a1",
        datetime.now(timezone.utc),
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
        datetime.now(timezone.utc),
        source="simulated",
    )
    assert det.source == "simulated"
