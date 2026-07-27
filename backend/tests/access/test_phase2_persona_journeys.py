import pytest
from fastapi import HTTPException

from app.access.policy import Permission, require_station_access
from app.access.principal import Principal, StationMembership, StationRole


def principal(*, account_class="officer", verification_status="verified", membership=None):
    return Principal(
        "officer-1", "officer@example.gov", "aal2", account_class,
        verification_status, () if membership is None else (membership,),
    )


@pytest.mark.parametrize(
    "actor",
    [
        principal(account_class="civilian", verification_status=None),
        principal(),
        principal(membership=StationMembership("station-1", "One", "invited", frozenset({StationRole.VIEWER}))),
        principal(verification_status="expired", membership=StationMembership("station-1", "One", "active", frozenset({StationRole.STATION_ADMIN}))),
        principal(verification_status="revoked", membership=StationMembership("station-1", "One", "active", frozenset({StationRole.STATION_ADMIN}))),
    ],
    ids=["civilian", "verified-unassigned", "invited-member", "expired-officer", "revoked-officer"],
)
def test_phase2_non_operational_personas_cannot_manage_station_lakes(actor):
    with pytest.raises(HTTPException, match="Verified station access"):
        require_station_access(actor, "station-1", Permission.ADD_LAKE)


def test_phase2_station_admin_can_add_only_its_own_station_lake():
    admin = principal(membership=StationMembership("station-1", "One", "active", frozenset({StationRole.STATION_ADMIN})))
    assert require_station_access(admin, "station-1", Permission.ADD_LAKE).station_id == "station-1"
    with pytest.raises(HTTPException, match="Verified station access"):
        require_station_access(admin, "station-2", Permission.ADD_LAKE)
