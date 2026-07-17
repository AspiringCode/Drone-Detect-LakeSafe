from __future__ import annotations

import base64
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException

from app import auth


def _base64url_uint(value: int) -> str:
    return base64.urlsafe_b64encode(value.to_bytes(32, "big")).rstrip(b"=").decode()


def _es256_jwks(private_key: ec.EllipticCurvePrivateKey) -> dict[str, object]:
    numbers = private_key.public_key().public_numbers()
    return {
        "keys": [
            {
                "kty": "EC",
                "crv": "P-256",
                "kid": "supabase-p256-key",
                "use": "sig",
                "alg": "ES256",
                "x": _base64url_uint(numbers.x),
                "y": _base64url_uint(numbers.y),
            }
        ]
    }


def _es256_token(private_key: ec.EllipticCurvePrivateKey) -> str:
    return jwt.encode(
        {"sub": "user-1", "exp": time.time() + 3600},
        private_key,
        algorithm="ES256",
        headers={"kid": "supabase-p256-key"},
    )


def _configure_es256(monkeypatch: pytest.MonkeyPatch, jwks: dict[str, object]) -> None:
    monkeypatch.setattr(auth, "SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setattr(auth, "SUPABASE_JWT_SECRET", None)
    monkeypatch.setattr(auth, "SUPABASE_JWT_ISSUER", None)
    monkeypatch.setattr(auth, "SUPABASE_JWT_AUDIENCE", None)

    def mocked_get(url: str, **_: object) -> httpx.Response:
        assert url == "https://project.supabase.co/auth/v1/.well-known/jwks.json"
        return httpx.Response(200, json=jwks, request=httpx.Request("GET", url))

    monkeypatch.setattr(auth.httpx, "get", mocked_get)


def test_verify_supabase_jwt_accepts_es256_token_from_supabase_jwks(monkeypatch: pytest.MonkeyPatch):
    private_key = ec.generate_private_key(ec.SECP256R1())
    _configure_es256(monkeypatch, _es256_jwks(private_key))

    claims = auth.verify_supabase_jwt(_es256_token(private_key))

    assert claims["sub"] == "user-1"


def test_verify_supabase_jwt_rejects_es256_token_with_invalid_signature(monkeypatch: pytest.MonkeyPatch):
    trusted_key = ec.generate_private_key(ec.SECP256R1())
    _configure_es256(monkeypatch, _es256_jwks(trusted_key))

    with pytest.raises(HTTPException, match="Invalid bearer token") as error:
        auth.verify_supabase_jwt(_es256_token(ec.generate_private_key(ec.SECP256R1())))

    assert error.value.status_code == 401


def test_verify_supabase_jwt_rejects_hs256_when_only_es256_jwks_is_configured(
    monkeypatch: pytest.MonkeyPatch,
):
    private_key = ec.generate_private_key(ec.SECP256R1())
    _configure_es256(monkeypatch, _es256_jwks(private_key))
    token = jwt.encode(
        {"sub": "user-1", "exp": time.time() + 3600},
        "attacker-secret-that-is-at-least-32-bytes",
        algorithm="HS256",
    )

    with pytest.raises(HTTPException, match="Invalid bearer token") as error:
        auth.verify_supabase_jwt(token)

    assert error.value.status_code == 401
