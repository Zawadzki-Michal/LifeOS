import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app import auth

logger = logging.getLogger("lifeos.auth")

router = APIRouter(prefix="/api/auth")


@router.get("/login")
async def login(request: Request):
    state = auth.new_state_token()
    resp = RedirectResponse(auth.build_auth_url(state))
    resp.set_cookie(
        auth.STATE_COOKIE,
        state,
        max_age=auth.STATE_MAX_AGE,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )
    return resp


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error:
        raise HTTPException(status_code=400, detail=f"Google returned an error: {error}")
    if not code or not state or state != request.cookies.get(auth.STATE_COOKIE):
        raise HTTPException(status_code=400, detail="Invalid or missing OAuth state")

    try:
        email = await auth.exchange_code_for_email(code)
    except PermissionError as exc:
        logger.warning("Rejected web login: %s", exc)
        raise HTTPException(status_code=403, detail="This Google account isn't allowed")
    except Exception:
        logger.exception("OAuth callback failed")
        raise HTTPException(status_code=400, detail="Login failed")

    resp = RedirectResponse("/")
    resp.delete_cookie(auth.STATE_COOKIE)
    resp.set_cookie(
        auth.SESSION_COOKIE,
        auth.create_session_token(email),
        max_age=auth.SESSION_MAX_AGE,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )
    return resp


@router.post("/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.SESSION_COOKIE)
    return resp


@router.get("/me")
async def me(email: str = Depends(auth.require_auth)):
    return {"email": email}
