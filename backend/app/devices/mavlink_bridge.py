"""Forward ArduPilot MAVLink telemetry to LakeSafe as signed heartbeats.

Runs off the drone or next to it; copy this file and drone_link.py side by side.
  pip install pymavlink cryptography

Ground laptop (Mission Planner: Ctrl+F > "Mavlink" > UDP Outbound, 127.0.0.1 port 14550):
  python mavlink_bridge.py --api URL --mavlink udpin:0.0.0.0:14550 --drone 1=DRONE_ID=drone.pem
Raspberry Pi on the flight controller's TELEM port:
  python mavlink_bridge.py --api URL --mavlink /dev/serial0 --baud 921600 --drone 1=DRONE_ID=drone.pem
"""

from __future__ import annotations

import argparse
import sys
import time

try:
    from app.devices import drone_link
except ImportError:  # copied next to drone_link.py on the companion computer
    import drone_link

STALE_S = 3.0
AUTOPILOT_COMPONENT = 1  # MAV_COMP_ID_AUTOPILOT1; cameras/gimbals share the sysid but not the flight mode
ARMED_FLAG = 128  # MAV_MODE_FLAG_SAFETY_ARMED
# ArduCopter custom_mode numbers.
FLIGHT_STATUS_BY_MODE = {3: "patrolling", 4: "en_route", 6: "returning", 9: "returning", 21: "returning"}


def flight_status(custom_mode: int | None, armed: bool) -> str:
    if not armed:
        return "idle"
    # Any other armed mode (LOITER, ALT_HOLD, manual...) means airborne over the lake; patrolling is the closest status.
    return FLIGHT_STATUS_BY_MODE.get(custom_mode, "patrolling")


def update(state: dict, msg, now: float) -> None:
    kind = msg.get_type()
    if kind == "HEARTBEAT":
        state.update(last_heartbeat=now, custom_mode=msg.custom_mode, armed=bool(msg.base_mode & ARMED_FLAG))
    elif kind == "SYS_STATUS":
        state["battery"] = msg.battery_remaining
    elif kind == "GLOBAL_POSITION_INT":
        # ArduPilot reports 0,0 until it has a GPS fix; that is not a position.
        state["position"] = None if msg.lat == 0 and msg.lon == 0 else {
            "lat": msg.lat / 1e7, "lon": msg.lon / 1e7, "alt_m": msg.relative_alt / 1000,
        }


def payload(state: dict, now: float) -> dict:
    fresh = now - state.get("last_heartbeat", float("-inf")) <= STALE_S
    battery = state.get("battery")
    body = {
        # -1/missing means the FC does not know; report empty so autonomy never dispatches on a guess.
        "battery_percent": battery if battery is not None and 0 <= battery <= 100 else 0,
        "health": "healthy" if fresh else "fault",
        "connected": fresh,
        "flight_status": flight_status(state.get("custom_mode"), state.get("armed", False)),
    }
    if state.get("position"):
        body["position"] = state["position"]
    return body


def parse_drone(text: str) -> tuple[int, str, str]:
    sysid, drone_id, key_path = text.split("=", 2)
    if not (1 <= int(sysid) <= 255) or not drone_id or not key_path:
        raise ValueError(text)
    return int(sysid), drone_id, key_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LakeSafe MAVLink bridge")
    parser.add_argument("--api", required=True)
    parser.add_argument("--mavlink", required=True, help="pymavlink connection string, e.g. udpin:0.0.0.0:14550 or /dev/serial0")
    parser.add_argument("--baud", type=int, default=57600, help="serial links only")
    parser.add_argument("--drone", type=parse_drone, action="append", required=True, metavar="SYSID=DRONE_ID=KEY_PATH")
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args(argv)

    from pymavlink import mavutil

    drones = {sysid: (drone_id, drone_link._load_key(key_path)) for sysid, drone_id, key_path in args.drone}
    states: dict[int, dict] = {sysid: {} for sysid in drones}
    conn = mavutil.mavlink_connection(args.mavlink, baud=args.baud)
    next_send = time.monotonic()
    while True:
        msg = conn.recv_match(type=["HEARTBEAT", "SYS_STATUS", "GLOBAL_POSITION_INT"], blocking=True, timeout=0.1)
        now = time.monotonic()
        if msg is not None and msg.get_srcSystem() in states and msg.get_srcComponent() == AUTOPILOT_COMPONENT:
            state = states[msg.get_srcSystem()]
            if msg.get_type() == "HEARTBEAT" and "last_heartbeat" not in state:
                # A bare serial link streams nothing until asked; through Mission Planner this is harmless.
                conn.mav.request_data_stream_send(msg.get_srcSystem(), AUTOPILOT_COMPONENT, mavutil.mavlink.MAV_DATA_STREAM_ALL, 2, 1)
            update(state, msg, now)
        if now < next_send:
            continue
        next_send = now + args.interval
        # shortcut: posts block the read loop (10 s timeout each); fine for a few drones, thread it for a fleet.
        for sysid, (drone_id, key) in drones.items():
            body = payload(states[sysid], now)
            try:
                status, text = drone_link.post(args.api, f"/api/devices/{drone_id}/heartbeat", key, drone_id, body)
            except OSError as exc:  # URLError and timeouts; never let a network blip stop the bridge
                status, text = "error", str(exc)
            print(sysid, drone_id, body["health"], body["flight_status"], status, text, flush=True)


if __name__ == "__main__":
    sys.exit(main())
