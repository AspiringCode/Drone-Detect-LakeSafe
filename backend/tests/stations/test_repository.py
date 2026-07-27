from datetime import datetime, timezone

from app.stations.models import AuditEventCreate, InvitationCreate, LakeCreate, StationReviewCreate
from app.stations.repository import SupabaseWorkflowRepository


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
    repository.accept_invitation("sha256-token", "user-1", " Officer@Example.Gov ")
    assert client.last_rpc == ("accept_station_invitation", {"p_token_hash": "sha256-token", "p_user_id": "user-1", "p_email": "officer@example.gov"})


def test_station_approval_requests_atomic_admin_membership():
    client = FakeClient({"membership_id": "m", "station_id": "s", "user_id": "u", "status": "active", "roles": ["station_admin"]})
    result = SupabaseWorkflowRepository(client).review_station_request(StationReviewCreate("request", "reviewer", "approved"))
    assert result and result.roles == ("station_admin",)
    assert client.last_rpc[0] == "review_station_request"


def test_invitation_creation_never_sends_plaintext_token_and_lake_is_station_scoped():
    client = FakeClient({"lake_id": "lake", "station_id": "station", "name": "Lake"})
    repository = SupabaseWorkflowRepository(client)
    repository.create_invitation(InvitationCreate("station", "hash", " USER@EXAMPLE.GOV ", datetime.now(timezone.utc)))
    assert client.last_rpc[1]["p_intended_email"] == "user@example.gov"
    lake = repository.create_lake(LakeCreate("lake", "station", "Lake", 47.6, -122.1, {"type": "MultiPolygon", "coordinates": []}, "user"))
    assert lake.station_id == "station"


def test_audit_payload_is_service_side_only():
    client = FakeClient()
    SupabaseWorkflowRepository(client).append_audit(AuditEventCreate("user", None, "00000000-0000-0000-0000-000000000001", "station.create", "allowed", "approved"))
    assert client.last_insert[0] == "audit_events"
