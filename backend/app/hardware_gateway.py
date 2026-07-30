"""Server-only boundary for the real-device command gateway."""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Protocol


class RealGatewayClient(Protocol):
    def publish(self, url: str, payload: bytes, signature: str) -> None: ...


class SecretProvider(Protocol):
    def resolve(self, reference: str) -> bytes | None: ...


class EnvironmentSecretProvider:
    """Minimal production seam for a server-side secret manager adapter.

    The resolved value is injected into the server environment by deployment;
    the reference remains an identifier and is never treated as key material.
    """

    def __init__(self, *, configured_reference: str | None, resolved_secret: str | None = None) -> None:
        self._configured_reference = configured_reference
        self._resolved_secret = resolved_secret if resolved_secret is not None else os.getenv("REAL_GATEWAY_SIGNING_KEY")

    def resolve(self, reference: str) -> bytes | None:
        if not reference or reference != self._configured_reference or not self._resolved_secret:
            return None
        return self._resolved_secret.encode("utf-8")


class HmacGatewaySigner:
    """Signs outbound command bytes without exposing the signing reference."""

    def __init__(self, signing_key: bytes) -> None:
        if not isinstance(signing_key, bytes) or len(signing_key) < 16:
            raise ValueError("real gateway signing key is not configured")
        self._key = signing_key

    def sign(self, payload: bytes) -> str:
        return hmac.new(self._key, payload, hashlib.sha256).hexdigest()


class HttpRealGatewayClient:
    """A deliberately separate HTTP client used only by the real adapter."""

    def publish(self, url: str, payload: bytes, signature: str) -> None:
        import httpx
        response = httpx.post(url, content=payload, headers={"X-LakeSafe-Signature": signature}, timeout=5.0)
        response.raise_for_status()
