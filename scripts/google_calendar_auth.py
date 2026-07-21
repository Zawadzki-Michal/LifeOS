"""One-time interactive OAuth authorization for Google Calendar.

Run inside the app container with the callback port published, e.g.:
    docker compose run --rm -p 8765:8765 app python scripts/google_calendar_auth.py

Prints a consent URL — open it in your own browser, approve, and this
script captures the resulting refresh token. Paste that into .env as
GOOGLE_CALENDAR_REFRESH_TOKEN.
"""

import http.server
import threading
import urllib.parse

import httpx

from app.config import settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/calendar"
REDIRECT_PORT = 8765
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/"

_result: dict = {}


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _result["code"] = params.get("code", [None])[0]
        _result["error"] = params.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h1>Done. You can close this tab.</h1>")

    def log_message(self, *args):
        pass


def main() -> None:
    if not settings.google_calendar_client_id or not settings.google_calendar_client_secret:
        print("Set GOOGLE_CALENDAR_CLIENT_ID / GOOGLE_CALENDAR_CLIENT_SECRET in .env first.")
        return

    params = {
        "client_id": settings.google_calendar_client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    print(f"\nOpen this URL in your browser and approve access:\n\n{url}\n")
    print(f"Waiting for the redirect on {REDIRECT_URI} (5 min timeout)...")

    server = http.server.HTTPServer(("0.0.0.0", REDIRECT_PORT), _CallbackHandler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    thread.join(timeout=300)

    if _result.get("error"):
        print(f"Authorization failed: {_result['error']}")
        return
    code = _result.get("code")
    if not code:
        print("No authorization code received (timed out).")
        return

    resp = httpx.post(
        TOKEN_URL,
        data={
            "client_id": settings.google_calendar_client_id,
            "client_secret": settings.google_calendar_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
    )
    resp.raise_for_status()
    tokens = resp.json()

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print(
            "No refresh_token in response — if you've authorized this app before, "
            "revoke access at https://myaccount.google.com/permissions and retry."
        )
        print(tokens)
        return

    print("\nSuccess. Put this in .env as GOOGLE_CALENDAR_REFRESH_TOKEN:\n")
    print(refresh_token)


if __name__ == "__main__":
    main()
