from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.responses import RedirectResponse

from app.access.principal import Principal, get_principal
from app.stations.repository import get_workflow_repository
from app.verification.idme import IdMeSettings, IdMeVerificationError, complete_authorization, start_authorization
from app.rate_limits import require_rate_limit

router = APIRouter(prefix="/api/verifications/idme", tags=["verification"])


@router.get('/availability')
def availability():
    try:
        IdMeSettings.from_config()
    except IdMeVerificationError:
        return {'available':False,'message':'ID.me affiliation verification is not available yet. Contact the LakeSafe administrator.'}
    return {'available':True}


@router.post("/start")
def start_idme(request: Request, principal: Principal = Depends(get_principal)):
    require_rate_limit("verification.start", principal, request)
    try:
        settings=IdMeSettings.from_config()
        url = start_authorization(principal.user_id, get_workflow_repository(), settings)
    except (IdMeVerificationError,RuntimeError) as exc:
        raise HTTPException(503,'ID.me verification is not available yet. Contact the LakeSafe administrator.') from exc
    return {"authorization_url": url}


@router.get("/callback")
def idme_callback(state: str = Query(default=""), code: str = Query(default=""), error: str | None = None):
    try:
        settings = IdMeSettings.from_config()
    except IdMeVerificationError as exc:
        raise HTTPException(503,'ID.me verification is not available yet. Return to LakeSafe account access.') from exc
    if error or not state or not code:
        return RedirectResponse(settings.failure_url, status_code=303)
    try:
        complete_authorization(state=state, code=code, repository=get_workflow_repository(), settings=settings)
    except Exception:
        # Do not disclose provider or account state to the browser. Failed flows never promote an account.
        return RedirectResponse(settings.failure_url, status_code=303)
    return RedirectResponse(settings.success_url, status_code=303)
