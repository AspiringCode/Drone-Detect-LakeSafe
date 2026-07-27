"""Build QGroundControl `.plan` documents from computed patrol circles.

Pure data transformation: no filesystem, no network. The plan format is
QGC plan version 1 with mission version 2, targeting ArduPilot Copter.

Coordinate-order warning: QGC uses [lat, lon] in `plannedHomePosition` and in
geofence polygon vertices, which is the OPPOSITE of GeoJSON's [lon, lat]. This
module is the single place that conversion happens.
"""

from __future__ import annotations

from app.coordination.patrol import circle_waypoints
from app.models import LatLon

# MAVLink command IDs
CMD_NAV_WAYPOINT = 16
CMD_NAV_TAKEOFF = 22
CMD_NAV_RETURN_TO_LAUNCH = 20

# MAV_FRAME values
FRAME_GLOBAL_RELATIVE_ALT = 3
FRAME_MISSION = 2

# QGC enum values
FIRMWARE_ARDUPILOT = 3
VEHICLE_QUADROTOR = 2
ALTITUDE_MODE_RELATIVE = 1

DEFAULT_CRUISE_SPEED_MPS = 15.0
DEFAULT_HOVER_SPEED_MPS = 5.0


def _simple_item(
    *, command: int, frame: int, params: list, altitude_m: float, do_jump_id: int
) -> dict:
    return {
        "AMSLAltAboveTerrain": None,
        "Altitude": altitude_m,
        "AltitudeMode": ALTITUDE_MODE_RELATIVE,
        "autoContinue": True,
        "command": command,
        "doJumpId": do_jump_id,
        "frame": frame,
        "params": params,
        "type": "SimpleItem",
    }


def build_patrol_plan(
    center: LatLon,
    radius_m: float,
    altitude_m: float,
    home: LatLon,
    n_points: int = 16,
    fence_polygon: list[LatLon] | None = None,
) -> dict:
    """Return a QGC `.plan` document flying one patrol loop around `center`.

    The mission is takeoff -> n_points waypoints around the circle -> RTL.
    A single loop is deliberate: looping forever is a flight-mode concern
    (LOITER/AUTO restart), not something to bake into the mission file, and a
    terminating mission is far safer to test.
    """
    if altitude_m <= 0:
        raise ValueError("altitude_m must be positive; got {!r}".format(altitude_m))
    if radius_m <= 0:
        raise ValueError("radius_m must be positive; got {!r}".format(radius_m))

    items: list[dict] = []
    do_jump_id = 1

    items.append(
        _simple_item(
            command=CMD_NAV_TAKEOFF,
            frame=FRAME_GLOBAL_RELATIVE_ALT,
            # takeoff params: [pitch, 0, 0, yaw, lat, lon, alt]
            params=[15.0, 0, 0, None, home.lat, home.lon, altitude_m],
            altitude_m=altitude_m,
            do_jump_id=do_jump_id,
        )
    )
    do_jump_id += 1

    for waypoint in circle_waypoints(center, radius_m=radius_m, n_points=n_points):
        items.append(
            _simple_item(
                command=CMD_NAV_WAYPOINT,
                frame=FRAME_GLOBAL_RELATIVE_ALT,
                # waypoint params: [hold_s, accept_radius, pass_radius, yaw, lat, lon, alt]
                params=[0, 0, 0, None, waypoint.lat, waypoint.lon, altitude_m],
                altitude_m=altitude_m,
                do_jump_id=do_jump_id,
            )
        )
        do_jump_id += 1

    items.append(
        _simple_item(
            command=CMD_NAV_RETURN_TO_LAUNCH,
            frame=FRAME_MISSION,
            params=[0, 0, 0, 0, 0, 0, 0],
            altitude_m=0,
            do_jump_id=do_jump_id,
        )
    )

    polygons = []
    if fence_polygon:
        polygons.append(
            {
                "inclusion": True,
                "polygon": [[point.lat, point.lon] for point in fence_polygon],
                "version": 1,
            }
        )

    return {
        "fileType": "Plan",
        "geoFence": {"circles": [], "polygons": polygons, "version": 2},
        "groundStation": "QGroundControl",
        "mission": {
            "cruiseSpeed": DEFAULT_CRUISE_SPEED_MPS,
            "firmwareType": FIRMWARE_ARDUPILOT,
            "globalPlanAltitudeMode": ALTITUDE_MODE_RELATIVE,
            "hoverSpeed": DEFAULT_HOVER_SPEED_MPS,
            "items": items,
            "plannedHomePosition": [home.lat, home.lon, 0],
            "vehicleType": VEHICLE_QUADROTOR,
            "version": 2,
        },
        "rallyPoints": {"points": [], "version": 2},
        "version": 1,
    }
