"""Forward ArduPilot MAVLink telemetry to LakeSafe as signed heartbeats, and run the website commands they bring back.

Runs off the drone or next to it; copy this file and drone_link.py side by side.
  pip install pymavlink cryptography

Ground laptop (Mission Planner: Ctrl+F > "Mavlink" > UDP Outbound, 127.0.0.1 port 14550):
  python mavlink_bridge.py --api URL --mavlink udpin:0.0.0.0:14550 --drone 1=DRONE_ID=drone.pem
Raspberry Pi on the flight controller's TELEM port:
  python mavlink_bridge.py --api URL --mavlink /dev/serial0 --baud 921600 --drone 1=DRONE_ID=drone.pem
"""

from __future__ import annotations

from datetime import datetime, timezone,timedelta
import argparse
import json
import os
import sys
import time
import tempfile
import math
from pathlib import Path

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
        state['last_position'] = now
    elif kind == 'MISSION_CURRENT':
        state['mission_index'] = msg.seq


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
    if state.get('completed_investigation'):
        body['investigation_completed'] = state['completed_investigation']
    return body


MAV_CMD_DO_SET_MODE = 176
CUSTOM_MODE_ENABLED = 1  # MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
AUTO, LOITER, RTL = 3, 5, 6  # ArduCopter custom_mode numbers
REPLY_TIMEOUT_S = 3.0


def _reply(conn, sysid: int, kinds: list[str]):
    """Next reply of these kinds from this vehicle; telemetry read meanwhile is dropped (a few seconds at most)."""
    deadline = time.monotonic() + REPLY_TIMEOUT_S
    while (left := deadline - time.monotonic()) > 0:
        msg = conn.recv_match(type=kinds, blocking=True, timeout=left)
        if msg is not None and msg.get_srcSystem() == sysid:
            return msg
    return None


def set_mode(conn, sysid: int, mode: int) -> bool:
    conn.mav.command_long_send(sysid, AUTOPILOT_COMPONENT, MAV_CMD_DO_SET_MODE, 0, CUSTOM_MODE_ENABLED, mode, 0, 0, 0, 0, 0)
    while (ack := _reply(conn, sysid, ["COMMAND_ACK"])) is not None:
        if ack.command == MAV_CMD_DO_SET_MODE:
            return ack.result == 0  # MAV_RESULT_ACCEPTED
    return False


def upload_mission(conn, sysid: int, rows: list[list[float]]) -> bool:
    """MAVLink mission upload: announce the count, answer each item request, wait for the ACK."""
    conn.mav.mission_count_send(sysid, AUTOPILOT_COMPONENT, len(rows), 0)
    while (msg := _reply(conn, sysid, ["MISSION_REQUEST_INT", "MISSION_REQUEST", "MISSION_ACK"])) is not None:
        if msg.get_type() == "MISSION_ACK":
            return msg.type == 0  # MAV_MISSION_ACCEPTED
        if not 0 <= msg.seq < len(rows):
            return False
        frame, command, p1, p2, p3, p4, lat, lon, alt = rows[msg.seq]
        conn.mav.mission_item_int_send(sysid, AUTOPILOT_COMPONENT, msg.seq, int(frame), int(command), 0, 1,
                                       p1, p2, p3, p4, int(lat * 1e7), int(lon * 1e7), alt, 0)
    return False


