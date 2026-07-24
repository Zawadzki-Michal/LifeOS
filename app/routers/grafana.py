"""Reverse-proxies Grafana (running in the monitoring namespace) through this
app's own domain, gated by the same require_auth session cookie as every
other route — this is the only auth boundary Grafana needs, since its
Service is otherwise unreachable from outside the cluster. Grafana itself
runs with auth.anonymous enabled (org_role Viewer, see
deploy/kube-prometheus-stack-values.yaml) so there's no second login/session
to forward: no Set-Cookie relayed, no credentials stored here.

Grafana is told (via grafana.ini's server.root_url/serve_from_sub_path) that
it's served from /api/grafana/, so every asset/link/internal-API URL it
emits already resolves back through this same catch-all route.

Known limitation: Grafana Live (websocket-based streaming panels) doesn't
work through this proxy — no WebSocket route exists here, only plain HTTP.
Normal dashboard viewing (polling refresh) doesn't need it.
"""

import httpx
from fastapi import APIRouter, Depends, Request
from starlette.responses import StreamingResponse

from app.auth import require_auth
from app.config import settings

router = APIRouter(prefix="/api/grafana", dependencies=[Depends(require_auth)])

_client = httpx.AsyncClient(timeout=30.0, follow_redirects=False)

_DROP_REQUEST_HEADERS = {"host", "content-length", "cookie"}
_DROP_RESPONSE_HEADERS = {
    "content-encoding",
    "content-length",
    "transfer-encoding",
    "connection",
    "x-frame-options",
    "set-cookie",
}


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def grafana_proxy(path: str, request: Request):
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _DROP_REQUEST_HEADERS}
    target = f"{settings.grafana_base_url.rstrip('/')}/{path}"

    req = _client.build_request(
        request.method, target, params=request.query_params, content=body, headers=headers
    )
    upstream = await _client.send(req, stream=True)

    async def relay():
        async for chunk in upstream.aiter_bytes():
            yield chunk
        await upstream.aclose()

    response_headers = {
        k: v for k, v in upstream.headers.items() if k.lower() not in _DROP_RESPONSE_HEADERS
    }
    return StreamingResponse(
        relay(),
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
        headers=response_headers,
    )
