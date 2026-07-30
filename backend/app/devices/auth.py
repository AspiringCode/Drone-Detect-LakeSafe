"""Verification for canonical, signed real-device requests."""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.config import DEVICE_CLOCK_SKEW_SECONDS

_RFC3339_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
_BASE64URL = re.compile(r"^[A-Za-z0-9_-]+$")


class DeviceAuthenticationError(RuntimeError):
    """Deliberately non-specific device authentication failure."""


class DeviceReplayError(DeviceAuthenticationError):
    pass


@dataclass(frozen=True)
class DevicePrincipal:
    drone_id: str
    station_id: str
    credential_id: str


class DeviceAuthRepository(Protocol):
    def active_credential(self, drone_id: str) -> dict | None: ...
    def claim_sequence(self, drone_id: str, sequence: int) -> bool: ...


def canonical_request_bytes(drone_id: str, timestamp: str, sequence: int, body: bytes) -> bytes:
    return f"{drone_id}\n{timestamp}\n{sequence}\n{hashlib.sha256(body).hexdigest()}".encode("ascii")


def decode_base64url(value: str, *, expected_length: int) -> bytes:
    """Decode a canonical unpadded base64url value of an exact byte length."""
    if not isinstance(value, str) or not _BASE64URL.fullmatch(value):
        raise DeviceAuthenticationError()
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as exc:
        raise DeviceAuthenticationError() from exc
    if len(decoded) != expected_length:
        raise DeviceAuthenticationError()
    return decoded


def _parse_timestamp(timestamp: str) -> datetime:
    if not isinstance(timestamp, str) or not _RFC3339_UTC.fullmatch(timestamp):
        raise DeviceAuthenticationError()
    try:
        value = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DeviceAuthenticationError() from exc
    if value.tzinfo is None or abs(datetime.now(timezone.utc) - value) > timedelta(seconds=DEVICE_CLOCK_SKEW_SECONDS):
        raise DeviceAuthenticationError()
    return value


def verify_device_request(drone_id: str, timestamp: str, sequence: int, signature: str, body: bytes, repository: DeviceAuthRepository) -> DevicePrincipal:
    """Verify before parsing a device payload and atomically consume its sequence."""
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0 or not isinstance(body, bytes):
        raise DeviceAuthenticationError()
    _parse_timestamp(timestamp)
    credential = repository.active_credential(drone_id)
    if not isinstance(credential, dict):
        raise DeviceAuthenticationError()
    try:
        Ed25519PublicKey.from_public_bytes(decode_base64url(str(credential.get("public_key", "")), expected_length=32)).verify(
            decode_base64url(signature, expected_length=64), canonical_request_bytes(drone_id, timestamp, sequence, body)
        )
    except (InvalidSignature, ValueError, DeviceAuthenticationError) as exc:
        raise DeviceAuthenticationError() from exc
    if not repository.claim_sequence(drone_id, sequence):
        raise DeviceReplayError()
    station_id, credential_id = credential.get("station_id"), credential.get("credential_id")
    if not isinstance(station_id, str) or not isinstance(credential_id, str):
        raise DeviceAuthenticationError()
    return DevicePrincipal(drone_id, station_id, credential_id)
