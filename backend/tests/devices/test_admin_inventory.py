from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import base64

from app.access.principal import Principal, StationMembership, StationRole, get_principal
from app.api import device_admin

class Repo:
    def register_real(self,*args): return {"drone_id":"d-1","credential_id":"c-1","source":"real"}
    def retire_real(self,*args): return {"drone_id":"d-1","lifecycle":"retired"}
def _principal(role):
    return Principal("user-1","o@gov","aal2","officer","verified",(StationMembership("st-1","Station","active",frozenset({role})),),({"method":"totp","timestamp":datetime.now(timezone.utc).timestamp()},))
def _client(role):
    app=FastAPI(); app.include_router(device_admin.router); app.dependency_overrides[get_principal]=lambda:_principal(role); device_admin.get_device_repository=lambda:Repo(); return TestClient(app)
def _key(): return base64.urlsafe_b64encode(Ed25519PrivateKey.generate().public_key().public_bytes_raw()).rstrip(b"=").decode()
def test_only_station_admin_can_register_real_inventory():
    assert _client(StationRole.VIEWER).post("/api/stations/st-1/inventory/real",json={"manufacturer":"Acme","serial":"SN-1","public_key":_key()}).status_code == 403
def test_admin_registers_public_key_without_private_material():
    response=_client(StationRole.STATION_ADMIN).post("/api/stations/st-1/inventory/real",json={"manufacturer":"Acme","serial":"SN-1","public_key":_key()})
    assert response.status_code == 201 and "private" not in response.text.lower() and response.json()["source"] == "real"

def test_registration_rejects_noncanonical_or_wrong_length_public_keys():
    client = _client(StationRole.STATION_ADMIN)
    for value in ("AAAA\n", "AAAA+AAA", "!!!!", "", "AAAA=", "AAAA"):
        response=client.post("/api/stations/st-1/inventory/real",json={"manufacturer":"Acme","serial":"SN-1","public_key":value})
        assert response.status_code in {422}
