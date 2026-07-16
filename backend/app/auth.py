from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import HTTPException

from app.config import SUPABASE_JWT_AUDIENCE, SUPABASE_JWT_ISSUER, SUPABASE_JWT_SECRET


def _decode_segment(segment: str) -> dict[str, object]:
    try:
        padded = segment + "=" * (-len(segment) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid bearer token") from exc


def verify_supabase_jwt(token: str) -> dict[str, object]:
    """Verify a Supabase HS256 bearer JWT and return its claims."""
    if not SUPABASE_JWT_SECRET:
        raise HTTPException(status_code=503, detail="JWT verification is not configured")
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    header = _decode_segment(parts[0])
    claims = _decode_segment(parts[1])
    if header.get("alg") != "HS256":
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    expected = hmac.new(
        SUPABASE_JWT_SECRET.encode(), f"{parts[0]}.{parts[1]}".encode(), hashlib.sha256
    ).digest()
    try:
        supplied = base64.urlsafe_b64decode(parts[2] + "=" * (-len(parts[2]) % 4))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid bearer token") from exc
    if not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="Invalid bearer token")
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
    return claims
