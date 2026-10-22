"""Drone-side client for the signed device endpoints in app/api/devices.py.

Standalone on purpose (stdlib + cryptography only) so the file can be copied
to the companion computer without the backend's dependencies.

  python drone_link.py keygen --key drone.pem            # prints the public key to register
  python drone_link.py heartbeat --api URL --drone-id ID --key drone.pem --battery 87 --lat 47.6 --lon -122.1 --interval 5
  python drone_link.py ack --api URL --drone-id ID --key drone.pem --command-id C --version 3 --status accepted --plan-id P
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def public_key_b64url(key: Ed25519PrivateKey) -> str:
    return _b64url(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def signed_headers(key: Ed25519PrivateKey, drone_id: str, body: bytes, *, sequence: int, timestamp: str) -> dict[str, str]:
    # Must stay byte-identical to app.devices.auth.canonical_request_bytes (guarded by a test).
    canonical = f"{drone_id}\n{timestamp}\n{sequence}\n{hashlib.sha256(body).hexdigest()}".encode("ascii")
    return {
        "Content-Type": "application/json",
        "X-Device-Timestamp": timestamp,
        "X-Device-Sequence": str(sequence),
        "X-Device-Signature": _b64url(key.sign(canonical)),
    }


def _now() -> tuple[int, str]:
    # Epoch milliseconds are strictly increasing across restarts, which is what
    # claim_drone_sequence requires; no sequence file to lose on the drone.
    now = datetime.now(timezone.utc)
    return int(now.timestamp() * 1000), now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def post(api: str, path: str, key: Ed25519PrivateKey, drone_id: str, payload: dict) -> tuple[int, str]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sequence, timestamp = _now()
    request = urllib.request.Request(
        f"{api.rstrip('/')}{path}", data=body, method="POST",
        headers=signed_headers(key, drone_id, body, sequence=sequence, timestamp=timestamp),
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def _load_key(path: str) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SystemExit("key file is not an Ed25519 private key")
    return key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LakeSafe drone link")
    sub = parser.add_subparsers(dest="command", required=True)
    keygen = sub.add_parser("keygen")
    keygen.add_argument("--key", required=True)
    for name in ("heartbeat", "ack"):
        p = sub.add_parser(name)
        p.add_argument("--api", required=True)
        p.add_argument("--drone-id", required=True)
        p.add_argument("--key", required=True)
    hb = sub.choices["heartbeat"]
    hb.add_argument("--battery", type=int, required=True)
    hb.add_argument("--health", choices=("healthy", "fault"), default="healthy")
    hb.add_argument("--disconnected", action="store_true")
    hb.add_argument("--interval", type=float, default=0, help="seconds between beats; 0 sends one")
    hb.add_argument("--lat", type=float)
    hb.add_argument("--lon", type=float)
    hb.add_argument("--alt", type=float)
    hb.add_argument("--status", choices=("idle", "en_route", "patrolling", "investigating", "returning", "charging"), default="idle")
    ack = sub.choices["ack"]
    ack.add_argument("--command-id", required=True)
    ack.add_argument("--version", type=int, required=True)
    ack.add_argument("--status", choices=("accepted", "rejected", "completed"), required=True)
    ack.add_argument("--plan-id")
    ack.add_argument("--detail")
    args = parser.parse_args(argv)

    if args.command == "keygen":
        path = Path(args.key)
        if path.exists():
            raise SystemExit(f"{path} already exists; refusing to overwrite a drone identity")
        key = Ed25519PrivateKey.generate()
        path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        print(public_key_b64url(key))
        return 0

    key = _load_key(args.key)
    if args.command == "ack":
        status, text = post(args.api, f"/api/devices/{args.drone_id}/commands/{args.command_id}/acknowledgements", key, args.drone_id, {
            "plan_id": args.plan_id, "desired_state_version": args.version, "status": args.status, "detail": args.detail,
        })
        print(status, text)
        return 0 if status == 202 else 1

    payload = {"battery_percent": args.battery, "health": args.health, "connected": not args.disconnected, "flight_status": args.status}
    if (args.lat is None) != (args.lon is None):
        raise SystemExit("--lat and --lon go together")
    if args.lat is not None:
        payload["position"] = {"lat": args.lat, "lon": args.lon, "alt_m": args.alt}
    # shortcut: fixed values per run; on the drone, replace with a MAVLink read each beat.
    while True:
        status, text = post(args.api, f"/api/devices/{args.drone_id}/heartbeat", key, args.drone_id, payload)
        print(status, text, flush=True)
        if args.interval <= 0:
            return 0 if status == 202 else 1
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
