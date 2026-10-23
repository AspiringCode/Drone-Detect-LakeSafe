import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.devices import live_commands, mavlink_bridge
from app.devices.live_commands import MailboxGateway

NOW = datetime(2026, 10, 22, 20, 0, tzinfo=timezone.utc)
LATER = (NOW + timedelta(minutes=5)).isoformat()


def test_outbox_commands_wait_for_their_ack_patrols_go_once_and_both_expire(monkeypatch):
    monkeypatch.setattr(live_commands, "_mailbox", {})
    MailboxGateway().publish("heartbeat", json.dumps({
        "command_id": "c-1", "drone_id": "d-1", "command_type": "return_to_reserve", "desired_state_version": 4,
        "station_id": "st-1", "lake_id": "test-drone-field", "payload": {"source": "real", "expires_at": LATER},
    }).encode(), "unused")
    live_commands.queue("d-1", {"command_id": "p-1", "command_type": "patrol", "expires_at": LATER, "mission": [], "ack": False})
    assert [c["command_id"] for c in live_commands.pending("d-1", NOW)] == ["c-1", "p-1"]
    [rtl] = live_commands.pending("d-1", NOW)
    assert (rtl["command_type"], rtl["desired_state_version"], rtl["plan_id"], rtl["ack"]) == ("return_to_reserve", 4, None, True)
    assert live_commands.pending("d-1", NOW + timedelta(minutes=6)) == []
    live_commands.queue("d-1", {**rtl})
    live_commands.discard("d-1", "c-1")
    assert live_commands.pending("d-1", NOW) == [] and live_commands.pending("nobody", NOW) == []


class FakeVehicle:
    """Answers the MAVLink calls the bridge makes, like ArduCopter would."""

    def __init__(self, *, accept_mode=True):
        self.sent, self.inbox, self.accept_mode = [], [], accept_mode
        self.mav = SimpleNamespace(command_long_send=self._command, mission_count_send=self._count, mission_item_int_send=self._item)

    def _msg(self, kind, **fields):
        self.inbox.append(SimpleNamespace(get_type=lambda: kind, get_srcSystem=lambda: 1, **fields))

    def _command(self, *args):
        self.sent.append(("mode", args[5]))
        self._msg("COMMAND_ACK", command=args[2], result=0 if self.accept_mode else 4)

    def _count(self, sysid, comp, count, mission_type):
        self.count = count
        self._msg("MISSION_REQUEST_INT", seq=0)

    def _item(self, sysid, comp, seq, *rest):
        self.sent.append(("item", seq, rest[-4] / 1e7))
        if seq + 1 < self.count:
            self._msg("MISSION_REQUEST_INT", seq=seq + 1)
        else:
            self._msg("MISSION_ACK", type=0)

    def recv_match(self, type, blocking, timeout):
        return self.inbox.pop(0) if self.inbox else None


ROWS = [[0, 16, 0, 0, 0, 0, 47.59, -122.03, 0], [3, 22, 15, 0, 0, 0, 47.59, -122.03, 30], [2, 20, 0, 0, 0, 0, 0, 0, 0]]


def test_bridge_switches_modes_only_when_airborne_and_uploads_patrols():
    vehicle = FakeVehicle()
    assert mavlink_bridge.run_command(vehicle, 1, {"armed": False}, {"command_type": "return_to_reserve"})[0] == "accepted"
    assert vehicle.sent == []
    assert mavlink_bridge.run_command(vehicle, 1, {"armed": True}, {"command_type": "return_to_reserve"}) == ("accepted", "switched to RTL")
    assert mavlink_bridge.run_command(vehicle, 1, {"armed": True}, {"command_type": "safety_hold"}) == ("accepted", "switched to LOITER")
    assert vehicle.sent == [("mode", 6), ("mode", 5)]

    vehicle = FakeVehicle()
    outcome, detail = mavlink_bridge.run_command(vehicle, 1, {"armed": False}, {"command_type": "patrol", "mission": ROWS})
    assert outcome == "accepted" and "arm" in detail
    assert vehicle.sent == [("item", 0, 47.59), ("item", 1, 47.59), ("item", 2, 0.0)]

    refused = FakeVehicle(accept_mode=False)
    assert mavlink_bridge.run_command(refused, 1, {"armed": True}, {"command_type": "safety_hold"})[0] == "rejected"
    assert mavlink_bridge.run_command(FakeVehicle(), 1, {}, {"command_type": "apply_assignment"})[0] == "rejected"


def test_bridge_runs_each_command_from_a_reply_once():
    vehicle, done = FakeVehicle(), set()
    reply = json.dumps({"received_sequence": 1, "commands": [{"command_id": "c-1", "command_type": "safety_hold"}]})
    assert [r[1] for r in mavlink_bridge.handle_reply(vehicle, 1, {"armed": True}, reply, done)] == ["accepted"]
    assert mavlink_bridge.handle_reply(vehicle, 1, {"armed": True}, reply, done) == []
    assert mavlink_bridge.handle_reply(vehicle, 1, {}, "not json", done) == []
