from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.stations.models import VerificationSession
from app.stations.repository import WorkflowConflict
from app.verification.idme import IdMeSettings, IdMeVerificationError, VerificationSecretStore, complete_authorization, start_authorization, validate_id_token


SETTINGS = IdMeSettings("client", "secret", "https://app/callback", "https://issuer", "audience", "https://idme/authorize", "https://idme/token", "https://idme/keys", "/profile?ok", "/profile?fail")
NOW = datetime(2026, 7, 27, tzinfo=timezone.utc)


class Repository:
    def __init__(self): self.created = None; self.consumed = []; self.owner = None; self.writes = []
    def create_verification_session(self, value): self.created = value
    def consume_verification_session(self, state_hash):
        self.consumed.append(state_hash)
        if self.created is None: raise WorkflowConflict("missing")
        return VerificationSession("session", self.created.state_hash, self.created.nonce_hash, self.created.verifier_hash, self.created.user_id, "consumed", self.created.expires_at)
    def idme_subject_owner(self, provider_subject): return self.owner
    def upsert_idme_verification(self, value): self.writes.append(value)


def test_start_uses_pkce_and_persists_hashes_only():
    repo, store = Repository(), VerificationSecretStore()
    query = parse_qs(urlparse(start_authorization("user", repo, SETTINGS, store, now=NOW)).query)
    assert query["code_challenge_method"] == ["S256"]
    assert "code_verifier" not in query and "state_hash" not in query
    assert repo.created and len(repo.created.state_hash) == 64 and len(repo.created.nonce_hash) == 64
    assert repo.created.verifier_hash not in query.values()


def test_unknown_expired_and_replayed_state_never_writes_verification(monkeypatch):
    repo, store = Repository(), VerificationSecretStore()
    with pytest.raises(IdMeVerificationError): complete_authorization(state="unknown", code="code", repository=repo, settings=SETTINGS, store=store, now=NOW)
    url = start_authorization("user", repo, SETTINGS, store, now=NOW)
    state = parse_qs(urlparse(url).query)["state"][0]
    with pytest.raises(IdMeVerificationError): complete_authorization(state=state, code="code", repository=repo, settings=SETTINGS, store=store, now=NOW + timedelta(minutes=11))
    assert repo.writes == []


def test_success_consumes_and_writes_only_verified_identity(monkeypatch):
    repo, store = Repository(), VerificationSecretStore()
    state = parse_qs(urlparse(start_authorization("user", repo, SETTINGS, store, now=NOW)).query)["state"][0]
    monkeypatch.setattr("app.verification.idme.validate_id_token", lambda *args, **kwargs: {"sub": "idme-sub", "name": "Officer Name", "agency": "Lake Police", "affiliation": "us_law_enforcement"})
    complete_authorization(state=state, code="code", repository=repo, settings=SETTINGS, store=store, now=NOW, token_exchange=lambda *_: {"id_token": "token"})
    assert repo.consumed == [repo.created.state_hash]
    assert repo.writes[0].provider_subject == "idme-sub"
    with pytest.raises(IdMeVerificationError): complete_authorization(state=state, code="code", repository=repo, settings=SETTINGS, store=store, now=NOW, token_exchange=lambda *_: {"id_token": "token"})


@pytest.mark.parametrize("claims", [
    {"sub": "sub", "name": "Name", "agency": "Agency"},
    {"sub": "sub", "name": "Name", "agency": "Agency", "affiliation": "civilian"},
])
def test_missing_or_wrong_affiliation_cannot_promote(monkeypatch, claims):
    repo, store = Repository(), VerificationSecretStore()
    state = parse_qs(urlparse(start_authorization("user", repo, SETTINGS, store, now=NOW)).query)["state"][0]
    monkeypatch.setattr("app.verification.idme.validate_id_token", lambda *args, **kwargs: claims)
    with pytest.raises(IdMeVerificationError): complete_authorization(state=state, code="code", repository=repo, settings=SETTINGS, store=store, now=NOW, token_exchange=lambda *_: {"id_token": "token"})
    assert repo.writes == []


def test_subject_collision_fails_closed(monkeypatch):
    repo, store = Repository(), VerificationSecretStore(); repo.owner = "different-user"
    state = parse_qs(urlparse(start_authorization("user", repo, SETTINGS, store, now=NOW)).query)["state"][0]
    monkeypatch.setattr("app.verification.idme.validate_id_token", lambda *args, **kwargs: {"sub": "idme-sub", "name": "Name", "agency": "Agency", "affiliation": "us_law_enforcement"})
    with pytest.raises(IdMeVerificationError): complete_authorization(state=state, code="code", repository=repo, settings=SETTINGS, store=store, now=NOW, token_exchange=lambda *_: {"id_token": "token"})
    assert repo.writes == []


def _signed_token(**overrides):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = {"sub": "sub", "iss": SETTINGS.issuer, "aud": SETTINGS.audience, "exp": int((NOW + timedelta(minutes=1)).timestamp()), "nonce": "nonce"}
    claims.update(overrides)
    token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "key"})
    public = key.public_key().public_numbers()
    from jwt.utils import base64url_encode
    jwk = {"kty": "RSA", "kid": "key", "n": base64url_encode(public.n.to_bytes((public.n.bit_length() + 7) // 8, "big")).decode(), "e": base64url_encode(public.e.to_bytes((public.e.bit_length() + 7) // 8, "big")).decode()}
    return token, [jwk]


@pytest.mark.parametrize("overrides", [{"iss": "wrong"}, {"aud": "wrong"}, {"nonce": "wrong"}, {"exp": 1}])
def test_id_token_rejects_issuer_audience_nonce_and_expiry(overrides):
    token, keys = _signed_token(**overrides)
    with pytest.raises(IdMeVerificationError): validate_id_token(token, SETTINGS, "nonce", jwks_fetcher=lambda _: keys)


def test_id_token_rejects_non_rs256_before_claims_are_trusted():
    token = jwt.encode({"sub": "sub"}, "secret", algorithm="HS256", headers={"kid": "key"})
    with pytest.raises(IdMeVerificationError): validate_id_token(token, SETTINGS, "nonce", jwks_fetcher=lambda _: [])
