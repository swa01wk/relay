"""Tool execution with registry governance, parallel calls, and RP progress events."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from relay_protocol import EventType, RelayEvent, RelayEventMetadata, minimal_payload_for

from relay_runtime.context_manager import ContextManager
from relay_runtime.interruption_manager import InterruptionManager
from relay_runtime.ports.tools import ToolExecutor
from relay_runtime.hitl_manager import HITLManager
from relay_runtime.observability import STAGE_TOOL, emit_trace_span
from relay_runtime.tool_registry import ToolClassification, ToolRegistry
from relay_runtime.turn_cancellation import TurnCancellation
from relay_runtime.trace_manager import TraceManager

PublishFn = Callable[[RelayEvent], Awaitable[None]]
MetadataFn = Callable[[], RelayEventMetadata]

logger = logging.getLogger(__name__)


HitlLookup = Callable[[str], HITLManager | None]


@dataclass
class RegistryToolExecutor:
    registry: ToolRegistry
    delegate: ToolExecutor
    trace_manager: TraceManager = field(default_factory=TraceManager)
    default_timeout_seconds: float = 30.0
    read_only_retries: int = 1
    hitl_for_session: HitlLookup | None = None

    async def execute(
        self,
        session_id: str,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        turn_id: str | None = None,
        publish: PublishFn | None = None,
        base_metadata: MetadataFn | None = None,
        context: ContextManager | None = None,
        idempotency_key: str | None = None,
        approval_id: str | None = None,
        cancel: TurnCancellation | None = None,
    ) -> dict[str, Any]:
        results = await self.execute_parallel(
            session_id,
            calls=[{"tool_name": tool_name, "arguments": arguments}],
            turn_id=turn_id,
            publish=publish,
            base_metadata=base_metadata,
            context=context,
            activity_label=None,
            idempotency_key=idempotency_key,
            approval_id=approval_id,
            cancel=cancel,
        )
        return results[0] if results else {"error": "no_result"}

    async def execute_parallel(
        self,
        session_id: str,
        *,
        calls: list[dict[str, Any]],
        turn_id: str | None = None,
        publish: PublishFn | None = None,
        base_metadata: MetadataFn | None = None,
        context: ContextManager | None = None,
        activity_label: str | None = None,
        idempotency_key: str | None = None,
        approval_id: str | None = None,
        cancel: TurnCancellation | None = None,
    ) -> list[dict[str, Any]]:
        if not calls:
            return []

        activity_id = str(uuid4()) if activity_label and publish and base_metadata else None
        if activity_id is not None:
            await publish(
                RelayEvent(
                    type=EventType.ACTIVITY_STARTED,
                    metadata=base_metadata().model_copy(
                        update={"turn_id": turn_id, "source": "tool_executor"}
                    ),
                    payload={"activity_id": activity_id, "label": activity_label},
                )
            )

        async def run_one(spec: dict[str, Any]) -> dict[str, Any]:
            return await self._execute_one(
                session_id,
                tool_name=str(spec["tool_name"]),
                arguments=dict(spec.get("arguments") or {}),
                turn_id=turn_id,
                publish=publish,
                base_metadata=base_metadata,
                context=context,
                idempotency_key=idempotency_key,
                approval_id=approval_id,
                cancel=cancel,
            )

        completed = 0
        lock = asyncio.Lock()

        async def run_one_tracked(spec: dict[str, Any]) -> dict[str, Any]:
            nonlocal completed
            result = await run_one(spec)
            if activity_id is not None and publish is not None and base_metadata is not None:
                async with lock:
                    completed += 1
                    progress = completed / len(calls)
                await publish(
                    RelayEvent(
                        type=EventType.ACTIVITY_PROGRESS,
                        metadata=base_metadata().model_copy(
                            update={"turn_id": turn_id, "source": "tool_executor"}
                        ),
                        payload={
                            "activity_id": activity_id,
                            "progress": progress,
                            "completed": completed,
                            "total": len(calls),
                        },
                    )
                )
            return result

        try:
            ordered = await asyncio.gather(
                *[run_one_tracked(spec) for spec in calls], return_exceptions=True
            )
        finally:
            if activity_id is not None and publish is not None and base_metadata is not None:
                await publish(
                    RelayEvent(
                        type=EventType.ACTIVITY_COMPLETED,
                        metadata=base_metadata().model_copy(
                            update={"turn_id": turn_id, "source": "tool_executor"}
                        ),
                        payload={"activity_id": activity_id},
                    )
                )

        results: list[dict[str, Any]] = []
        for item in ordered:
            if isinstance(item, BaseException):
                results.append({"error": str(item)})
            else:
                results.append(item)
        return results

    async def _execute_one(
        self,
        session_id: str,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        turn_id: str | None,
        publish: PublishFn | None,
        base_metadata: MetadataFn | None,
        context: ContextManager | None,
        idempotency_key: str | None,
        approval_id: str | None = None,
        cancel: TurnCancellation | None = None,
    ) -> dict[str, Any]:
        if cancel and cancel.is_cancelled:
            return {"error": "turn_cancelled", "ignored": True}

        blocked, reason = self.registry.is_blocked(tool_name)
        if blocked:
            err = reason or "blocked"
            await self._emit_failed(
                tool_name=tool_name,
                tool_call_id=self.trace_manager.new_tool_call_id(),
                turn_id=turn_id,
                publish=publish,
                base_metadata=base_metadata,
                error=err,
            )
            return {"error": err}

        resolved_idempotency_key = idempotency_key
        if self.registry.is_side_effecting(tool_name):
            hitl = self.hitl_for_session(session_id) if self.hitl_for_session else None
            if hitl is None or not hitl.can_execute_side_effect(approval_id, tool_name):
                err = "side_effecting_blocked_until_hitl"
                await self._emit_failed(
                    tool_name=tool_name,
                    tool_call_id=self.trace_manager.new_tool_call_id(),
                    turn_id=turn_id,
                    publish=publish,
                    base_metadata=base_metadata,
                    error=err,
                )
                return {"error": err}
            if resolved_idempotency_key is None and approval_id:
                resolved_idempotency_key = hitl.idempotency_key_for(approval_id)

        call_arguments = dict(arguments)

        validation_error = self.registry.validate_input(tool_name, call_arguments)
        if validation_error:
            await self._emit_failed(
                tool_name=tool_name,
                tool_call_id=self.trace_manager.new_tool_call_id(),
                turn_id=turn_id,
                publish=publish,
                base_metadata=base_metadata,
                error=validation_error,
            )
            return {"error": validation_error}

        definition = self.registry.get(tool_name)
        classification = (
            definition.classification if definition is not None else ToolClassification.READ_ONLY
        )

        tool_call_id = self.trace_manager.new_tool_call_id()
        correlation_id = self.trace_manager.new_correlation_id()
        trace_id = base_metadata().trace_id if base_metadata is not None else None
        if publish is not None and base_metadata is not None and trace_id:
            await emit_trace_span(
                publish=publish,
                base_metadata=base_metadata,
                stage=STAGE_TOOL,
                trace_id=trace_id,
                turn_id=turn_id,
                tool_call_id=tool_call_id,
                attributes={"tool_name": tool_name, "phase": "start"},
            )
        if publish is not None and base_metadata is not None:
            await publish(
                RelayEvent(
                    type=EventType.TOOL_CALL_STARTED,
                    metadata=base_metadata().model_copy(
                        update={
                            "turn_id": turn_id,
                            "tool_call_id": tool_call_id,
                            "correlation_id": correlation_id,
                            "source": "tool_executor",
                        }
                    ),
                    payload={"name": tool_name, "arguments": call_arguments},
                )
            )
            await publish(
                RelayEvent(
                    type=EventType.TOOL_CALL_PROGRESS,
                    metadata=base_metadata().model_copy(
                        update={
                            "turn_id": turn_id,
                            "tool_call_id": tool_call_id,
                            "correlation_id": correlation_id,
                            "source": "tool_executor",
                        }
                    ),
                    payload={"name": tool_name, "progress": 0.0},
                )
            )

        attempts = max(1, 1 + self.read_only_retries)
        last_error = "unknown"
        result: dict[str, Any] | None = None
        for attempt in range(attempts):
            try:
                result = await asyncio.wait_for(
                    self.delegate.execute(
                        session_id,
                        tool_name=tool_name,
                        arguments=call_arguments,
                        idempotency_key=resolved_idempotency_key,
                    ),
                    timeout=self.default_timeout_seconds,
                )
                break
            except TimeoutError:
                last_error = "timeout"
                if attempt + 1 >= attempts:
                    break
            except Exception as exc:  # noqa: BLE001 — surface as TOOL_CALL_FAILED
                last_error = str(exc)
                if attempt + 1 >= attempts:
                    break

        if result is None:
            await self._emit_failed(
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                turn_id=turn_id,
                publish=publish,
                base_metadata=base_metadata,
                error=last_error,
            )
            return {"error": last_error}

        if cancel and cancel.is_cancelled:
            turn_active = context is not None and context.active_turn_id == turn_id
            if InterruptionManager.discard_tool_result_on_interrupt(
                classification=classification,
                turn_active=turn_active,
            ):
                logger.info(
                    "dropping tool result after interrupt tool=%s turn_id=%s",
                    tool_name,
                    turn_id,
                )
                return {"error": "turn_cancelled", "ignored": True, "result": result}

        out_err = self.registry.validate_output(tool_name, result)
        if out_err:
            await self._emit_failed(
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                turn_id=turn_id,
                publish=publish,
                base_metadata=base_metadata,
                error=out_err,
            )
            return {"error": out_err}

        if context is not None and turn_id is not None:
            if not context.merge_tool_result(
                turn_id=turn_id,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                result=result,
            ):
                logger.info(
                    "dropping stale tool result tool=%s turn_id=%s active=%s",
                    tool_name,
                    turn_id,
                    context.active_turn_id,
                )
                return {"error": "stale_turn", "ignored": True, "result": result}

        if publish is not None and base_metadata is not None and trace_id:
            await emit_trace_span(
                publish=publish,
                base_metadata=base_metadata,
                stage=STAGE_TOOL,
                trace_id=trace_id,
                turn_id=turn_id,
                tool_call_id=tool_call_id,
                attributes={"tool_name": tool_name, "phase": "complete"},
            )
        if publish is not None and base_metadata is not None:
            await publish(
                RelayEvent(
                    type=EventType.TOOL_CALL_PROGRESS,
                    metadata=base_metadata().model_copy(
                        update={
                            "turn_id": turn_id,
                            "tool_call_id": tool_call_id,
                            "correlation_id": correlation_id,
                            "source": "tool_executor",
                        }
                    ),
                    payload={"name": tool_name, "progress": 1.0},
                )
            )
            await publish(
                RelayEvent(
                    type=EventType.TOOL_CALL_COMPLETED,
                    metadata=base_metadata().model_copy(
                        update={
                            "turn_id": turn_id,
                            "tool_call_id": tool_call_id,
                            "correlation_id": correlation_id,
                            "source": "tool_executor",
                        }
                    ),
                    payload={"name": tool_name, "result": result},
                )
            )
        return result

    async def _emit_failed(
        self,
        *,
        tool_name: str,
        tool_call_id: str,
        turn_id: str | None,
        publish: PublishFn | None,
        base_metadata: MetadataFn | None,
        error: str,
    ) -> None:
        if publish is None or base_metadata is None:
            return
        await publish(
            RelayEvent(
                type=EventType.TOOL_CALL_FAILED,
                metadata=base_metadata().model_copy(
                    update={
                        "turn_id": turn_id,
                        "tool_call_id": tool_call_id,
                        "source": "tool_executor",
                    }
                ),
                payload={"name": tool_name, "error": error},
            )
        )
