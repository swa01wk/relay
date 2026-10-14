"""SmallWebRTC signaling — media plane."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from relay_gateway.core.container import realtime_service, session_service
from relay_gateway.core.http import session_token

router = APIRouter(tags=["webrtc"])

_TOKEN_ERROR = "invalid or expired session token"


class WebRtcOfferBody(BaseModel):
    sdp: str
    type: str
    pc_id: str | None = None
    restart_pc: bool | None = None


class IceCandidateBody(BaseModel):
    candidate: str
    sdp_mid: str
    sdp_mline_index: int


class WebRtcPatchBody(BaseModel):
    pc_id: str
    candidates: list[IceCandidateBody] = Field(default_factory=list)


@router.post("/sessions/{session_id}/webrtc/offer")
async def webrtc_offer(
    session_id: str,
    body: WebRtcOfferBody,
    request: Request,
    token: str | None = Query(default=None, description="Deprecated: send Authorization: Bearer <token>"),
) -> dict[str, Any]:
    session_service.require_token(session_id, session_token(request, token), detail=_TOKEN_ERROR)
    return await realtime_service.offer(session_id, body.model_dump(exclude_none=True))


@router.patch("/sessions/{session_id}/webrtc/offer")
async def webrtc_ice_patch(
    session_id: str,
    body: WebRtcPatchBody,
    request: Request,
    token: str | None = Query(default=None, description="Deprecated: send Authorization: Bearer <token>"),
) -> dict[str, str]:
    session_service.require_token(session_id, session_token(request, token), detail=_TOKEN_ERROR)
    await realtime_service.add_ice_candidates(
        session_id, pc_id=body.pc_id, candidates=[c.model_dump() for c in body.candidates]
    )
    return {"status": "ok"}
