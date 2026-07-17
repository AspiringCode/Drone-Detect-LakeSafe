from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import httpx
import jwt
from fastapi import HTTPException

from app.config import SUPABASE_JWT_AUDIENCE, SUPABASE_JWT_ISSUER, SUPABASE_JWT_SECRET, SUPABASE_URL


def _decode_segment(segment: str) -> dict[str, object]:
    try:
        padded = segment + "=" * (-len(segment) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid bearer token") from exc
    if not isinstance(decoded, dict):
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    return decoded


def verify_supabase_jwt(token: str) -> dict[str, object]:
    """Verify a Supabase HS256 or ES256 bearer JWT and return its claims."""
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    header = _decode_segment(parts[0])
    algorithm = header.get("alg")
    if algorithm == "HS256":
        claims = _verify_hs256(token, parts)
    elif algorithm == "ES256":
        claims = _verify_es256(token, header)
    else:
        raise HTTPException(status_code=401, detail="Invalid bearer token")

    _validate_claims(claims)
    return claims


def _verify_hs256(token: str, parts: list[str]) -> dict[str, object]:
    if not SUPABASE_JWT_SECRET:
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    claims = _decode_segment(parts[1])
    expected = hmac.new(
        SUPABASE_JWT_SECRET.encode(), f"{parts[0]}.{parts[1]}".encode(), hashlib.sha256
    ).digest()
    try:
        supplied = base64.urlsafe_b64decode(parts[2] + "=" * (-len(parts[2]) % 4))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid bearer token") from exc
    if not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    return claims


def _verify_es256(token: str, header: dict[str, object]) -> dict[str, object]:
    if not SUPABASE_URL or not isinstance(header.get("kid"), str):
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    try:
        response = httpx.get(f"{SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json", timeout=5.0)
        response.raise_for_status()
        keys = response.json().get("keys", [])
        jwk_data = next(key for key in keys if key.get("kid") == header["kid"])
        key = jwt.PyJWK.from_dict(jwk_data).key
        return jwt.decode(token, key, algorithms=["ES256"], options={"verify_aud": False})
    except (httpx.HTTPError, jwt.PyJWTError, KeyError, StopIteration, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid bearer token") from exc


def _validate_claims(claims: dict[str, object]) -> None:
    try:
        expired = float(claims.get("exp", 0)) <= time.time()
    except (TypeError, ValueError):
        expired = True
    if not isinstance(claims.get("sub"), str) or expired:
        raise HTTPException(status_code=401, detail="Expired or invalid bearer token")
    if SUPABASE_JWT_ISSUER and claims.get("iss") != SUPABASE_JWT_ISSUER:
        raise HTTPException(status_code=401, detail="Invalid bearer token issuer")
    audience = claims.get("aud")
    if SUPABASE_JWT_AUDIENCE and audience != SUPABASE_JWT_AUDIENCE and SUPABASE_JWT_AUDIENCE not in (audience if isinstance(audience, list) else []):
        raise HTTPException(status_code=401, detail="Invalid bearer token audience")
