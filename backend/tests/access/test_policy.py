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



def test_judge_password_session_preserves_station_and_role_scope():
    judge = replace(principal(aal="aal1"), judge_demo_access=True)
    assert require_station_access(judge, "station-1", Permission.READ_OPERATIONS).station_id == "station-1"
    with pytest.raises(HTTPException):
        require_station_access(judge, "station-2", Permission.READ_OPERATIONS)
    with pytest.raises(HTTPException):
        require_station_access(judge, "station-1", Permission.MANAGE_MEMBERS)


@pytest.mark.parametrize("subject", [
    principal(verification="expired"), principal(verification="revoked"), principal(verification=None),
    principal(status="revoked"), principal(status="invited"), replace(principal(), account_class="civilian"),
])
def test_judge_access_does_not_bypass_verification_or_membership(subject):
    judge = replace(subject, aal="aal1", judge_demo_access=True)
    with pytest.raises(HTTPException):
        require_station_access(judge, "station-1", Permission.READ_OPERATIONS)


def test_judge_access_does_not_satisfy_recent_mfa():
    from datetime import timedelta
    from app.access.policy import require_recent_mfa
    judge = replace(principal(aal="aal1"), judge_demo_access=True)
    with pytest.raises(HTTPException, match="Recent MFA"):
        require_recent_mfa(judge, timedelta(minutes=5))


def test_public_demo_role_is_simulation_only_even_with_accidental_extra_roles():
    from app.stations.routes import _capabilities
    subject = replace(principal(aal="aal1", roles=frozenset({StationRole.DEMO_OPERATOR, StationRole.STATION_ADMIN, StationRole.SAFETY_SUPERVISOR})), judge_demo_access=True)
    with pytest.raises(HTTPException):
        require_station_access(subject, "station-1", Permission.READ_OPERATIONS)
    assert _capabilities(subject.memberships[0]) == []
    subject = replace(subject, memberships=(replace(subject.memberships[0], simulation_only=True),))
    for permission in (Permission.READ_OPERATIONS, Permission.MANAGE_ALERTS, Permission.CHANGE_SIMULATED_CIRCULATION):
        require_station_access(subject, "station-1", permission)
    for permission in (Permission.MANAGE_INVENTORY, Permission.CHANGE_FLEET_SAFETY, Permission.ADD_LAKE, Permission.MANAGE_MEMBERS):
        with pytest.raises(HTTPException):
            require_station_access(subject, "station-1", permission)
    assert _capabilities(subject.memberships[0]) == ["alert.manage", "autonomy.manage", "station.read"]
    with pytest.raises(HTTPException):
        require_station_access(subject, "real-station", Permission.MANAGE_ALERTS)
