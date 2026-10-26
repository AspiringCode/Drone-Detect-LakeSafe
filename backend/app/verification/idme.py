from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib.parse import urlencode,urlparse

import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app import config
from app.stations.models import IdMeVerification, VerificationSession, VerificationSessionCreate
from app.stations.repository import WorkflowConflict, WorkflowRepository


class IdMeVerificationError(RuntimeError):
    """A provider callback is invalid or cannot establish eligibility."""


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class IdMeSettings:
    client_id: str
    client_secret: str
    redirect_uri: str
    issuer: str
    audience: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    userinfo_endpoint: str
    success_url: str
    failure_url: str
    scope: str = 'openid'

    @classmethod
    def from_config(cls) -> "IdMeSettings":
        required = {
            "IDME_CLIENT_ID": config.IDME_CLIENT_ID,
            "IDME_CLIENT_SECRET": config.IDME_CLIENT_SECRET,
            "IDME_REDIRECT_URI": config.IDME_REDIRECT_URI,
            "IDME_AUDIENCE": config.IDME_AUDIENCE,
            'IDME_SCOPE': config.IDME_SCOPE,
        }
        if any(not value for value in required.values()):
            raise IdMeVerificationError("ID.me verification is not configured")
        _fernet()
        for url in (config.IDME_PROFILE_SUCCESS_URL,config.IDME_PROFILE_FAILURE_URL,config.IDME_REDIRECT_URI,
                    config.IDME_AUTHORIZATION_ENDPOINT,config.IDME_TOKEN_ENDPOINT,config.IDME_USERINFO_ENDPOINT,config.IDME_JWKS_URI):
            parsed=urlparse(url or '')
            if not parsed.hostname or parsed.username or parsed.password or parsed.fragment or (
                parsed.scheme!='https' and not(parsed.scheme=='http' and parsed.hostname in {'localhost','127.0.0.1'})):
                raise IdMeVerificationError('ID.me requires configured absolute callback and application URLs')
        if 'openid' not in config.IDME_SCOPE.split() or len(config.IDME_SCOPE.split())<2:
            raise IdMeVerificationError('ID.me affiliation policy scope is not configured')
        return cls(
            client_id=str(config.IDME_CLIENT_ID), client_secret=str(config.IDME_CLIENT_SECRET),
            redirect_uri=str(config.IDME_REDIRECT_URI), issuer=config.IDME_ISSUER,
            audience=str(config.IDME_AUDIENCE), authorization_endpoint=config.IDME_AUTHORIZATION_ENDPOINT,
            token_endpoint=config.IDME_TOKEN_ENDPOINT, jwks_uri=config.IDME_JWKS_URI,
            userinfo_endpoint=config.IDME_USERINFO_ENDPOINT,
            success_url=config.IDME_PROFILE_SUCCESS_URL, failure_url=config.IDME_PROFILE_FAILURE_URL,
            scope=config.IDME_SCOPE,
        )


@dataclass(frozen=True)
class SessionSecrets:
    state: str
    nonce: str
    verifier: str
    expires_at: datetime


def _fernet(key: str | None = None) -> Fernet:
    try:
        return Fernet((key or config.VERIFICATION_SESSION_ENCRYPTION_KEY or "").encode())
    except (ValueError, TypeError) as exc:
        raise IdMeVerificationError("Verification session encryption is not configured") from exc


def _encrypt(secret: SessionSecrets, key: str | None = None) -> str:
    return _fernet(key).encrypt(json.dumps({"nonce": secret.nonce, "verifier": secret.verifier}).encode()).decode()


def _decrypt(ciphertext: str, key: str | None = None) -> tuple[str, str]:
    try:
        value = json.loads(_fernet(key).decrypt(ciphertext.encode()))
        nonce, verifier = value["nonce"], value["verifier"]
    except (InvalidToken, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise IdMeVerificationError("Verification session cannot be recovered") from exc
    if not isinstance(nonce, str) or not isinstance(verifier, str):
        raise IdMeVerificationError("Verification session cannot be recovered")
    return nonce, verifier


def start_authorization(user_id: str, repository: WorkflowRepository, settings: IdMeSettings, *, now: datetime | None = None, encryption_key: str | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    secret = SessionSecrets(secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(64), now + timedelta(minutes=10))
    repository.create_verification_session(VerificationSessionCreate(
        state_hash=_hash(secret.state), nonce_hash=_hash(secret.nonce), verifier_hash=_hash(secret.verifier),
        encrypted_secrets=_encrypt(secret, encryption_key), user_id=user_id, expires_at=secret.expires_at,
    ))
    return f"{settings.authorization_endpoint}?{urlencode({
        'response_type': 'code', 'client_id': settings.client_id, 'redirect_uri': settings.redirect_uri,
        'scope': settings.scope, 'state': secret.state, 'nonce': secret.nonce,
        'code_challenge': _pkce_challenge(secret.verifier), 'code_challenge_method': 'S256',
    })}"


