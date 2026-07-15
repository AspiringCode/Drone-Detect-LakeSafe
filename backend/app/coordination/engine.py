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

    def trigger_detection(self, zone_id: str, at: LatLon) -> None:
        detecting = next((d for d in self.drones if d.assigned_zone == zone_id), self.drones[0])
        detecting.status = DroneStatus.INVESTIGATING
        detecting.assigned_zone = zone_id
        self.targets[detecting.drone_id] = at
        self._patrol_waypoints.pop(detecting.drone_id, None)

        candidates = [d for d in self.drones if d.drone_id != detecting.drone_id and d.status != DroneStatus.RETURNING]
        confirmer = min(candidates, key=lambda d: haversine_m(d.pos, at)) if candidates else None
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
        }

    def step(self, dt: float) -> SimulationState:
        self.t += dt
        self.altitudes = deconflict(self.drones, self.altitudes)

        for drone in self.drones:
            drone.source = "simulated"
            if drone.status == DroneStatus.PATROLLING and drone.drone_id in self._patrol_waypoints:
                self._advance_patrol(drone, dt)
                continue
            target = self.targets.get(drone.drone_id)
            if target and drone.status in {DroneStatus.EN_ROUTE, DroneStatus.RETURNING}:
                arrived = self._move_toward(drone, target, dt)
                if arrived:
                    if self._confirmation and drone.drone_id == self._confirmation.get("confirmer"):
                        drone.status = DroneStatus.INVESTIGATING
                        self._confirmation["confirmed"] = True
                    elif drone.status == DroneStatus.EN_ROUTE:
                        drone.status = DroneStatus.PATROLLING
                        self._start_patrol_if_circular(drone)

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
        }
