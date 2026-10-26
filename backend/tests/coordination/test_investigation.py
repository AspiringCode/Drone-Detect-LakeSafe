import pytest
from app.coordination.engine import SimulationEngine
from app.models import Drone, DroneStatus, LatLon, RiskZone


def engine():
    a, b = LatLon(47.6, -122.1), LatLon(47.601, -122.1)
    zones = [RiskZone(str(i), p, [p, p, p, p], 1, {}, is_proxy=False) for i, p in enumerate((a, b))]
    value = SimulationEngine([Drone(str(i), p, 1, DroneStatus.IDLE, None) for i, p in enumerate((a, b))], zones, [])
    value.step(1)
    return value


def test_arrival_is_separate_from_a_second_drone_finding_and_origins_restore():
    value = engine()
    original = {d.drone_id: (d.pos, d.assigned_zone) for d in value.drones}
    value.trigger_detection('0', LatLon(47.6005, -122.1), alert_id='incident')
    state = value.step(30)
    assert state['investigation']['phase'] == 'awaiting_finding'
    assert not state['confirmed']
    value.record_finding('incident', 'not_observed')
    assert value.investigation_status('incident')['finding'] == 'not_observed'
    value.finish_investigation('incident')
    value.step(30)
    for drone in value.drones:
        assert (drone.pos, drone.assigned_zone) == original[drone.drone_id]
        assert drone.status == DroneStatus.PATROLLING


def test_overlapping_incident_cannot_lose_return_positions():
    value = engine()
    value.trigger_detection('0', LatLon(47.6, -122.1), alert_id='a')
    with pytest.raises(ValueError):
        value.trigger_detection('0', LatLon(47.6, -122.1), alert_id='b')


def test_one_drone_reports_no_second_drone():
    value = engine()
    value.drones = value.drones[:1]
    value.trigger_detection('0', LatLon(47.6, -122.1), alert_id='a')
    assert value.investigation_status('a')['phase'] == 'unavailable'


def test_demo_sample_is_delayed_after_arrival_and_does_not_claim_camera_evidence():
    value=engine()
    value.trigger_detection('0',LatLon(47.6005,-122.1),alert_id='a')
    value._confirmation['demo_finding']='not_observed'
    assert value.step(30)['investigation']['finding'] is None
    assert value.step(3)['investigation']['finding']=='not_observed'
    assert not value.step(0)['confirmed']
