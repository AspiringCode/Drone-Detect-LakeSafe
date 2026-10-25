"""Per-drone command mailbox handed out in heartbeat replies.

The drone only makes outbound requests, so it works behind a hotspot or phone
NAT; nothing has to reach into it. Outbox commands stay until the drone's
signed acknowledgement lands or they expire. Reviewed mission uploads use
the separate durable patrol repository.
shortcut: in-memory and single-worker like live_positions; move to the database if the API ever runs several workers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

_mailbox: dict[str, dict[str, dict]] = {}


def queue(drone_id: str, command: dict) -> None:
    _mailbox.setdefault(drone_id, {})[command["command_id"]] = command


def pending(drone_id: str, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    box = _mailbox.get(drone_id, {})
    for command_id, command in list(box.items()):
        if datetime.fromisoformat(command["expires_at"].replace("Z", "+00:00")) <= now:
            del box[command_id]
    handed = list(box.values())
    for command in handed:
        if not command["ack"]:
            del box[command["command_id"]]
    return handed


def discard(drone_id: str, command_id: str) -> None:
    _mailbox.get(drone_id, {}).pop(command_id, None)


class MailboxGateway:
    """RealAdapter transport for REAL_GATEWAY_URL=heartbeat: queue instead of POSTing to a gateway.

    The HMAC signature is unused: the drone collects commands over its own signed, authenticated request.
    """

    def publish(self, url: str, payload: bytes, signature: str) -> None:
        del url, signature
        envelope = json.loads(payload)
        queue(envelope["drone_id"], {
            "command_id": envelope["command_id"], "command_type": envelope["command_type"],
            "desired_state_version": envelope["desired_state_version"],
            "plan_id": envelope["payload"].get("plan_id"), "expires_at": envelope["payload"]["expires_at"],
            "ack": True,
        })
