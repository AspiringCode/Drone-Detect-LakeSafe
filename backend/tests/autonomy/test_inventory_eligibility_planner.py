from app.autonomy.eligibility import eligible_simulated_drones
from app.autonomy.models import FleetPolicy, InventoryDrone, PriorAssignment, ZoneCell, ZonePlan
from app.autonomy.planner import plan_assignments


def drone(drone_id: str, **changes: object) -> InventoryDrone:
    values = {
        "inventory_id": drone_id,
        "station_id": "st-1",
        "lake_id": "lake-1",
        "source": "simulated",
        "lifecycle": "available",
        "battery_percent": 90,
        "health": "healthy",
        "connectivity": "connected",
        "maintenance_due": False,
        "desired_state_version": 3,
    }
    values.update(changes)
    return InventoryDrone(**values)


def zone_plan(*cells: ZoneCell) -> ZonePlan:
    return ZonePlan("plan-1", "st-1", "lake-1", cells)


def test_real_unhealthy_charging_and_reserved_inventory_is_excluded():
    drones = (
        drone("real", source="real"),
        drone("bad", health="fault"),
        drone("charge", lifecycle="charging"),
        drone("ok-a"),
        drone("ok-b"),
    )
    assert eligible_simulated_drones(drones, "st-1", "lake-1", FleetPolicy(safety_reserve=1)) == (drone("ok-a"),)


def test_assignment_versions_increment_only_on_change():
    desired = plan_assignments(
        (drone("d1"),),
        zone_plan(ZoneCell("z1", "hotspot", 1.0)),
        (),
    )
    assert desired[0].zone_id == "z1"
    assert desired[0].desired_state_version == 4

    unchanged = plan_assignments(
        (drone("d1"),),
        zone_plan(ZoneCell("z1", "hotspot", 1.0)),
        (PriorAssignment("d1", "z1", 3),),
    )
    assert unchanged[0].desired_state_version == 3


def test_hotspots_precede_coverage_and_safe_assignment_survives():
    desired = plan_assignments(
        (drone("d1"), drone("d2")),
        zone_plan(ZoneCell("hot", "hotspot", 0.4), ZoneCell("coverage", "coverage", 0.9)),
        (PriorAssignment("d2", "coverage", 3),),
    )
    assert [(item.inventory_id, item.zone_id) for item in desired] == [("d1", "hot"), ("d2", "coverage")]


def test_planner_never_mutates_input_inventory():
    candidate = drone("d1")
    plan_assignments((candidate,), zone_plan(ZoneCell("z1", "hotspot", 1.0)), ())
    assert candidate.desired_state_version == 3
