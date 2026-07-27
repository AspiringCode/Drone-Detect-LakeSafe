from app.access.principal import principal_from_claims


class Repository:
    def __init__(self, state): self.state = state
    def load_principal_state(self, user_id): return self.state


def test_principal_uses_server_side_profile_and_memberships_not_jwt_roles():
    principal = principal_from_claims(
        {"sub": "user-1", "aal": "aal2", "role": "station_admin"},
        Repository({"account_class": "officer", "verification_status": "verified", "memberships": [{"station_id": "station-1", "station_name": "One", "membership_status": "active", "roles": ["viewer"]}]}),
    )
    assert principal.memberships[0].roles == {"viewer"}
    assert principal.account_class == "officer"


def test_missing_server_profile_is_civilian_without_memberships():
    principal = principal_from_claims({"sub": "user-1", "aal": "aal2"}, Repository(None))
    assert principal.account_class == "civilian"
    assert not principal.memberships
