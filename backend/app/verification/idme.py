from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib.parse import urlencode

import httpx
import jwt

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
    success_url: str
    failure_url: str

    @classmethod
    def from_config(cls) -> "IdMeSettings":
        required = {
            "IDME_CLIENT_ID": config.IDME_CLIENT_ID,
            "IDME_CLIENT_SECRET": config.IDME_CLIENT_SECRET,
            "IDME_REDIRECT_URI": config.IDME_REDIRECT_URI,
            "IDME_AUDIENCE": config.IDME_AUDIENCE,
        }
        if any(not value for value in required.values()):
            raise IdMeVerificationError("ID.me verification is not configured")
        return cls(
            client_id=str(config.IDME_CLIENT_ID), client_secret=str(config.IDME_CLIENT_SECRET),
            redirect_uri=str(config.IDME_REDIRECT_URI), issuer=config.IDME_ISSUER,
            audience=str(config.IDME_AUDIENCE), authorization_endpoint=config.IDME_AUTHORIZATION_ENDPOINT,
            token_endpoint=config.IDME_TOKEN_ENDPOINT, jwks_uri=config.IDME_JWKS_URI,
            success_url=config.IDME_PROFILE_SUCCESS_URL, failure_url=config.IDME_PROFILE_FAILURE_URL,
        )


@dataclass(frozen=True)
class SessionSecrets:
    state: str
    nonce: str
    verifier: str
    expires_at: datetime


class VerificationSecretStore:
    """Short-lived process-local raw OIDC material; the database gets hashes only."""

    def __init__(self) -> None:
        self._values: dict[str, SessionSecrets] = {}

    def create(self, now: datetime) -> SessionSecrets:
        value = SessionSecrets(
            state=secrets.token_urlsafe(32), nonce=secrets.token_urlsafe(32),
            verifier=secrets.token_urlsafe(64), expires_at=now + timedelta(minutes=10),
        )
        self._values[_hash(value.state)] = value
        return value

    def take(self, state: str, now: datetime) -> SessionSecrets:
        value = self._values.pop(_hash(state), None)
        if value is None or value.expires_at <= now:
            raise IdMeVerificationError("Verification session is invalid or expired")
        return value


def start_authorization(user_id: str, repository: WorkflowRepository, settings: IdMeSettings, store: VerificationSecretStore, *, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    secret = store.create(now)
    repository.create_verification_session(VerificationSessionCreate(
        state_hash=_hash(secret.state), nonce_hash=_hash(secret.nonce), verifier_hash=_hash(secret.verifier),
        user_id=user_id, expires_at=secret.expires_at,
    ))
    return f"{settings.authorization_endpoint}?{urlencode({
        'response_type': 'code', 'client_id': settings.client_id, 'redirect_uri': settings.redirect_uri,
        'scope': 'openid profile', 'state': secret.state, 'nonce': secret.nonce,
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
        claims = jwt.decode(token, jwt.PyJWK.from_dict(key_data).key, algorithms=["RS256"], issuer=settings.issuer, audience=settings.audience)
    except (jwt.PyJWTError, StopIteration, TypeError, ValueError, httpx.HTTPError) as exc:
        raise IdMeVerificationError("ID.me identity token is invalid") from exc
    if not secrets.compare_digest(str(claims.get("nonce", "")), expected_nonce):
        raise IdMeVerificationError("ID.me token nonce is invalid")
    return claims


def _identity_from_claims(claims: dict[str, object]) -> tuple[str, str, str]:
    subject, name, agency = claims.get("sub"), claims.get("name"), claims.get("agency")
    affiliations = claims.get("affiliations", claims.get("affiliation"))
    valid_affiliation = affiliations == "us_law_enforcement" or (
        isinstance(affiliations, list) and "us_law_enforcement" in affiliations
    )
    if not all(isinstance(value, str) and value.strip() for value in (subject, name, agency)) or not valid_affiliation:
        raise IdMeVerificationError("ID.me did not verify a US law-enforcement affiliation")
    return subject, name, agency


def complete_authorization(*, state: str, code: str, repository: WorkflowRepository, settings: IdMeSettings, store: VerificationSecretStore, now: datetime | None = None, token_exchange: Callable[[str, str, IdMeSettings], dict] | None = None, jwks_fetcher: Callable[[str], list[dict]] = _jwks) -> None:
    now = now or datetime.now(timezone.utc)
    secrets_value = store.take(state, now)
    try:
        session: VerificationSession = repository.consume_verification_session(_hash(state))
    except WorkflowConflict as exc:
        raise IdMeVerificationError("Verification session is invalid or expired") from exc
    if session.expires_at <= now or not (
        secrets.compare_digest(session.nonce_hash, _hash(secrets_value.nonce))
        and secrets.compare_digest(session.verifier_hash, _hash(secrets_value.verifier))
    ):
        raise IdMeVerificationError("Verification session integrity check failed")
    payload = (token_exchange or exchange_code)(code, secrets_value.verifier, settings)
    token = payload.get("id_token")
    if not isinstance(token, str):
        raise IdMeVerificationError("ID.me did not return an identity token")
    claims = validate_id_token(token, settings, secrets_value.nonce, jwks_fetcher=jwks_fetcher)
    subject, legal_name, agency_name = _identity_from_claims(claims)
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
