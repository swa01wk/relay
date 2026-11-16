"""Route ACTION_REQUESTED to the client and correlate ACTION_APPLIED / ACTION_FAILED."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

from relay_protocol import EventType, RelayEvent, RelayEventMetadata, minimal_payload_for


ActionOutcome = Literal["applied", "failed", "timeout"]


@dataclass
class ActionRouter:
    """Per-session pending UI actions (client executes rendering)."""

    _pending: dict[str, asyncio.Future[ActionOutcome]] = field(default_factory=dict)
    _results: dict[str, dict[str, Any]] = field(default_factory=dict)

    def new_action_id(self) -> str:
        return str(uuid4())

    async def request_with_result(
        self,
        *,
        publish: Any,
        metadata: RelayEventMetadata,
        name: str,
        params: dict[str, Any],
        timeout_seconds: float = 15.0,
    ) -> tuple[ActionOutcome, dict[str, Any]]:
        """Request an action and wait for the client's outcome plus its result / failure reason."""
        holder: dict[str, str] = {}
        outcome = await self.request(
            publish=publish,
            metadata=metadata,
            name=name,
            params=params,
            wait=True,
            timeout_seconds=timeout_seconds,
            _action_id_out=holder,
        )
        return outcome or "timeout", self._results.pop(holder.get("action_id", ""), {})

    async def request(
        self,
        *,
        publish: Any,
        metadata: RelayEventMetadata,
        name: str,
        params: dict[str, Any],
        wait: bool = False,
        timeout_seconds: float = 15.0,
        _action_id_out: dict[str, str] | None = None,
    ) -> ActionOutcome | None:
        action_id = self.new_action_id()
        if _action_id_out is not None:
            _action_id_out["action_id"] = action_id
        event = RelayEvent(
            type=EventType.ACTION_REQUESTED,
            metadata=metadata.model_copy(update={"correlation_id": action_id}),
            payload={
                "action": name,
                "action_id": action_id,
                "params": params,
            },
        )
        await publish(event)
        if not wait:
            return None

        loop = asyncio.get_running_loop()
        future: asyncio.Future[ActionOutcome] = loop.create_future()
        self._pending[action_id] = future
        try:
            return await asyncio.wait_for(future, timeout=timeout_seconds)
        except TimeoutError:
            self._pending.pop(action_id, None)
            return "timeout"

    def resolve(
        self, action_id: str, outcome: ActionOutcome, result: dict[str, Any] | None = None
    ) -> None:
        future = self._pending.pop(action_id, None)
        if future is not None and not future.done():
            if result:
                self._results[action_id] = dict(result)
            future.set_result(outcome)

    @staticmethod
    def applied_event(
        *,
        metadata: RelayEventMetadata,
        action_id: str,
        name: str,
        result: dict[str, Any] | None = None,
    ) -> RelayEvent:
        payload = dict(minimal_payload_for(EventType.ACTION_APPLIED))
        payload["action"] = name
        payload["action_id"] = action_id
        if result:
            payload["result"] = result
        return RelayEvent(
            type=EventType.ACTION_APPLIED,
            metadata=metadata.model_copy(update={"correlation_id": action_id}),
            payload=payload,
        )

    @staticmethod
    def failed_event(
        *,
        metadata: RelayEventMetadata,
        action_id: str,
        name: str,
        reason: str,
    ) -> RelayEvent:
        payload = dict(minimal_payload_for(EventType.ACTION_FAILED))
        payload["action"] = name
        payload["action_id"] = action_id
        payload["reason"] = reason
        return RelayEvent(
            type=EventType.ACTION_FAILED,
            metadata=metadata.model_copy(update={"correlation_id": action_id}),
            payload=payload,
        )
