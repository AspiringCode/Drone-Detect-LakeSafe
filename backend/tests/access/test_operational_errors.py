import httpx
import pytest
from fastapi import HTTPException
from postgrest.exceptions import APIError

from app import main
from app.access.policy import Permission
from app.access.principal import Principal


@pytest.mark.parametrize("failure", [httpx.ReadError("socket unavailable"), APIError({"code": "503", "message": "database unavailable", "details": None, "hint": None})])
def test_lake_ownership_infrastructure_failure_is_503(monkeypatch, failure):
    class Repository:
        def lake_station_id(self, _lake_id):
            raise failure

    monkeypatch.setattr(main, "get_access_repository", lambda: Repository())
    with pytest.raises(HTTPException) as error:
        main.require_lake_permission("lake-sammamish", Principal("u", None, "aal2", "officer", "verified", ()), Permission.READ_OPERATIONS)
    assert error.value.status_code == 503
    assert error.value.detail == "Authorization service is unavailable"
