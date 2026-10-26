import pytest
from fastapi import HTTPException
from app import config
from app.verification import routes
from app.verification.idme import IdMeSettings,IdMeVerificationError


def test_default_endpoints_match_published_discovery():
    assert config.IDME_AUTHORIZATION_ENDPOINT=='https://api.id.me/oauth/authorize'
    assert config.IDME_TOKEN_ENDPOINT=='https://api.id.me/oauth/token'
    assert config.IDME_JWKS_URI=='https://api.id.me/oidc/.well-known/jwks'
    assert config.IDME_USERINFO_ENDPOINT=='https://api.id.me/api/public/v3/userinfo'


def test_unconfigured_callback_is_service_unavailable_not_unhandled_failure(monkeypatch):
    monkeypatch.setattr(routes.IdMeSettings,'from_config',classmethod(lambda cls: (_ for _ in ()).throw(IdMeVerificationError('missing'))))
    with pytest.raises(HTTPException) as error: routes.idme_callback(state='',code='',error='denied')
    assert error.value.status_code==503
