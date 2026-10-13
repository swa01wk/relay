"""Model-proposed side-effecting actions: propose → human approval → execute → follow-up turn."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from relay_protocol import EventType
from relay_runtime import (
    AgentRuntime,
    MemoryEventStore,
    ModelRouter,
    PersistingEventGateway,
    RegistryToolExecutor,
    SessionManager,
    ToolClassification,
    ToolDefinition,
    ToolRegistry,
    ToolUsingAgent,
)
from relay_runtime.ports.model import ModelProvider
from relay_runtime.ports.tools import ToolExecutor


class RecordingStore(ToolExecutor):
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, session_id, *, tool_name, arguments, idempotency_key=None):
        del session_id, idempotency_key
        self.calls.append((tool_name, dict(arguments)))
        if tool_name == "update_deal_stage":
            return {"deal": {"id": arguments["deal_id"], "stage": arguments["stage"]}}
        return {"deal": {"id": "DEAL-2042", "stage": "Proposal"}}


class ProposingModel(ModelProvider):
    """Turn 1: propose a stage change. Follow-up turns: echo the outcome message."""

    def __init__(self, arguments: dict[str, Any]) -> None:
        self.arguments = arguments
        self.offered: list[str] = []
        self.user_texts: list[str] = []

    async def stream_completion(
        self, session_id: str, *, messages: list[dict[str, Any]], tools: Any = None
    ) -> AsyncIterator[dict[str, Any]]:
        del session_id
        self.offered = [t["function"]["name"] for t in tools or []]
        last_user = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        self.user_texts.append(last_user)
        if last_user.startswith("[Action"):
            yield {"type": "token", "text": f"Noted: {last_user[:40]}"}
            return
        if not [m for m in messages if m.get("role") == "tool"]:
            yield {
                "type": "tool_calls",
                "calls": [{"id": "c1", "name": "update_deal_stage", "arguments": json.dumps(self.arguments)}],
            }
            return
        yield {"type": "token", "text": "I've asked you to approve the change."}

    async def cancel(self, session_id: str) -> None:
        del session_id


def _setup(arguments: dict[str, Any]):
    registry = ToolRegistry()
    registry.register(ToolDefinition(
        name="get_deal", classification=ToolClassification.READ_ONLY, description="One deal",
        input_schema={"type": "object", "properties": {"deal_id": {"type": "string"}}},
    ))
    registry.register(ToolDefinition(
        name="update_deal_stage", classification=ToolClassification.SIDE_EFFECTING,
        description="Move a deal to another stage",
        input_schema={
            "type": "object",
            "required": ["deal_id", "stage"],
            "properties": {"deal_id": {"type": "string", "minLength": 1}, "stage": {"type": "string"}},
        },
    ))
    registry.register(ToolDefinition(
        name="delete_deal", classification=ToolClassification.SIDE_EFFECTING, description="Delete",
        input_schema={"type": "object", "required": ["deal_id"], "properties": {"deal_id": {"type": "string"}}},
    ))
    model = ProposingModel(arguments)
    router = ModelRouter(model)
    store = RecordingStore()
    events = MemoryEventStore()
    manager = SessionManager(
        event_gateway=PersistingEventGateway(events),
        agent_runtime=AgentRuntime(
            model_router=router,
            agent=ToolUsingAgent(router, system_prompt="CRM assistant", registry=registry),
            tool_executor=RegistryToolExecutor(registry=registry, delegate=store),
        ),
        session_lock=None,
        idle_grace_seconds=0,
    )
    return manager, events, store, model


def _of(events: MemoryEventStore, kind: EventType):
    return [e for e in events.all_events() if e.type == kind]


async def _settle(manager: SessionManager, session_id: str) -> None:
    for _ in range(50):
        await asyncio.sleep(0.02)
        session = manager.get(session_id)
        if session is None or session.queue.empty():
            await asyncio.sleep(0.05)
            return


@pytest.mark.asyncio
async def test_proposal_waits_for_approval_then_executes_and_confirms():
    manager, events, store, model = _setup(
        {"deal_id": "DEAL-2042", "stage": "Negotiation", "summary": "Move DEAL-2042 from Proposal to Negotiation"}
    )
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    try:
        await manager.submit_user_text(session.session_id, "Move DEAL-2042 to Negotiation")

        assert {"update_deal_stage", "delete_deal", "get_deal"} <= set(model.offered)
        requested = _of(events, EventType.APPROVAL_REQUESTED)
        assert len(requested) == 1
        payload = requested[0].payload
        assert payload["summary"] == "Move DEAL-2042 from Proposal to Negotiation"
        assert payload["arguments"] == {"deal_id": "DEAL-2042", "stage": "Negotiation"}
        assert "followup" not in payload and "verify_tool" not in payload
        assert store.calls == []  # nothing happens before approval

        await manager.submit_client_app_event(
            session.session_id,
            name="approval.grant",
            payload={"approval_id": payload["approval_id"], "auth_proof": "dev-approver"},
        )
        await _settle(manager, session.session_id)
    finally:
        await manager.end_session(session.session_id)

    assert store.calls == [("update_deal_stage", {"deal_id": "DEAL-2042", "stage": "Negotiation"})]
    verified = _of(events, EventType.COMMIT_VERIFIED)
    assert verified and verified[-1].payload["verified"] is True
    assert verified[-1].payload["result"]["deal"]["stage"] == "Negotiation"
    assert model.user_texts[-1].startswith("[Action approved] Move DEAL-2042 from Proposal to Negotiation")
    assert _of(events, EventType.RESPONSE_COMPLETED)[-1].payload["text"].startswith("Noted: [Action approved]")


@pytest.mark.asyncio
async def test_rejected_proposal_never_executes():
    manager, events, store, model = _setup({"deal_id": "DEAL-2042", "stage": "Closed Lost", "summary": "Mark DEAL-2042 lost"})
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    try:
        await manager.submit_user_text(session.session_id, "Mark it lost")
        approval_id = _of(events, EventType.APPROVAL_REQUESTED)[0].payload["approval_id"]
        await manager.submit_client_app_event(
            session.session_id, name="approval.reject", payload={"approval_id": approval_id}
        )
        await _settle(manager, session.session_id)
    finally:
        await manager.end_session(session.session_id)

    assert store.calls == []
    assert _of(events, EventType.APPROVAL_REJECTED)
    assert model.user_texts[-1] == "[Action rejected] Mark DEAL-2042 lost"


@pytest.mark.asyncio
async def test_invalid_proposal_is_rejected_before_any_approval():
    manager, events, store, _model = _setup({"stage": "Negotiation", "summary": "missing deal id"})
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    try:
        await manager.submit_user_text(session.session_id, "Move it")
    finally:
        await manager.end_session(session.session_id)
    assert _of(events, EventType.APPROVAL_REQUESTED) == []
    assert store.calls == []


@pytest.mark.asyncio
async def test_side_effect_guard_requires_a_grant_for_that_exact_tool():
    manager, events, store, _model = _setup({"deal_id": "DEAL-2042", "stage": "Negotiation", "summary": "Move it"})
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    try:
        await manager.submit_user_text(session.session_id, "Move it")
        approval_id = _of(events, EventType.APPROVAL_REQUESTED)[0].payload["approval_id"]
        executor = manager._tools_for(manager.get(session.session_id))
        hitl = manager.get(session.session_id).hitl_manager

        # Not granted yet → blocked even with the right approval id.
        pending = await executor.execute(
            session.session_id, tool_name="update_deal_stage",
            arguments={"deal_id": "DEAL-2042", "stage": "Negotiation"}, approval_id=approval_id,
        )
        assert pending == {"error": "side_effecting_blocked_until_hitl"}

        hitl.grant(approval_id, auth_proof="dev-approver")
        # Granted for update_deal_stage → cannot be reused to delete.
        other = await executor.execute(
            session.session_id, tool_name="delete_deal", arguments={"deal_id": "DEAL-2042"}, approval_id=approval_id,
        )
        assert other == {"error": "side_effecting_blocked_until_hitl"}
        # No approval id at all → blocked.
        none = await executor.execute(session.session_id, tool_name="delete_deal", arguments={"deal_id": "DEAL-2042"})
        assert none == {"error": "side_effecting_blocked_until_hitl"}
    finally:
        await manager.end_session(session.session_id)
    assert store.calls == []


@pytest.mark.asyncio
async def test_agent_decides_shared_state_after_a_saved_change():
    """The runtime knows no domain: after a verified save it asks the agent for the new state."""
    manager, events, _store, _model = _setup({"deal_id": "DEAL-2042", "stage": "Negotiation", "summary": "Move it"})
    seen: dict[str, Any] = {}

    def state_after_commit(*, state, tool_name, arguments, commit_result, verify_result):
        seen.update(tool_name=tool_name, arguments=arguments, verify_result=verify_result)
        return {**state, "last_saved": commit_result["deal"]["stage"]}

    manager.agent_runtime.agent.state_after_commit = state_after_commit
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    try:
        await manager.submit_user_text(session.session_id, "Move DEAL-2042 to Negotiation")
        assert "last_saved" not in session.context.state
        approval_id = _of(events, EventType.APPROVAL_REQUESTED)[0].payload["approval_id"]
        await manager.submit_client_app_event(
            session.session_id,
            name="approval.grant",
            payload={"approval_id": approval_id, "auth_proof": "dev-approver"},
        )
        await _settle(manager, session.session_id)

        assert session.context.state["last_saved"] == "Negotiation"
        assert seen["tool_name"] == "update_deal_stage" and seen["arguments"]["deal_id"] == "DEAL-2042"
        verified = _of(events, EventType.COMMIT_VERIFIED)[0].payload
        assert verified["verified"] is True and verified["verify_result"] is None  # no verify step here
    finally:
        await manager.end_session(session.session_id)


def test_runtime_and_published_packages_contain_no_example_domain():
    """Relay is domain-agnostic: example domains live in examples/ and agents/, never in the engine,
    the adapters, the gateway (one opt-in module aside), the SDK or the CLI."""
    import re
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    domain = re.compile(r"mortgage|crm\b|sales[-_ ]crm", re.IGNORECASE)
    sources = [
        *(repo / "runtime" / "src").rglob("*.py"),
        *(repo / "packages" / "protocol" / "src").rglob("*.py"),
        *(repo / "packages" / "web-sdk" / "src").glob("*.ts"),
        *(repo / "packages" / "cli" / "src").glob("*.mjs"),
        *(repo / "packages" / "cli" / "bin").glob("*.mjs"),
        *(repo / "adapters").glob("*/*/src/**/*.py"),
        *(repo / "adapters").glob("*/*/src/**/*.txt"),
        *(p for p in (repo / "services" / "gateway" / "src").rglob("*.py") if p.name != "example_agents.py"),
    ]
    assert len(sources) > 20
    offenders = [f"{p.relative_to(repo)}:{n}" for p in sources if ".test." not in p.name
                 for n, line in enumerate(p.read_text().splitlines(), 1) if domain.search(line)]
    assert offenders == []
