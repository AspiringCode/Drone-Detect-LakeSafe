"""Server-only boundary for the real-device command gateway."""

from __future__ import annotations

import hashlib
import hmac
from typing import Protocol


class RealGatewayClient(Protocol):
    def publish(self, url: str, payload: bytes, signature: str) -> None: ...


class HmacGatewaySigner:
    """Signs outbound command bytes without exposing the signing reference."""

    def __init__(self, signing_key_ref: str) -> None:
        if not signing_key_ref:
            raise ValueError("real gateway signing key is not configured")
        self._key = signing_key_ref.encode("utf-8")

    def sign(self, payload: bytes) -> str:
        return hmac.new(self._key, payload, hashlib.sha256).hexdigest()


class HttpRealGatewayClient:
    """A deliberately separate HTTP client used only by the real adapter."""

    def publish(self, url: str, payload: bytes, signature: str) -> None:
        import httpx
        response = httpx.post(url, content=payload, headers={"X-LakeSafe-Signature": signature}, timeout=5.0)
        response.raise_for_status()

