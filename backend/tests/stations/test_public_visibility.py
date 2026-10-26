from types import SimpleNamespace
from datetime import datetime,timezone
import pytest
from fastapi import HTTPException
from app.access.principal import Principal,StationMembership,StationRole
from app.stations import routes


def test_station_visibility_cannot_be_changed_by_viewer(monkeypatch):
    actor=Principal('actor',None,'aal2','officer','verified',(
        StationMembership('station','Station','active',frozenset({StationRole.VIEWER})),))
    with pytest.raises(HTTPException) as error:
        routes.set_public_visibility('station',routes.PublicVisibilityInput(visible=False),actor)
    assert error.value.status_code==403


def test_station_visibility_uses_verified_station_and_recent_mfa(monkeypatch):
    actor=Principal('actor',None,'aal2','officer','verified',(
        StationMembership('station','Station','active',frozenset({StationRole.STATION_ADMIN})),))
    calls=[]
    monkeypatch.setattr(routes,'require_recent_mfa',lambda *args:calls.append('mfa'))
    monkeypatch.setattr(routes,'get_workflow_repository',lambda:SimpleNamespace(
        set_public_visibility=lambda s,a,v: {'visible':v,'published_lakes':2}))
    assert routes.set_public_visibility('station',routes.PublicVisibilityInput(visible=False),actor)['visible'] is False
    assert calls==['mfa']
