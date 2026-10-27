from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from postgrest.exceptions import APIError

from app.access.principal import principal_from_claims
from app.access.repository import SupabaseAccessRepository


class Query:
    def __init__(self, response):
        self.response = response

    def select(self, *_args): return self
    def eq(self, *_args): return self
    def maybe_single(self): return self

    def execute(self):
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def repository_with(responses):
    repository = SupabaseAccessRepository.__new__(SupabaseAccessRepository)
    repository.client = SimpleNamespace(table=lambda table: Query(responses.get(table)))
    return repository


def test_missing_profile_optional_response_is_unprivileged_civilian():
    repository = repository_with({"profiles": None})
    principal = principal_from_claims({"sub": "user-1", "aal": "aal2"}, repository)
    assert principal.account_class == "civilian"
    assert principal.verification_status is None
    assert principal.memberships == ()


def test_missing_verification_optional_response_preserves_profile_and_roles():
    repository = repository_with({
        "profiles": SimpleNamespace(data={"account_class": "civilian"}),
        "officer_verifications": None,
        "station_memberships": SimpleNamespace(data=[{
            "station_id": "station-1", "status": "active",
            "stations": {"name": "One", "status": "active"},
            "station_membership_roles": [{"role": "viewer"}],
        }]),
    })
    principal = principal_from_claims({"sub": "user-1", "aal": "aal2"}, repository)
    assert principal.account_class == "civilian"
    assert principal.verification_status is None
    assert principal.memberships[0].roles == {"viewer"}
    assert principal.memberships[0].status == "active"


def test_public_demo_station_flag_comes_from_the_repository():
    repository = repository_with({
        "profiles": SimpleNamespace(data={"account_class": "officer"}),
        "station_memberships": SimpleNamespace(data=[{
            "station_id": "demo-station", "status": "active",
            "stations": {"name": "Public demo", "status": "active", "simulation_only": True},
            "station_membership_roles": [{"role": "demo_operator"}],
        }]),
    })
    principal = principal_from_claims({"sub": "user-1", "aal": "aal1"}, repository)
    assert principal.memberships[0].simulation_only is True
    assert str(next(iter(principal.memberships[0].roles))) == "demo_operator"


@pytest.mark.parametrize("response, expected", [
    (None, None),
    (SimpleNamespace(data={"station_id": "station-1"}), "station-1"),
])
def test_lake_station_lookup_handles_optional_response(response, expected):
    assert repository_with({"lakes": response}).lake_station_id("lake-1") == expected


def test_query_errors_are_not_treated_as_missing_profiles():
    failure = APIError({"message": "database unavailable", "code": "503", "hint": None, "details": None})
    with pytest.raises(APIError) as error:
        repository_with({"profiles": failure}).load_principal_state("user-1")
    assert error.value is failure


@pytest.mark.parametrize("expiry, expected", [
    ((datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(), True),
    ("2000-01-01T00:00:00Z", False),
    (None, False),
])
def test_judge_access_requires_future_repository_expiry(expiry, expected):
    repository = repository_with({
        "profiles": SimpleNamespace(data={"account_class": "officer"}),
        "officer_verifications": SimpleNamespace(data={"status": "verified"}),
        "station_memberships": SimpleNamespace(data=[]),
        "cac_judge_access": SimpleNamespace(data={"expires_at": expiry}) if expiry else None,
    })
    assert repository.load_principal_state("user-1")["judge_demo_access"] is expected
