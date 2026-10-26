from fastapi import FastAPI
from fastapi.testclient import TestClient
from types import SimpleNamespace
from app.api import devices
from app.devices.auth import DeviceAuthenticationError


def test_investigation_ack_authenticates_before_parsing(monkeypatch):
    monkeypatch.setattr(devices,'get_device_repository',lambda:object())
    calls=[]
    def reject(*args,**kwargs):
        calls.append(args[4])
        raise DeviceAuthenticationError()
    monkeypatch.setattr(devices,'verify_device_request',reject)
    app=FastAPI();app.include_router(devices.router)
    response=TestClient(app).post('/api/devices/drone/investigation-commands/command/acknowledgements',content=b'not-json',headers={'X-Device-Sequence':'1'})
    assert response.status_code==401 and calls==[b'not-json']


def test_invalid_signed_outcome_never_changes_investigation(monkeypatch):
    monkeypatch.setattr(devices,'get_device_repository',lambda:object())
    monkeypatch.setattr(devices,'verify_device_request',lambda *a,**kw:SimpleNamespace(sequence=1))
    calls=[]
    monkeypatch.setattr(devices,'get_investigation_repository',lambda:SimpleNamespace(acknowledge=lambda *a:calls.append(a)))
    app=FastAPI();app.include_router(devices.router)
    response=TestClient(app).post('/api/devices/drone/investigation-commands/command/acknowledgements',json={'status':'completed'},headers={'X-Device-Sequence':'1'})
    assert response.status_code==422 and calls==[]
