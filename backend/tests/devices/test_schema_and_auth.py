from __future__ import annotations

import base64
from datetime import datetime, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.devices.auth import DeviceAuthenticationError, DeviceReplayError, canonical_request_bytes, verify_device_request

class Repo:
    def __init__(self, key: bytes): self.key, self.sequence = key, -1
    def active_credential(self, drone_id): return {"drone_id":drone_id,"station_id":"station-1","credential_id":"credential-1","public_key":base64.urlsafe_b64encode(self.key).rstrip(b"=").decode()}
    def claim_sequence(self, drone_id, sequence):
        if sequence <= self.sequence: return False
        self.sequence = sequence; return True

def _signed(private, drone_id, timestamp, sequence, body):
    return base64.urlsafe_b64encode(private.sign(canonical_request_bytes(drone_id,timestamp,sequence,body))).rstrip(b"=").decode()

def test_valid_request_claims_monotonic_sequence():
    private=Ed25519PrivateKey.generate(); repo=Repo(private.public_key().public_bytes_raw()); body=b'{"battery":0.8}'; timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result=verify_device_request("d-1",timestamp,8,_signed(private,"d-1",timestamp,8,body),body,repo)
    assert result.drone_id == "d-1" and repo.sequence == 8

def test_replay_and_bad_signatures_are_rejected():
    private=Ed25519PrivateKey.generate(); repo=Repo(private.public_key().public_bytes_raw()); timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"); sig=_signed(private,"d-1",timestamp,8,b"{}")
    verify_device_request("d-1",timestamp,8,sig,b"{}",repo)
    with pytest.raises(DeviceReplayError): verify_device_request("d-1",timestamp,8,sig,b"{}",repo)
    with pytest.raises(DeviceAuthenticationError): verify_device_request("d-1",timestamp,9,sig,b"{}",repo)

def test_non_utc_or_stale_clock_is_rejected():
    private=Ed25519PrivateKey.generate(); repo=Repo(private.public_key().public_bytes_raw())
    with pytest.raises(DeviceAuthenticationError): verify_device_request("d-1","2020-01-01T00:00:00Z",1,"x",b"{}",repo)

@pytest.mark.parametrize("value", ["AAAA\n", "AAAA+AAA", "!!!!", "", "AAAA="])
def test_noncanonical_base64url_signatures_are_rejected(value):
    private=Ed25519PrivateKey.generate(); repo=Repo(private.public_key().public_bytes_raw()); timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with pytest.raises(DeviceAuthenticationError): verify_device_request("d-1",timestamp,1,value,b"{}",repo)

def test_wrong_length_signature_is_rejected():
    private=Ed25519PrivateKey.generate(); repo=Repo(private.public_key().public_bytes_raw()); timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with pytest.raises(DeviceAuthenticationError): verify_device_request("d-1",timestamp,1,"AAAA",b"{}",repo)
