"""Run a text turn: agent adapter + streaming model output as RP events."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from relay_protocol import EventType, RelayEvent, RelayEventMetadata, minimal_payload_for

from relay_runtime.action_router import ActionRouter
from relay_runtime.context_manager import ContextManager
from relay_runtime.model_router import ModelRouter
from relay_runtime.ports.agent import AgentAdapter
from relay_runtime.registry_tool_executor import RegistryToolExecutor
from relay_runtime.observability import STAGE_MODEL, emit_trace_span
from relay_runtime.turn_cancellation import TurnCancellation

PublishFn = Callable[[RelayEvent], Awaitable[None]]
AgentEventFn = Callable[[RelayEvent], Awaitable[bool]]
TokenFn = Callable[[str], Awaitable[None]]
MetricFn = Callable[[str, float], Awaitable[None]]


@dataclass
class AgentRuntime:
    model_router: ModelRouter
    agent: AgentAdapter
    tool_executor: RegistryToolExecutor | None = None

    async def _assistant_tokens(
        self,
        session_id: str,
        *,
        agent_context: dict[str, Any],
        cancel: TurnCancellation | None = None,
    ) -> AsyncIterator[str]:
        if hasattr(self.agent, "stream_turn"):
            async for token in self.agent.stream_turn(session_id, context=agent_context):
                if cancel and cancel.is_cancelled:
                    break
                yield token
            return
        events = await self.agent.on_turn(session_id, context=agent_context)
        for event in events:
            if cancel and cancel.is_cancelled:
                break
            if event.type == EventType.RESPONSE_DELTA:
                chunk = str(event.payload.get("text", ""))
                if chunk:
                    yield chunk

    async def run_streaming_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        user_text: str,
        context: ContextManager,
        base_metadata: Callable[[], RelayEventMetadata],
        publish: PublishFn,
        include_user_transcript: bool = True,
        on_token: TokenFn | None = None,
        cancel: TurnCancellation | None = None,
        on_metric: MetricFn | None = None,
        action_router: ActionRouter | None = None,
        emit_agent_event: AgentEventFn | None = None,
    ) -> str:
        context.append_user(user_text)
        if include_user_transcript:
            transcript = RelayEvent(
                type=EventType.TRANSCRIPT_FINAL,
                metadata=base_metadata().model_copy(
                    update={"turn_id": turn_id, "source": "agent_runtime"}
                ),
                payload={"text": user_text, "is_final": True},
            )
            await publish(transcript)

        response_id = str(uuid4())
        started = RelayEvent(
            type=EventType.RESPONSE_STARTED,
            metadata=base_metadata().model_copy(
                update={
                    "turn_id": turn_id,
                    "response_id": response_id,
                    "source": "agent_runtime",
                }
            ),
            payload=minimal_payload_for(EventType.RESPONSE_STARTED),
        )
        await publish(started)

        trace_id = base_metadata().trace_id
        if trace_id:
            await emit_trace_span(
                publish=publish,
                base_metadata=base_metadata,
                stage=STAGE_MODEL,
                trace_id=trace_id,
                turn_id=turn_id,
                attributes={"phase": "start"},
            )

        async def emit_event(event: RelayEvent) -> None:
            if emit_agent_event is not None:
                await emit_agent_event(event)

        async def request_action(
            name: str,
            params: dict[str, Any],
            *,
            wait: bool = False,
        ) -> None:
            if action_router is None:
                return
            await action_router.request(
                publish=publish,
                metadata=base_metadata().model_copy(update={"turn_id": turn_id, "source": "agent"}),
                name=name,
                params=params,
                wait=wait,
            )

        async def request_hitl_approval(
            tool_name: str,
            arguments: dict[str, Any],
            *,
            summary: str = "",
        ) -> None:
            event = RelayEvent(
                type=EventType.APPROVAL_REQUESTED,
                metadata=base_metadata().model_copy(
                    update={"turn_id": turn_id, "source": "agent"}
                ),
                payload={
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "summary": summary,
                },
            )
            await emit_event(event)

        async def apply_state_delta(
            patch: list[dict[str, Any]],
            *,
            based_on_version: int,
        ) -> bool:
            if emit_agent_event is None:
                return False
            delta = RelayEvent(
                type=EventType.STATE_DELTA,
                metadata=base_metadata().model_copy(
                    update={
                        "turn_id": turn_id,
                        "source": "agent",
                        "based_on_version": based_on_version,
                    }
                ),
                payload={"patch": patch, "based_on_version": based_on_version},
            )
            return await emit_agent_event(delta)

        agent_context: dict[str, Any] = {
            "messages": context.as_chat_messages(),
            "user_text": user_text,
            "session_id": session_id,
            "turn_id": turn_id,
            "state": context.state_summary_for_agent(),
            "live_state": lambda: context.state_summary_for_agent(),
            "live_state_version": lambda: context.state_version,
            "tool_results": context.tool_results_for_agent(),
            "emit_event": emit_event,
            "request_action": request_action,
            "request_hitl_approval": request_hitl_approval,
            "apply_state_delta": apply_state_delta,
        }
        if self.tool_executor is not None:

            async def run_tool(name: str, params: dict[str, Any]) -> dict[str, Any]:
                return await self.tool_executor.execute(
                    session_id,
                    tool_name=name,
                    arguments=params,
                    turn_id=turn_id,
                    publish=publish,
                    base_metadata=base_metadata,
                    context=context,
                    cancel=cancel,
                )

            async def run_tools_parallel(
                calls: list[dict[str, Any]],
                *,
                activity_label: str | None = None,
            ) -> list[dict[str, Any]]:
                return await self.tool_executor.execute_parallel(
                    session_id,
                    calls=calls,
                    turn_id=turn_id,
                    publish=publish,
                    base_metadata=base_metadata,
                    context=context,
                    activity_label=activity_label,
                    cancel=cancel,
                )

            agent_context["run_tool"] = run_tool
            agent_context["run_tools_parallel"] = run_tools_parallel
        assistant_text = ""
        model_started = time.perf_counter()
        first_token_at: float | None = None
        async for token in self._assistant_tokens(
            session_id, agent_context=agent_context, cancel=cancel
        ):
            if first_token_at is None:
                first_token_at = time.perf_counter()
                if on_metric:
                    await on_metric("model.ttft_ms", (first_token_at - model_started) * 1000.0)
            assistant_text += token
            await publish(
                RelayEvent(
                    type=EventType.RESPONSE_DELTA,
                    metadata=base_metadata().model_copy(
                        update={
                            "turn_id": turn_id,
                            "response_id": response_id,
                            "source": "agent_runtime",
                        }
                    ),
                    payload={"text": token},
                )
            )
            if on_token is not None:
                await on_token(token)

        if cancel and cancel.is_cancelled:
            cancelled = RelayEvent(
                type=EventType.RESPONSE_CANCELLED,
                metadata=base_metadata().model_copy(
                    update={
                        "turn_id": turn_id,
                        "response_id": response_id,
                        "source": "agent_runtime",
                    }
                ),
                payload={"reason": "interrupt"},
            )
            await publish(cancelled)
            await self.model_router.get_provider().cancel(session_id)
            return assistant_text

        completed = RelayEvent(
            type=EventType.RESPONSE_COMPLETED,
            metadata=base_metadata().model_copy(
                update={
                    "turn_id": turn_id,
                    "response_id": response_id,
                    "source": "agent_runtime",
                }
            ),
            payload={
                "text": assistant_text,
                "generated_text": assistant_text,
            },
        )
        await publish(completed)
        context.append_assistant(assistant_text)
        return assistant_text

    async def run_text_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        user_text: str,
        context: ContextManager,
        base_metadata: Callable[[], RelayEventMetadata],
        publish: PublishFn,
        include_user_transcript: bool = True,
        action_router: ActionRouter | None = None,
        emit_agent_event: AgentEventFn | None = None,
    ) -> str:
        return await self.run_streaming_turn(
            session_id=session_id,
            turn_id=turn_id,
            user_text=user_text,
            context=context,
            base_metadata=base_metadata,
            publish=publish,
            include_user_transcript=include_user_transcript,
            action_router=action_router,
            emit_agent_event=emit_agent_event,
        )