def run_command(conn, sysid: int, state: dict, command: dict) -> tuple[str, str]:
    """Carry out one website command; returns (accepted|rejected, detail). The RC transmitter always overrides."""
    kind = command.get("command_type")
    armed = state.get("armed", False)
    if kind in ('investigate', 'resume_patrol'):
        now = time.monotonic()
        position = state.get('position') or {}
        if (not armed or now-state.get('last_heartbeat',float('-inf'))>STALE_S
                or now-state.get('last_position',float('-inf'))>STALE_S
                or not isinstance(position.get('alt_m'), (int,float)) or not 5<=position['alt_m']<=120):
            return 'rejected', 'Fresh airborne telemetry and a safe relative altitude are required'
        if kind == 'investigate':
            if state.get('custom_mode') != AUTO or state.get('mission_index') is None or state.get('investigation'):
                return 'rejected', 'Only an aircraft already patrolling in AUTO may investigate'
            target = command.get('target') or {}
            if not all(isinstance(target.get(k),(int,float)) and math.isfinite(target[k]) for k in ('lat','lon')) or not -90<=target['lat']<=90 or not -180<=target['lon']<=180:
                return 'rejected', 'Invalid investigation location'
            context = {'id':command['investigation_id'], 'origin':dict(position), 'mission_index':state['mission_index'], 'returning':False,
                       'deadline':(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()}
            if not set_mode(conn,sysid,4):
                return 'rejected','Flight controller refused GUIDED'
            state['investigation'] = context
        else:
            context = state.get('investigation') or command.get('restore_context')
            if not context or context.get('id') != command.get('investigation_id') or state.get('custom_mode') != 4:
                return 'rejected','Original patrol context unavailable or pilot changed flight mode; pilot review required'
            target = context['origin']
            context['returning'] = True
            state['investigation'] = context
        # Keep the current altitude; no arming, takeoff, landing, or descent is issued.
        conn.mav.set_position_target_global_int_send(0,sysid,AUTOPILOT_COMPONENT,6,3576,
            int(target['lat']*1e7),int(target['lon']*1e7),position['alt_m'],0,0,0,0,0,0,0,0)
        return 'accepted', 'Returning to original patrol position' if kind=='resume_patrol' else 'Investigation target requested; arrival is not corroboration'
    if kind in ("return_to_reserve", "safety_hold"):
        cancelled=state.pop('investigation',None)
        if cancelled: state['cancelled_investigation']=cancelled['id']
        if not armed:
            return "accepted", "on the ground; nothing to do"
        mode, name = (RTL, "RTL") if kind == "return_to_reserve" else (LOITER, "LOITER")
        return ("accepted", f"switched to {name}") if set_mode(conn, sysid, mode) else ("rejected", f"flight controller refused {name}")
    if kind == "patrol":
        if not upload_mission(conn, sysid, command.get("mission") or []):
            return "rejected", "mission upload failed"
        # Arming stays with the pilot: on the ground the mission just waits for them.
        if not armed:
            return "accepted", "mission uploaded; arm and switch to AUTO to fly it"
        return ("accepted", "mission uploaded; flying it in AUTO") if set_mode(conn, sysid, AUTO) else ("rejected", "mission uploaded but AUTO was refused")
    return "rejected", f"unsupported command {kind!r}"


def handle_reply(conn, sysid: int, state: dict, text: str, done: dict | set, persist=None) -> list[tuple[dict, str, str]]:
    """Upload once and replay cached outcomes until the signed acknowledgement arrives."""
    try:
        commands = json.loads(text).get("commands") or []
    except (ValueError, AttributeError):
        return []
    results = []
    for command in commands:
        command_id = command.get("command_id")
        if not isinstance(command_id, str):
            continue
        if isinstance(done, set):
            # Compatibility for callers that only deduplicate unacknowledged
            # one-shot actions; the running bridge uses persisted outcomes.
            if command_id in done:
                continue
            done.add(command_id)
            results.append((command, *run_command(conn, sysid, state, command)))
            continue
        if command_id not in done:
            context_key = 'investigation:'+str(command.get('investigation_id'))
            if command.get('command_type') == 'resume_patrol':
                command = {**command,'restore_context':done.get(context_key)}
            if command.get('command_type') == 'investigate':
                # Persist the patrol origin before any flight command can execute.
                done[context_key] = {'id':command.get('investigation_id'),'origin':dict(state.get('position') or {}),
                                     'mission_index':state.get('mission_index'),'returning':False,
                                     'deadline':(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()}
            try:
                expires = datetime.fromisoformat(command["expires_at"].replace("Z", "+00:00"))
                valid = expires > datetime.now(timezone.utc)
            except (KeyError, ValueError, TypeError):
                valid = False
            # Journal an uncertain result before touching the controller. A
            # crash during upload must require operator review, not re-upload.
            done[command_id] = {"status": "rejected", "detail": "Prior upload outcome is unknown; review the mission again", "expires_at": command.get("expires_at")}
            if persist is not None:
                persist()
            outcome, detail = run_command(conn, sysid, state, command) if valid else ("rejected", "Command expired or has no valid expiry")
            if outcome=='accepted' and state.get('investigation'):
                done[context_key] = dict(state['investigation'])
            done[command_id] = {"status": outcome, "detail": detail, "expires_at": command.get("expires_at")}
            if persist is not None:
                persist()
        cached = done[command_id]
        results.append((command, cached["status"], cached["detail"]))
    return results


def acknowledgement_request(drone_id: str, command: dict, outcome: str, detail: str):
    if command.get('investigation_ack'):
        return f"/api/devices/{drone_id}/investigation-commands/{command['command_id']}/acknowledgements", {'status':outcome,'detail':detail}
    if command.get("patrol_ack"):
        return f"/api/devices/{drone_id}/patrol-commands/{command['command_id']}/acknowledgements", {
            "command_id": command["command_id"], "status": outcome, "detail": detail,
        }
    return f"/api/devices/{drone_id}/commands/{command['command_id']}/acknowledgements", {
        "plan_id": command.get("plan_id"), "desired_state_version": command.get("desired_state_version"),
        "status": outcome, "detail": detail,
    }


def load_outcomes(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except FileNotFoundError:
        return {}


def default_outcome_file() -> str:
    if os.name == "nt":
        parent = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "LakeSafe"
    else:
        parent = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / "lakesafe"
    return str(parent / "command-outcomes.json")


def save_outcomes(path: str, outcomes: dict) -> None:
    target = Path(path).expanduser()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".command-outcomes-", dir=str(target.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(outcomes, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_positions(path: str, positions: dict[str, dict], now: float) -> None:
    """Latest fix per drone for drone_detect.py; replaced atomically so a reader never sees half a file."""
    data = {drone_id: {**position, "at": now} for drone_id, position in positions.items() if position}
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    os.replace(tmp, path)


def parse_drone(text: str) -> tuple[int, str, str]:
    sysid, drone_id, key_path = text.split("=", 2)
    if not (1 <= int(sysid) <= 255) or not drone_id or not key_path:
        raise ValueError(text)
    return int(sysid), drone_id, key_path


def advance_investigation(conn, sysid, state):
    context = state.get('investigation')
    if not context:
        return
    if not state.get('armed') or state.get('custom_mode') != 4:
        state['cancelled_investigation']=context['id']
        state.pop('investigation',None)  # pilot/safety mode always wins
        return
    if not context.get('returning'):
        if context.get('deadline') and datetime.fromisoformat(context['deadline'])<=datetime.now(timezone.utc):
            if run_command(conn,sysid,state,{'command_type':'resume_patrol','investigation_id':context['id']})[0]!='accepted':
                return
        else:
            return
    position = state.get('position') or {}
    origin = context['origin']
    if not position or time.monotonic()-state.get('last_position',float('-inf'))>STALE_S:
        return
    distance = math.hypot((position['lat']-origin['lat'])*111320,
                          (position['lon']-origin['lon'])*111320*math.cos(math.radians(origin['lat'])))
    if distance<=8 and context.get('mission_index') is not None:
        conn.mav.mission_set_current_send(sysid,AUTOPILOT_COMPONENT,context['mission_index'])
        current=_reply(conn,sysid,['MISSION_CURRENT'])
        if current is not None and current.seq==context['mission_index'] and set_mode(conn,sysid,AUTO):
            state['completed_investigation'] = context['id']
            state.pop('investigation',None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LakeSafe MAVLink bridge")
    parser.add_argument("--api", required=True)
    parser.add_argument("--mavlink", required=True, help="pymavlink connection string, e.g. udpin:0.0.0.0:14550 or /dev/serial0")
    parser.add_argument("--baud", type=int, default=57600, help="serial links only")
    parser.add_argument("--drone", type=parse_drone, action="append", required=True, metavar="SYSID=DRONE_ID=KEY_PATH")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--position-file", help="also write each drone's latest fix here for drone_detect.py")
    parser.add_argument("--outcome-file", default=default_outcome_file(), help="durable command upload outcomes; keep this file across bridge restarts")
    args = parser.parse_args(argv)

    from pymavlink import mavutil

    drones = {sysid: (drone_id, drone_link._load_key(key_path)) for sysid, drone_id, key_path in args.drone}
    states: dict[int, dict] = {sysid: {} for sysid in drones}
    outcomes = load_outcomes(args.outcome_file)
    done = {sysid: outcomes.setdefault(drone_id, {}) for sysid, (drone_id, _) in drones.items()}
    for sysid in states:
        for key,value in done[sysid].items():
            if key.startswith('investigation:') and isinstance(value,dict) and value.get('origin') and not value.get('completed'):
                states[sysid]['investigation'] = dict(value)
    conn = mavutil.mavlink_connection(args.mavlink, baud=args.baud)
    next_send = time.monotonic()
    while True:
        msg = conn.recv_match(type=["HEARTBEAT", "SYS_STATUS", "GLOBAL_POSITION_INT", "MISSION_CURRENT"], blocking=True, timeout=0.1)
        now = time.monotonic()
        if msg is not None and msg.get_srcSystem() in states and msg.get_srcComponent() == AUTOPILOT_COMPONENT:
            state = states[msg.get_srcSystem()]
            if msg.get_type() == "HEARTBEAT" and "last_heartbeat" not in state:
                # A bare serial link streams nothing until asked; through Mission Planner this is harmless.
                conn.mav.request_data_stream_send(msg.get_srcSystem(), AUTOPILOT_COMPONENT, mavutil.mavlink.MAV_DATA_STREAM_ALL, 2, 1)
            update(state, msg, now)
            advance_investigation(conn,msg.get_srcSystem(),state)
            completed = state.get('completed_investigation')
            if completed and not done[msg.get_srcSystem()].get('investigation:'+completed,{}).get('completed'):
                done[msg.get_srcSystem()]['investigation:'+completed] = {'completed':True}
                save_outcomes(args.outcome_file,outcomes)
            cancelled=state.pop('cancelled_investigation',None)
            if cancelled:
                done[msg.get_srcSystem()]['investigation:'+cancelled]={'completed':True,'cancelled':True}
                save_outcomes(args.outcome_file,outcomes)
        if now < next_send:
            continue
        next_send = now + args.interval
        if args.position_file:
            write_positions(args.position_file, {drone_id: states[sysid].get("position") for sysid, (drone_id, _) in drones.items()}, time.time())
        # shortcut: posts block the read loop (10 s timeout each); fine for a few drones, thread it for a fleet.
        for sysid, (drone_id, key) in drones.items():
            body = payload(states[sysid], now)
            try:
                status, text = drone_link.post(args.api, f"/api/devices/{drone_id}/heartbeat", key, drone_id, body)
            except OSError as exc:  # URLError and timeouts; never let a network blip stop the bridge
                status, text = "error", str(exc)
            print(sysid, drone_id, body["health"], body["flight_status"], status, text, flush=True)
            if status != 202:
                continue
            results = handle_reply(conn, sysid, states[sysid], text, done[sysid],
                persist=lambda: save_outcomes(args.outcome_file, outcomes))
            for command, outcome, detail in results:
                print(sysid, drone_id, "command", command.get("command_type"), outcome, detail, flush=True)
                if not command.get("ack"):
                    continue
                try:
                    path, acknowledgement = acknowledgement_request(drone_id, command, outcome, detail)
                    ack_status, ack_text = drone_link.post(args.api, path, key, drone_id, acknowledgement)
                    if ack_status != 202:
                        print(sysid, drone_id, "ack pending", ack_status, ack_text, flush=True)
                except OSError as exc:
                    # The cached result is sent again on the next heartbeat reply.
                    print(sysid, drone_id, "ack failed", exc, flush=True)


if __name__ == "__main__":
    sys.exit(main())
