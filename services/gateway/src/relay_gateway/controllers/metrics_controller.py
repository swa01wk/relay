"""Prometheus scrape endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Header, Response

from relay_gateway.core.container import metrics_service

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics(authorization: str | None = Header(default=None)) -> Response:
    body, content_type = metrics_service.render(authorization)
    return Response(content=body, media_type=content_type)
