"""Prometheus scrape endpoint.

The gateway port is also the browser-facing port, so metrics (usage, cost) are off by default:
set ``RELAY_METRICS_TOKEN`` (scrape with ``Authorization: Bearer <token>``) or, on a private
network, ``RELAY_METRICS_ENABLED=1`` for unauthenticated access.
"""

from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Header, HTTPException, Response

from relay_gateway.deps import metrics_bridge

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics(authorization: str | None = Header(default=None)) -> Response:
    token = os.environ.get("RELAY_METRICS_TOKEN", "").strip()
    if token:
        supplied = (authorization or "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(supplied.encode(), token.encode()):
            raise HTTPException(status_code=401, detail="invalid metrics token")
    elif os.environ.get("RELAY_METRICS_ENABLED", "").lower() not in ("1", "true", "yes"):
        raise HTTPException(status_code=404, detail="metrics are disabled")
    body, content_type = metrics_bridge.render()
    return Response(content=body, media_type=content_type)
