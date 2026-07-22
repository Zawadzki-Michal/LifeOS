"""Google OAuth login for the web app.

Authorization-code flow implemented directly with httpx (same pattern as
scripts/google_calendar_auth.py — no OAuth library dependency), the id_token
verified through Google's tokeninfo endpoint, gated by an allow-list of
emails, and backed by a signed session cookie. This only replaces the login
*mechanism* — the deployment stays single-tenant; every allowed email sees
the same data. See 03-WEBAPP-PLAN.md.
"""

import logging
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings

logger = logging.getLogger("lifeos.auth")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
SCOPE = "openid email"

SESSION_COOKIE = "lifeos_session"
STATE_COOKIE = "lifeos_oauth_state"
SESSION_MAX_AGE = 30 * 24 * 60 * 60  # 30 days
STATE_MAX_AGE = 10 * 60  # 10 minutes to complete the redirect round trip

if not settings.webapp_secret_key:
    logger.warning(
        "WEBAPP_SECRET_KEY not set — web app session cookies are unsigned/insecure "
        "until it's configured in .env"
    )

_serializer = URLSafeTimedSerializer(settings.webapp_secret_key, salt="lifeos-webapp-session")


def allowed_emails() -> set[str]:
    return {e.strip().lower() for e in settings.webapp_allowed_emails.split(",") if e.strip()}


def new_state_token() -> str:
    return secrets.token_urlsafe(24)


def build_auth_url(state: str) -> str:
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "state": state,
        "prompt": "select_account",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_email(code: str) -> str:
    """Exchange an authorization code for tokens, verify the id_token via
    Google's tokeninfo endpoint, and return the verified + allow-listed
    email. Raises ValueError for a bad/unverified token, PermissionError if
    the email isn't on the allow-list.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        token_resp = await client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_resp.raise_for_status()
        id_token = token_resp.json()["id_token"]

        info_resp = await client.get(TOKENINFO_URL, params={"id_token": id_token})
        info_resp.raise_for_status()
        claims = info_resp.json()

    if claims.get("aud") != settings.google_oauth_client_id:
        raise ValueError("id_token audience mismatch")
    if claims.get("email_verified") != "true":
        raise ValueError("Google email not verified")

    email = claims["email"].lower()
    if email not in allowed_emails():
        raise PermissionError(f"{email} is not on the allow-list")
    return email


def create_session_token(email: str) -> str:
    return _serializer.dumps({"email": email})


def read_session_token(token: str) -> str | None:
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE)
        return data["email"]
    except (BadSignature, SignatureExpired):
        return None


def require_auth(request: Request) -> str:
    token = request.cookies.get(SESSION_COOKIE)
    email = read_session_token(token) if token else None
    if email is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return email
