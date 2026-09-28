"""POC-only dev session endpoints."""

from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException

from relay_gateway.deps import event_store, session_manager
from relay_runtime.session_timeline import build_session_timeline

router = APIRouter(prefix="/dev", tags=["dev-sessions"])


class DevSessionCreateRequest(BaseModel):
    project_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)


class DevSessionCreateResponse(BaseModel):
    session_id: str
    dev_token: str
    token_expires_at: str
    events: list[dict]


@router.post("/sessions", response_model=DevSessionCreateResponse)
async def create_dev_session(body: DevSessionCreateRequest) -> DevSessionCreateResponse:
    """Mint a short-lived dev token and emit SESSION_STARTED + SESSION_READY."""
    session, events = await session_manager.create_dev_session(
        project_id=body.project_id,
        agent_id=body.agent_id,
    )
    return DevSessionCreateResponse(
        session_id=session.session_id,
        dev_token=session.dev_token,
        token_expires_at=session.token_expires_at.isoformat(),
        events=[e.model_dump(mode="json") for e in events],
    )


@router.get("/sessions/{session_id}")
async def get_dev_session(session_id: str, token: str) -> dict:
    if not session_manager.validate_dev_token(session_id, token):
        raise HTTPException(status_code=401, detail="invalid or expired dev token")
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return {
        "session_id": session.session_id,
        "project_id": session.project_id,
        "agent_id": session.agent_id,
        "trace_id": session.trace_id,
    }


@router.get("/sessions/{session_id}/timeline")
async def get_session_timeline(session_id: str, token: str) -> dict:
    """Ordered RP events + metrics/spans waterfall (Phase 10)."""
    if not session_manager.validate_dev_token(session_id, token):
        raise HTTPException(status_code=401, detail="invalid or expired dev token")
    events = await event_store.list_for_session(session_id)
    return build_session_timeline(events)
