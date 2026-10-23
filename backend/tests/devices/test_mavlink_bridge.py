from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.devices.heartbeat import HeartbeatPayload
from app.devices import mavlink_bridge
from app.devices.mavlink_bridge import flight_status, parse_drone, payload, update


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
