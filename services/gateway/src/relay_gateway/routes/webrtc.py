"""SmallWebRTC signaling — media plane (Phase 2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from relay_gateway.deps import session_manager

router = APIRouter(tags=["webrtc"])


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


def _require_token(session_id: str, token: str | None) -> None:
    if not token or not session_manager.validate_dev_token(session_id, token):
        raise HTTPException(status_code=401, detail="invalid or expired session token")


@router.post("/sessions/{session_id}/webrtc/offer")
async def webrtc_offer(
    session_id: str,
    body: WebRtcOfferBody,
    token: str = Query(..., description="Dev session token"),
) -> dict[str, Any]:
    _require_token(session_id, token)
    if session_manager.realtime_transport is None:
        raise HTTPException(status_code=503, detail="realtime transport unavailable")
    try:
        return await session_manager.start_realtime(
            session_id,
            body.model_dump(exclude_none=True),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.patch("/sessions/{session_id}/webrtc/offer")
async def webrtc_ice_patch(
    session_id: str,
    body: WebRtcPatchBody,
    token: str = Query(..., description="Dev session token"),
) -> dict[str, str]:
    _require_token(session_id, token)
    if session_manager.realtime_transport is None:
        raise HTTPException(status_code=503, detail="realtime transport unavailable")
    try:
        await session_manager.patch_realtime_ice(
            session_id,
            pc_id=body.pc_id,
            candidates=[c.model_dump() for c in body.candidates],
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}
