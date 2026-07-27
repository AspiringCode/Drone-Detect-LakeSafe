from datetime import datetime, timezone

import pytest

from app.stations.models import AuditEventCreate, InvitationCreate, JoinRequestCreate, LakeCreate, StationReviewCreate
from app.stations.repository import SupabaseWorkflowRepository, WorkflowConflict


class Result:
    def __init__(self, data): self.data = data


class Call:
    def __init__(self, client, name, args=None): self.client, self.name, self.args = client, name, args
    def insert(self, value): self.client.last_insert = (self.name, value); return self
    def execute(self): return Result(self.client.response)


class FakeClient:
    def __init__(self, response=None): self.response = response or {"membership_id": "m", "station_id": "s", "user_id": "u", "status": "active", "roles": ["viewer"]}; self.last_rpc = None; self.last_insert = None
    def rpc(self, name, args): self.last_rpc = (name, args); return Call(self, name, args)
    def table(self, name): return Call(self, name)


def test_accept_invitation_queries_only_hash_and_normalized_email():
    client = FakeClient()
    repository = SupabaseWorkflowRepository(client)
    repository.accept_invitation("a" * 64, "user-1", " Officer@Example.Gov ")
    assert client.last_rpc == ("accept_station_invitation", {"p_token_hash": "a" * 64, "p_user_id": "user-1", "p_email": "officer@example.gov"})


def test_station_approval_requests_atomic_admin_membership():
    client = FakeClient({"membership_id": "m", "station_id": "s", "user_id": "u", "status": "active", "roles": ["station_admin"]})
    result = SupabaseWorkflowRepository(client).review_station_request(StationReviewCreate("request", "reviewer", "approved"))
    assert result and result.roles == ("station_admin",)
    assert client.last_rpc[0] == "review_station_request"


def test_invitation_creation_never_sends_plaintext_token_and_lake_is_station_scoped():
    client = FakeClient({"lake_id": "lake", "station_id": "station", "name": "Lake"})
    repository = SupabaseWorkflowRepository(client)
    repository.create_invitation(InvitationCreate("station", "admin", "b" * 64, " USER@EXAMPLE.GOV ", datetime.now(timezone.utc)))
    assert client.last_rpc[1]["p_intended_email"] == "user@example.gov"
    assert client.last_rpc[1]["p_actor_user_id"] == "admin"
    lake = repository.create_lake(LakeCreate("lake", "station", "Lake", 47.6, -122.1, {"type": "MultiPolygon", "coordinates": []}, "user"))
    assert lake.station_id == "station"


def test_audit_payload_is_service_side_only():
    client = FakeClient()
    SupabaseWorkflowRepository(client).append_audit(AuditEventCreate("user", None, "00000000-0000-0000-0000-000000000001", "station.create", "allowed", "approved"))
    assert client.last_insert[0] == "audit_events"


def test_join_request_uses_its_own_result_model_and_rejects_malformed_result():
    client = FakeClient({"station_join_request_id": "join", "station_id": "station", "user_id": "user", "status": "pending"})
    result = SupabaseWorkflowRepository(client).create_join_request(JoinRequestCreate("station", "user"))
    assert result.station_join_request_id == "join"
    client.response = {"station_id": "station"}
    with pytest.raises(KeyError):
        SupabaseWorkflowRepository(client).create_join_request(JoinRequestCreate("station", "user"))


@pytest.mark.parametrize("response", [None, [], {}])
def test_one_use_or_expired_invitation_maps_to_generic_conflict(response):
    client = FakeClient()
    client.response = response
    with pytest.raises(WorkflowConflict, match="invalid, expired, or already used"):
        SupabaseWorkflowRepository(client).accept_invitation("a" * 64, "user", "user@example.gov")


def test_plaintext_invitation_token_is_rejected_before_repository_rpc():
    client = FakeClient()
    with pytest.raises(ValueError, match="SHA-256"):
        SupabaseWorkflowRepository(client).accept_invitation("plain-token", "user", "user@example.gov")
    assert client.last_rpc is None
