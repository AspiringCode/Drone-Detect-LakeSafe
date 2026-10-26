from __future__ import annotations

from typing import TypedDict

from app.coordination.assignment import assign_zones, haversine_m
from app.coordination.battery import reassign_on_low_battery
from app.coordination.collision import deconflict, detect_conflicts
from app.coordination.patrol import circle_waypoints
from app.models import Drone, DroneStatus, LatLon, RiskZone

PATROL_WAYPOINT_COUNT = 16


class SimulationState(TypedDict, total=False):
    drones: list[Drone]
    conflicts: list[tuple[str, str]]
    t: float
    altitudes: dict[str, float]
    confirmed: bool


class SimulationEngine:
    def __init__(self, drones: list[Drone], zones: list[RiskZone], shore_stations: list[LatLon]) -> None:
        self.drones = drones
        self.zones = zones
        self.shore_stations = shore_stations
        self.t = 0.0
        self.targets: dict[str, LatLon] = {}
        self.altitudes: dict[str, float] = {drone.drone_id: 30.0 for drone in drones}
        self._confirmation: dict | None = None
        self._patrol_waypoints: dict[str, list[LatLon]] = {}
        self._patrol_index: dict[str, int] = {}
        # This is intentionally an acknowledgement, not desired state.  It is
        # advanced only by a successfully applied simulated command.
        self.acknowledged_desired_versions: dict[str, int] = {}
        self._assign_patrol_params()
        self._initial_assign()

    def _assign_patrol_params(self) -> None:
        """Alternate direction and stagger phase across circular patrol zones."""
        circular_zones = [z for z in self.zones if z.radius_m is not None]
        n = len(circular_zones)
        self._zone_patrol_params: dict[str, tuple[float, bool]] = {}
        for rank, zone in enumerate(circular_zones):
            phase = (360.0 / n) * rank if n else 0.0
            clockwise = rank % 2 == 0
            self._zone_patrol_params[zone.zone_id] = (phase, clockwise)

    def _initial_assign(self) -> None:
        assignment = assign_zones(self.drones, self.zones)
        zone_by_id = {zone.zone_id: zone for zone in self.zones}
        for drone in self.drones:
            zone_id = assignment.get(drone.drone_id)
            if zone_id:
                drone.assigned_zone = zone_id
                drone.status = DroneStatus.EN_ROUTE
                self.targets[drone.drone_id] = zone_by_id[zone_id].centroid

    def set_fleet(self, drones: list[Drone], zones: list[RiskZone] | None = None) -> None:
        """Start (or, with no drones, end) a simulation session; each drone heads to its zone."""
        if zones is not None:
            self.zones = zones
            self._assign_patrol_params()
        self.drones = drones
        self.altitudes = {drone.drone_id: 30.0 for drone in drones}
        self.targets = {}
        self._patrol_waypoints = {}
        self._patrol_index = {}
        self._confirmation = None
        self._initial_assign()

    def add_drone(self, drone: Drone) -> None:
        """Join the session idle; the drone gets a zone at the next re-division."""
        self.drones.append(drone)
        self.altitudes[drone.drone_id] = 30.0

    def apply_plan(
        self,
        zones: list[RiskZone],
        assignments: dict[str, str],
        desired_state_versions: dict[str, int] | None = None,
    ) -> None:
        """Atomically replace simulated zone/assignment state after validation.

        All references are checked before touching the current engine.  Existing
        patrol state is deliberately discarded because it belongs to the old
        plan; the new plan starts every assigned drone en route to its new cell.
        """
        zone_by_id = {zone.zone_id: zone for zone in zones}
        if len(zone_by_id) != len(zones):
            raise ValueError("zone IDs must be unique")
        drone_by_id = {drone.drone_id: drone for drone in self.drones}
        if len(drone_by_id) != len(self.drones):
            raise ValueError("drone IDs must be unique")
        for drone_id, zone_id in assignments.items():
            if drone_id not in drone_by_id:
                raise ValueError(f"unknown drone: {drone_id}")
            if zone_id not in zone_by_id:
                raise ValueError(f"unknown zone: {zone_id}")
        versions = desired_state_versions or {}
        if not set(versions).issubset(assignments):
            raise ValueError("versions require an assignment")
        for drone_id, version in versions.items():
            if not isinstance(version, int) or version < 1:
                raise ValueError(f"invalid desired state version for {drone_id}")
            if version < self.acknowledged_desired_versions.get(drone_id, 0):
                raise ValueError(f"stale desired state version for {drone_id}")

        circular_zones = [zone for zone in zones if zone.radius_m is not None]
        count = len(circular_zones)
        patrol_params = {
            zone.zone_id: ((360.0 / count) * rank if count else 0.0, rank % 2 == 0)
            for rank, zone in enumerate(circular_zones)
        }
        next_targets = {drone_id: zone_by_id[zone_id].centroid for drone_id, zone_id in assignments.items()}

        # The assignments above have fully validated.  This is the sole mutation
        # boundary so invalid plans cannot leave a partially applied runtime.
        self.zones = list(zones)
        self.targets = next_targets
        self._zone_patrol_params = patrol_params
        self._patrol_waypoints = {}
        self._patrol_index = {}
        self._confirmation = None
        for drone in self.drones:
            zone_id = assignments.get(drone.drone_id)
            drone.assigned_zone = zone_id
            drone.status = DroneStatus.EN_ROUTE if zone_id else DroneStatus.IDLE
        self.acknowledged_desired_versions.update(versions)

    def return_to_reserve(self, drone_id: str, desired_state_version: int) -> None:
        """Stop autonomous patrol for one simulated drone without steering it.

        A reserve location is used only when the simulation has one configured;
        otherwise the simulated runtime safely becomes idle.  No caller passes
        a coordinate, heading, or waypoint.
        """
        drone = next((item for item in self.drones if item.drone_id == drone_id), None)
        if drone is None:
            raise ValueError(f"unknown drone: {drone_id}")
        if desired_state_version < self.acknowledged_desired_versions.get(drone_id, 0):
            raise ValueError(f"stale desired state version for {drone_id}")
        drone.assigned_zone = None
        self._patrol_waypoints.pop(drone_id, None)
        self._patrol_index.pop(drone_id, None)
        if self.shore_stations:
            drone.status = DroneStatus.RETURNING
            self.targets[drone_id] = min(self.shore_stations, key=lambda shore: haversine_m(drone.pos, shore))
        else:
            drone.status = DroneStatus.IDLE
            self.targets.pop(drone_id, None)
        self.acknowledged_desired_versions[drone_id] = desired_state_version

    def _move_toward(self, drone: Drone, target: LatLon, dt: float, speed_mps: float = 15.0) -> bool:
        dist = haversine_m(drone.pos, target)
        if dist <= speed_mps * dt or dist < 1.0:
            drone.pos = target
            return True
        frac = (speed_mps * dt) / dist
        drone.pos = LatLon(
            drone.pos.lat + (target.lat - drone.pos.lat) * frac,
            drone.pos.lon + (target.lon - drone.pos.lon) * frac,
        )
        return False

    def _start_patrol_if_circular(self, drone: Drone) -> None:
        zone = next((z for z in self.zones if z.zone_id == drone.assigned_zone), None)
        if zone is None or zone.radius_m is None:
            return
        phase, clockwise = self._zone_patrol_params.get(zone.zone_id, (0.0, True))
        self._patrol_waypoints[drone.drone_id] = circle_waypoints(
            zone.centroid, zone.radius_m, PATROL_WAYPOINT_COUNT, phase, clockwise
        )
        self._patrol_index[drone.drone_id] = 0

    def _advance_patrol(self, drone: Drone, dt: float) -> None:
        waypoints = self._patrol_waypoints.get(drone.drone_id)
        if not waypoints:
            return
        idx = self._patrol_index[drone.drone_id]
        target = waypoints[idx]
        arrived = self._move_toward(drone, target, dt)
        if arrived:
            self._patrol_index[drone.drone_id] = (idx + 1) % len(waypoints)

    def investigation_status(self, alert_id: str) -> dict | None:
        incident = self._confirmation
        if not incident or incident.get("alert_id") != alert_id:
            return None
        return {key: incident[key] for key in ("alert_id", "detecting", "confirmer", "phase", "finding")}

    def record_finding(self, alert_id: str, finding: str) -> None:
        if not self.investigation_status(alert_id) or self._confirmation["phase"] != "awaiting_finding":
            raise ValueError("The second drone has not arrived")
        if finding not in {"observed", "not_observed", "inconclusive"}:
            raise ValueError("Invalid finding")
        self._confirmation.update(finding=finding, confirmed=finding == "observed", phase="finding_received")

    def finish_investigation(self, alert_id: str) -> None:
        if not self.investigation_status(alert_id):
            return
        if self._confirmation["phase"] in {"returning", "returned"}:
            return
        self._confirmation["phase"] = "returning"
        for drone in self.drones:
            original = self._confirmation["origins"].get(drone.drone_id)
            if original and drone.battery >= .25:
                drone.assigned_zone = original["zone"]
                drone.status = DroneStatus.RETURNING
                self.targets[drone.drone_id] = original["position"]

    def trigger_detection(self, zone_id: str, at: LatLon, *, alert_id: str = "demo") -> None:
        if not self.drones:
            raise ValueError("No simulated drones")
        if self._confirmation and self._confirmation["phase"] != "returned":
            raise ValueError("Finish the current investigation before starting another")
        detecting = next((d for d in self.drones if d.assigned_zone == zone_id), self.drones[0])
        candidates = [d for d in self.drones if d.drone_id != detecting.drone_id and d.status != DroneStatus.RETURNING and d.battery >= .25]
        confirmer = min(candidates, key=lambda d: haversine_m(d.pos, at)) if candidates else None
        origins = {d.drone_id: {"position": d.pos, "zone": d.assigned_zone,
                   "waypoints": self._patrol_waypoints.get(d.drone_id), "index": self._patrol_index.get(d.drone_id, 0)}
                   for d in (detecting, confirmer) if d is not None}
        detecting.status = DroneStatus.INVESTIGATING
        detecting.assigned_zone = zone_id
        self.targets[detecting.drone_id] = at
        self._patrol_waypoints.pop(detecting.drone_id, None)

        if confirmer:
            confirmer.status = DroneStatus.EN_ROUTE
            confirmer.assigned_zone = zone_id
            self.targets[confirmer.drone_id] = at
            self._patrol_waypoints.pop(confirmer.drone_id, None)
        self._confirmation = {
            "zone_id": zone_id,
            "at": at,
            "detecting": detecting.drone_id,
            "confirmer": confirmer.drone_id if confirmer else None,
            "confirmed": False,
            "alert_id": alert_id, "phase": "en_route" if confirmer else "unavailable",
            "finding": None, "origins": origins,
        }

    def step(self, dt: float) -> SimulationState:
        self.t += dt
        self.altitudes = deconflict(self.drones, self.altitudes)

        for drone in self.drones:
            if drone.status == DroneStatus.PATROLLING and drone.drone_id in self._patrol_waypoints:
                self._advance_patrol(drone, dt)
                continue
            target = self.targets.get(drone.drone_id)
            if target and drone.status in {DroneStatus.EN_ROUTE, DroneStatus.RETURNING}:
                arrived = self._move_toward(drone, target, dt)
                if arrived:
                    if self._confirmation and self._confirmation["phase"] == "returning" and drone.drone_id in self._confirmation["origins"]:
                        original = self._confirmation["origins"][drone.drone_id]
                        drone.status = DroneStatus.PATROLLING if original["zone"] else DroneStatus.IDLE
                        self.targets.pop(drone.drone_id, None)
                        if original["waypoints"]:
                            self._patrol_waypoints[drone.drone_id] = original["waypoints"]
                            self._patrol_index[drone.drone_id] = original["index"]
                    elif self._confirmation and drone.drone_id == self._confirmation.get("confirmer"):
                        drone.status = DroneStatus.INVESTIGATING
                        self._confirmation["phase"] = "awaiting_finding"
                        self._confirmation['arrived_at']=self.t
                    elif drone.status == DroneStatus.EN_ROUTE:
                        drone.status = DroneStatus.PATROLLING
                        self._start_patrol_if_circular(drone)

        if (self._confirmation and self._confirmation['phase']=='awaiting_finding'
            and self._confirmation.get('demo_finding') and self.t-self._confirmation.get('arrived_at',self.t)>=2):
            self.record_finding(self._confirmation['alert_id'],self._confirmation['demo_finding'])
        if self._confirmation and self._confirmation["phase"] == "returning" and not any(
            d.status == DroneStatus.RETURNING for d in self.drones if d.drone_id in self._confirmation["origins"]
        ):
            self._confirmation["phase"] = "returned"
        assignment = {drone.drone_id: drone.assigned_zone for drone in self.drones}
        reassign_on_low_battery(self.drones, self.zones, assignment)
        self.altitudes = deconflict(self.drones, self.altitudes)
        conflicts = detect_conflicts(self.drones, altitudes=self.altitudes)
        return {
            "drones": self.drones,
            "conflicts": conflicts,
            "t": self.t,
            "altitudes": self.altitudes,
            "confirmed": bool(self._confirmation and self._confirmation["confirmed"]),
            "investigation": self.investigation_status(self._confirmation["alert_id"]) if self._confirmation else None,
        }
