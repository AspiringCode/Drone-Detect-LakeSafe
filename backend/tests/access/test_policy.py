from dataclasses import replace

import pytest
from fastapi import HTTPException

from app.access.policy import Permission, require_station_access
from app.access.principal import Principal, StationMembership, StationRole


def principal(*, aal="aal2", verification="verified", status="active", roles=frozenset({StationRole.VIEWER}), station="station-1"):
    return Principal("u", None, aal, "officer", verification, (StationMembership(station, "One", status, roles),))


@pytest.mark.parametrize("subject", [principal(aal="aal1"), principal(verification="expired"), principal(status="revoked"), principal(station="station-2")])
def test_aal_verification_and_membership_fail_closed(subject):
    with pytest.raises(HTTPException) as error:
        require_station_access(subject, "station-1", Permission.READ_OPERATIONS)
    assert error.value.status_code == 403


def test_roles_are_additive_and_real_safety_needs_supervisor():
    subject = principal(roles=frozenset({StationRole.STATION_ADMIN, StationRole.DISPATCHER}))
    require_station_access(subject, "station-1", Permission.MANAGE_INVENTORY)
    require_station_access(subject, "station-1", Permission.MANAGE_ALERTS)
    with pytest.raises(HTTPException):
        require_station_access(subject, "station-1", Permission.CHANGE_FLEET_SAFETY)
    require_station_access(replace(subject, memberships=(replace(subject.memberships[0], roles=frozenset({StationRole.STATION_ADMIN, StationRole.SAFETY_SUPERVISOR})),)), "station-1", Permission.CHANGE_FLEET_SAFETY)
