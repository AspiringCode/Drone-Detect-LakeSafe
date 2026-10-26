from app.coordination.collision import detect_conflicts
from app.coordination.engine import SimulationEngine
from app.models import Drone, DroneStatus, LatLon, RiskZone


def mk_zone(zone_id: str, at: LatLon = LatLon(47.58, -122.09)) -> RiskZone:
    return RiskZone(zone_id, at, [at, at, at, at], 1.0, {}, is_proxy=False)


def mk_engine(n_drones: int = 5) -> SimulationEngine:
    drones = [
        Drone(f"d{i}", LatLon(47.579 + i * 0.0001, -122.091), 1.0, DroneStatus.IDLE, None)
        for i in range(n_drones)
    ]
    return SimulationEngine(drones, [mk_zone("z1"), mk_zone("z2", LatLon(47.581, -122.09))], [])


def test_step_moves_en_route_to_patrolling():
    eng = mk_engine(1)
    eng.targets["d0"] = LatLon(47.58, -122.09)
    eng.drones[0].status = DroneStatus.EN_ROUTE
    st = eng.step(20.0)
    assert st["drones"][0].status == DroneStatus.PATROLLING


def test_confirmation_protocol_dispatches_second_drone():
    eng = mk_engine(n_drones=5)
    eng.trigger_detection("z1", at=LatLon(47.58, -122.09))
    st = eng.step(1.0)
    investigating = [d for d in st["drones"] if d.status == DroneStatus.INVESTIGATING]
    enroute_confirm = [d for d in st["drones"] if d.status == DroneStatus.EN_ROUTE]
    assert len(investigating) == 1 and len(enroute_confirm) >= 1


def test_arrival_does_not_claim_an_independent_detection():
    eng = mk_engine(n_drones=2)
    eng.trigger_detection("z1", at=LatLon(47.58, -122.09))
    st = eng.step(30.0)
    assert st["confirmed"] is False
    eng.record_finding('demo','observed')
    assert eng.step(0)['confirmed'] is True


def test_step_deconflicts_altitudes():
    eng = mk_engine(n_drones=2)
    eng.drones[0].pos = LatLon(47.58, -122.09)
    eng.drones[1].pos = LatLon(47.58001, -122.09001)
    st = eng.step(1.0)
    assert detect_conflicts(st["drones"], altitudes=st["altitudes"]) == []
    assert all(d.source == "simulated" for d in st["drones"])


def test_step_does_not_rewrite_a_drone_transport_source():
    eng = mk_engine(1)
    eng.drones[0].source = "real"

    eng.step(1.0)

    assert eng.drones[0].source == "real"


def mk_circular_zone(zone_id: str, at: LatLon, radius_m: float = 60.0) -> RiskZone:
    return RiskZone(zone_id, at, [at, at, at, at], 1.0, {}, is_proxy=False, radius_m=radius_m)


def test_patrolling_drone_on_circular_zone_advances_around_waypoints():
    drones = [Drone("d0", LatLon(47.579, -122.091), 1.0, DroneStatus.IDLE, None)]
    zone = mk_circular_zone("z1", LatLon(47.58, -122.09))
    eng = SimulationEngine(drones, [zone], [])
    eng.drones[0].status = DroneStatus.EN_ROUTE
    eng.targets["d0"] = zone.centroid

    st = eng.step(20.0)
    assert st["drones"][0].status == DroneStatus.PATROLLING
    pos_after_arrival = st["drones"][0].pos

    st = eng.step(5.0)
    assert st["drones"][0].pos != pos_after_arrival


def test_patrolling_drone_on_grid_zone_still_holds_position():
    drones = [Drone("d0", LatLon(47.579, -122.091), 1.0, DroneStatus.IDLE, None)]
    zone = mk_zone("z1")
    eng = SimulationEngine(drones, [zone], [])
    eng.drones[0].status = DroneStatus.EN_ROUTE
    eng.targets["d0"] = zone.centroid

    eng.step(20.0)
    held_pos = eng.drones[0].pos
    eng.step(5.0)
    assert eng.drones[0].pos == held_pos