def _jwks(url: str) -> list[dict]:
    response = httpx.get(url, timeout=5.0)
    response.raise_for_status()
    values = response.json().get("keys")
    if not isinstance(values, list):
        raise IdMeVerificationError("ID.me key set is invalid")
    return values


def validate_id_token(token: str, settings: IdMeSettings, expected_nonce: str, *, jwks_fetcher: Callable[[str], list[dict]] = _jwks) -> dict[str, object]:
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
            raise IdMeVerificationError("ID.me token algorithm is not allowed")
        key_data = next(key for key in jwks_fetcher(settings.jwks_uri) if key.get("kid") == header["kid"] and key.get("kty") == "RSA")
        claims = jwt.decode(token, jwt.PyJWK.from_dict(key_data).key, algorithms=["RS256"], issuer=settings.issuer, audience=settings.audience, options={"require": ["exp", "sub", "iss", "aud", "nonce"]})
    except (jwt.PyJWTError, StopIteration, TypeError, ValueError, httpx.HTTPError) as exc:
        raise IdMeVerificationError("ID.me identity token is invalid") from exc
    if not secrets.compare_digest(str(claims.get("nonce", "")), expected_nonce):
        raise IdMeVerificationError("ID.me token nonce is invalid")
    return claims


def fetch_userinfo(access_token: str, settings: IdMeSettings) -> dict[str, object]:
    response = httpx.get(settings.userinfo_endpoint, headers={"Authorization": f"Bearer {access_token}"}, timeout=10.0)
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict):
        raise IdMeVerificationError("ID.me UserInfo response is invalid")
    return value


def _identity_from_userinfo(id_token_claims: dict[str, object], userinfo: dict[str, object]) -> tuple[str, str, str]:
    subject = userinfo.get("sub")
    if not isinstance(subject, str) or not secrets.compare_digest(subject, str(id_token_claims.get("sub", ""))):
        raise IdMeVerificationError("ID.me UserInfo subject is invalid")
    name, agency, affiliations = userinfo.get("name"), userinfo.get("agency"), userinfo.get("affiliations")
    verified_us_le = isinstance(affiliations, list) and any(
        isinstance(item, dict) and item.get("verified") is True
        and str(item.get("country", "")).upper() == "US"
        and str(item.get("type", item.get("value", ""))).strip().casefold() in {"law_enforcement", "us_law_enforcement"}
        for item in affiliations
    )
    if not all(isinstance(value, str) and value.strip() for value in (name, agency)) or not verified_us_le:
        raise IdMeVerificationError("ID.me did not verify a US law-enforcement affiliation")
    return subject, name.strip(), agency.strip()


def complete_authorization(*, state: str, code: str, repository: WorkflowRepository, settings: IdMeSettings, now: datetime | None = None, token_exchange: Callable[[str, str, IdMeSettings], dict] | None = None, userinfo_fetcher: Callable[[str, IdMeSettings], dict] = fetch_userinfo, jwks_fetcher: Callable[[str], list[dict]] = _jwks, encryption_key: str | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    try:
        session: VerificationSession = repository.consume_verification_session(_hash(state))
    except WorkflowConflict as exc:
        raise IdMeVerificationError("Verification session is invalid or expired") from exc
    nonce, verifier = _decrypt(session.encrypted_secrets, encryption_key)
    if session.expires_at <= now or not (
        secrets.compare_digest(session.nonce_hash, _hash(nonce))
        and secrets.compare_digest(session.verifier_hash, _hash(verifier))
    ):
        raise IdMeVerificationError("Verification session integrity check failed")
    payload = (token_exchange or exchange_code)(code, verifier, settings)
    token = payload.get("id_token")
    if not isinstance(token, str):
        raise IdMeVerificationError("ID.me did not return an identity token")
    claims = validate_id_token(token, settings, nonce, jwks_fetcher=jwks_fetcher)
    access_token = payload.get("access_token")
    if not isinstance(access_token, str):
        raise IdMeVerificationError("ID.me did not return an access token")
    subject, legal_name, agency_name = _identity_from_userinfo(claims, userinfo_fetcher(access_token, settings))
    owner = repository.idme_subject_owner(subject)
    if owner is not None and owner != session.user_id:
        raise IdMeVerificationError("ID.me identity is already associated with another account")
    repository.upsert_idme_verification(IdMeVerification(
        user_id=session.user_id, provider_subject=subject, legal_name=legal_name, agency_name=agency_name,
        verified_at=now, expires_at=None,
    ))


def exchange_code(code: str, verifier: str, settings: IdMeSettings) -> dict:
    response = httpx.post(settings.token_endpoint, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": settings.redirect_uri,
        "client_id": settings.client_id, "client_secret": settings.client_secret, "code_verifier": verifier,
    }, timeout=10.0)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise IdMeVerificationError("ID.me token response is invalid")
    return payload
