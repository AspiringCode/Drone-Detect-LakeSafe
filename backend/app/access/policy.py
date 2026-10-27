from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import StrEnum

from fastapi import HTTPException

from app.access.principal import Principal, StationMembership, StationRole


class Permission(StrEnum):
    READ_OPERATIONS = "read_operations"
    MANAGE_ALERTS = "manage_alerts"
    ADD_LAKE = "add_lake"
    MANAGE_INVENTORY = "manage_inventory"
    CHANGE_FLEET_SAFETY = "change_fleet_safety"
    CHANGE_SIMULATED_CIRCULATION = "change_simulated_circulation"
    MANAGE_MEMBERS = "manage_members"


_ROLE_PERMISSIONS = {
    StationRole.VIEWER: frozenset({Permission.READ_OPERATIONS}),
    StationRole.DISPATCHER: frozenset({Permission.READ_OPERATIONS, Permission.MANAGE_ALERTS}),
    StationRole.SAFETY_SUPERVISOR: frozenset({Permission.READ_OPERATIONS, Permission.CHANGE_FLEET_SAFETY, Permission.CHANGE_SIMULATED_CIRCULATION}),
    StationRole.STATION_ADMIN: frozenset({Permission.READ_OPERATIONS, Permission.MANAGE_ALERTS, Permission.ADD_LAKE, Permission.MANAGE_INVENTORY, Permission.CHANGE_SIMULATED_CIRCULATION, Permission.MANAGE_MEMBERS}),
    StationRole.DEMO_OPERATOR: frozenset({Permission.READ_OPERATIONS, Permission.MANAGE_ALERTS, Permission.CHANGE_SIMULATED_CIRCULATION, Permission.MANAGE_INVENTORY, Permission.CHANGE_FLEET_SAFETY}),
}


def _current_verification(principal: Principal) -> bool:
    return principal.account_class == "officer" and principal.verification_status == "verified"


def _membership(principal: Principal, station_id: str) -> StationMembership | None:
    for membership in principal.memberships:
        if membership.station_id == station_id:
            return membership
    return None


def require_station_access(principal: Principal, station_id: str, permission: Permission) -> StationMembership:
    membership = _membership(principal, station_id)
    if (principal.aal != "aal2" and not principal.judge_demo_access) or not _current_verification(principal) or membership is None or membership.status != "active":
        raise HTTPException(status_code=403, detail="Verified station access is required")
    granted = set().union(*(_ROLE_PERMISSIONS[role] for role in membership.roles)) if membership.roles else set()
    if StationRole.DEMO_OPERATOR in membership.roles:
        if not membership.simulation_only:
            raise HTTPException(status_code=403, detail="Demo access requires an isolated simulation station")
        granted &= _ROLE_PERMISSIONS[StationRole.DEMO_OPERATOR]
        if not membership.demo_device_access:
            granted -= {Permission.MANAGE_INVENTORY, Permission.CHANGE_FLEET_SAFETY}
    if permission not in granted:
        raise HTTPException(status_code=403, detail="Station role does not permit this action")
    return membership


def require_recent_mfa(principal: Principal, maximum_age: timedelta, *, station_id: str | None = None) -> None:
    membership = _membership(principal, station_id) if station_id else None
    if principal.judge_demo_access and membership and membership.demo_device_access and membership.simulation_only and StationRole.DEMO_OPERATOR in membership.roles:
        require_station_access(principal, station_id, Permission.CHANGE_FLEET_SAFETY)
        return
    now = datetime.now(timezone.utc)
    for method in principal.amr:
        if method.get("method") not in {"totp", "mfa"}:
            continue
        timestamp = method.get("timestamp")
        if isinstance(timestamp, (int, float)) and now - datetime.fromtimestamp(timestamp, timezone.utc) <= maximum_age:
            return
    raise HTTPException(status_code=403, detail="Recent MFA is required")
