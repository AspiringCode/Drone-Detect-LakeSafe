from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.devices.heartbeat import HeartbeatPayload
from app.devices import mavlink_bridge
from app.devices.mavlink_bridge import flight_status, parse_drone, payload, update


def test_investigation_refuses_ground_or_manual_control_and_keeps_origin(monkeypatch):
    calls = []
    conn = SimpleNamespace(mav=SimpleNamespace(set_position_target_global_int_send=lambda *args: calls.append(args)))
    monkeypatch.setattr(mavlink_bridge, 'set_mode', lambda *args: True)
    cmd = {'command_type': 'investigate', 'investigation_id': 'a', 'target': {'lat':47.6,'lon':-122.1}}
    state = {'armed': False}
    assert mavlink_bridge.run_command(conn, 1, state, cmd)[0] == 'rejected'
    state.update(armed=True, custom_mode=3, position={'lat':47.601,'lon':-122.1,'alt_m':30}, last_heartbeat=0)
    assert mavlink_bridge.run_command(conn, 1, state, cmd)[0] == 'rejected'  # stale telemetry
    state.update(last_heartbeat=mavlink_bridge.time.monotonic(), last_position=mavlink_bridge.time.monotonic(), mission_index=4)
    assert mavlink_bridge.run_command(conn, 1, state, cmd)[0] == 'accepted'
    state['custom_mode'] = 4
    assert state['investigation']['origin']['lat'] == 47.601
    assert len(calls) == 1
    state['custom_mode'] = 6  # pilot RTL must win
    assert mavlink_bridge.run_command(conn, 1, state, {'command_type':'resume_patrol','investigation_id':'a'})[0] == 'rejected'


def test_resume_returns_to_origin_before_restarting_original_mission(monkeypatch):
    calls=[]
    conn=SimpleNamespace(mav=SimpleNamespace(set_position_target_global_int_send=lambda *a:calls.append(('target',a)),
        mission_set_current_send=lambda *a:calls.append(('mission',a))))
    monkeypatch.setattr(mavlink_bridge,'set_mode',lambda *a:calls.append(('mode',a[-1])) or True)
    monkeypatch.setattr(mavlink_bridge,'_reply',lambda *a:SimpleNamespace(seq=7))
    context={'id':'a','origin':{'lat':47.601,'lon':-122.1,'alt_m':30},'mission_index':7,'returning':False}
    state={'armed':True,'custom_mode':4,'position':{'lat':47.6,'lon':-122.1,'alt_m':30},
           'last_position':mavlink_bridge.time.monotonic(),'last_heartbeat':mavlink_bridge.time.monotonic(),'investigation':context}
    assert mavlink_bridge.run_command(conn,1,state,{'command_type':'resume_patrol','investigation_id':'a'})[0]=='accepted'
    mavlink_bridge.advance_investigation(conn,1,state)
    assert not any(c[0]=='mission' for c in calls)
    state['position']['lat']=47.601
    mavlink_bridge.advance_investigation(conn,1,state)
    assert ('mission',(1,1,7)) in calls and ('mode',3) in calls
    assert state['completed_investigation']=='a'


def test_pilot_override_is_journaled_as_cancellation_not_a_completed_return():
    state={'armed':True,'custom_mode':5,'investigation':{'id':'a','returning':False}}
    mavlink_bridge.advance_investigation(None,1,state)
    assert state['cancelled_investigation']=='a'
    assert 'investigation' not in state and 'completed_investigation' not in state


def msg(kind, **fields):
    return SimpleNamespace(get_type=lambda: kind, **fields)


def test_position_units_and_no_fix():
    state = {}
    update(state, msg("GLOBAL_POSITION_INT", lat=476062000, lon=-1223321000, relative_alt=12500), now=0)
    assert state["position"] == {"lat": 47.6062, "lon": -122.3321, "alt_m": 12.5}
    update(state, msg("GLOBAL_POSITION_INT", lat=0, lon=0, relative_alt=0), now=1)
    assert state["position"] is None


@pytest.mark.parametrize(("mode", "armed", "expected"), [
    (3, True, "patrolling"), (4, True, "en_route"), (6, True, "returning"), (21, True, "returning"),
    (9, True, "returning"), (5, True, "patrolling"), (3, False, "idle"), (None, False, "idle"),
])
def test_mode_mapping(mode, armed, expected):
    assert flight_status(mode, armed) == expected


def test_heartbeat_reads_armed_flag_and_goes_stale():
    state = {}
    update(state, msg("HEARTBEAT", custom_mode=4, base_mode=128 | 1), now=10)
    update(state, msg("SYS_STATUS", battery_remaining=76), now=10)
    assert payload(state, now=13) == {"battery_percent": 76, "health": "healthy", "connected": True, "flight_status": "en_route"}
    stale = payload(state, now=13.1)
    assert stale["health"] == "fault" and stale["connected"] is False
    assert payload({}, now=0)["health"] == "fault"


@pytest.mark.parametrize("battery", [None, -1, 255])
def test_unknown_battery_reports_empty(battery):
    state = {} if battery is None else {"battery": battery}
    assert payload(state, now=0)["battery_percent"] == 0


def test_payload_validates():
    state = {}
    update(state, msg("HEARTBEAT", custom_mode=6, base_mode=128), now=0)
    update(state, msg("SYS_STATUS", battery_remaining=40), now=0)
    update(state, msg("GLOBAL_POSITION_INT", lat=476062000, lon=-1223321000, relative_alt=-500), now=0)
    for body in (payload(state, now=1), payload({}, now=1)):
        HeartbeatPayload.model_validate(body)


def test_parse_drone():
    assert parse_drone("2=drone-a=C:/keys/a=b.pem") == (2, "drone-a", "C:/keys/a=b.pem")
    for bad in ("drone-a=a.pem", "0=drone-a=a.pem", "1==a.pem", "x=drone-a=a.pem"):
        with pytest.raises(ValueError):
            parse_drone(bad)


def test_bridge_position_file_feeds_the_detector_only_while_fresh(tmp_path):
    from app.devices.drone_detect import fresh_position

    path = str(tmp_path / "position.json")
    assert fresh_position(path, "d-1") is None  # bridge not running yet
    mavlink_bridge.write_positions(path, {"d-1": {"lat": 47.592, "lon": -122.032, "alt_m": 30.0}, "d-2": None}, now=1000.0)
    assert fresh_position(path, "d-1", now=1003.0) == {"lat": 47.592, "lon": -122.032}
    assert fresh_position(path, "d-1", now=1006.0) is None  # stale: never report an old spot
    assert fresh_position(path, "d-2", now=1001.0) is None  # no GPS fix yet
