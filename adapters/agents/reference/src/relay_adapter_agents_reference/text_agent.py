"""Thin text agent: system prompt + streaming model completion."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from relay_protocol import EventType, RelayEvent, minimal_payload_for
from relay_runtime.model_router import ModelRouter
from relay_runtime.ports.agent import AgentAdapter


class ReferenceTextAgent(AgentAdapter):
    def __init__(self, model_router: ModelRouter, *, system_prompt: str | None = None) -> None:
        self._model_router = model_router
        self._system_prompt = system_prompt or _default_system_prompt()

    async def on_turn(
        self,
        session_id: str,
        *,
        context: dict[str, Any],
    ) -> list[RelayEvent]:
        events: list[RelayEvent] = []
        full_text = ""
        async for token in self.stream_turn(session_id, context=context):
            full_text += token
            events.append(
                RelayEvent(
                    type=EventType.RESPONSE_DELTA,
                    metadata=_stub_metadata(session_id, context),
                    payload={"text": token},
                )
            )
        events.append(
            RelayEvent(
                type=EventType.RESPONSE_COMPLETED,
                metadata=_stub_metadata(session_id, context),
                payload={"text": full_text or minimal_payload_for(EventType.RESPONSE_COMPLETED).get("text", "")},
            )
        )
        return events

    async def stream_turn(
        self,
        session_id: str,
        *,
        context: dict[str, Any],
    ) -> AsyncIterator[str]:
        messages: list[dict[str, str]] = [{"role": "system", "content": self._system_prompt}]
        for item in context.get("messages", []):
            messages.append({"role": item["role"], "content": item["content"]})

        provider = self._model_router.get_provider()
        async for chunk in provider.stream_completion(session_id, messages=messages):
            token = str(chunk.get("text", ""))
            if token:
                yield token


def _stub_metadata(session_id: str, context: dict[str, Any]) -> Any:
    from relay_protocol import RelayEventMetadata

    return RelayEventMetadata(
        session_id=session_id,
        sequence=0,
        source="reference_agent",
        turn_id=str(context.get("turn_id")) if context.get("turn_id") else None,
        trace_id=None,
        project_id=None,
    )


def _default_system_prompt() -> str:
    bundled = Path(__file__).resolve().parent / "system_prompt.txt"
    if bundled.is_file():
        return bundled.read_text(encoding="utf-8").strip()
    return (
        "You are a helpful mortgage servicing reference assistant. "
        "Answer briefly and professionally. You do not have access to tools yet."
    )
