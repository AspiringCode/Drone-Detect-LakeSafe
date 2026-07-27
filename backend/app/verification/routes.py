from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse

from app.access.principal import Principal, get_principal
from app.stations.repository import get_workflow_repository
from app.verification.idme import IdMeSettings, IdMeVerificationError, VerificationSecretStore, complete_authorization, start_authorization

router = APIRouter(prefix="/api/verifications/idme", tags=["verification"])
secret_store = VerificationSecretStore()


@router.post("/start")
def start_idme(principal: Principal = Depends(get_principal)):
    url = start_authorization(principal.user_id, get_workflow_repository(), IdMeSettings.from_config(), secret_store)
    return {"authorization_url": url}


@router.get("/callback")
def idme_callback(state: str = Query(default=""), code: str = Query(default=""), error: str | None = None):
    settings = IdMeSettings.from_config()
    if error or not state or not code:
        return RedirectResponse(settings.failure_url, status_code=303)
    try:
        complete_authorization(state=state, code=code, repository=get_workflow_repository(), settings=settings, store=secret_store)
    except Exception:
        # Do not disclose provider or account state to the browser. Failed flows never promote an account.
        return RedirectResponse(settings.failure_url, status_code=303)
    return RedirectResponse(settings.success_url, status_code=303)
