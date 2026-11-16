"""Generic LLM agent: read tools from a ToolRegistry + ``present_ui`` generative UI.

A domain supplies a system prompt, a registry and optional extra instructions; the model
fetches data with read-only tools and renders results with ``present_ui`` (Web SDK surfaces).
Side-effecting tools are never offered to the model.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any

from uuid import uuid4

from relay_sdk import RelayEvent

from relay_runtime.hitl_manager import (
    ACTION_APPROVED_PREFIX,
    ACTION_FAILED_PREFIX,
    ACTION_REJECTED_PREFIX,
)
from relay_runtime.model_router import ModelRouter
from relay_runtime.ports.agent import AgentAdapter
from relay_runtime.tool_registry import ToolClassification, ToolRegistry
from relay_runtime.ui_surfaces import (
    FILL_FORM_ACTION,
    FILL_FORM_TOOL_NAME,
    fill_form_instructions,
    fill_form_tool,
    sanitize_form_fill,
    FORM_SUBMISSION_PREFIX,
    PRESENT_UI_ACTION,
    PRESENT_UI_TOOL_NAME,
    SURFACE_KINDS,
    form_fields_from_schema,
    model_tools_from_registry,
    present_ui_tool,
    sanitize_present_ui_arguments,
)

TokenFilter = Callable[[AsyncIterator[str]], AsyncIterator[str]]
ScreenFormatter = Callable[[dict[str, Any]], str | None]

MAX_MODEL_TOOL_ROUNDS = 4
MAX_TOOL_RESULT_CHARS = 6000
_MAX_SCREEN_STATE_CHARS = 4000


def canvas_instructions() -> str:
    """Domain-neutral rules for using ``present_ui``."""
    return (
        "You can show results on the user's screen with the present_ui tool (tables, "
        "key/value details, cards, charts, comparisons, markdown, notices, forms). When the user "
        "asks for a table, list, chart, graph, trend, comparison, breakdown or details, fetch "
        "only the data that request needs with the read tools (skip it if it is already in "
        "context), then call present_ui. For a chart, pass numbers (not strings) in data and "
        "pick the chart_type that fits. Use comparison to put 2-4 entities side by side, "
        "markdown for a formatted explanation, and a form when you need several details from "
        "the user (give it an id, and prefill any fields the user already gave you). When the "
        "user asks you to write, draft or rewrite something, write it yourself and prefill it in "
        "the form's text fields; never show an empty text field the user expected you to write. "
        "When editing an existing record, fetch it first and prefill its current values. "
        f"A message starting with {FORM_SUBMISSION_PREFIX!r} is the user's form submission. "
        "Submitting a form does not save anything: the values only reach you. Unless you call a "
        "tool that saves them, never say details were saved, updated or changed; confirm what "
        "you received instead. After showing results, reply with one short spoken sentence "
        "about what is on screen; do not read table or chart values aloud. Your text reply is "
        "shown as a chat message and may be spoken, so write it as plain sentences: never put "
        "tables, bullet lists, headings or other markdown in it — anything structured goes "
        "through present_ui."
    )


def approval_instructions() -> str:
    """Rules for tools that change data (offered as proposals that need the user's approval)."""
    return (
        "Tools whose description starts with 'Requires the user's approval' change data. Calling "
        "one does not change anything yet: it shows the user an approval request with Approve "
        "and Reject buttons in the assistant panel. Fill 'summary' with one plain sentence of "
        "the exact change (e.g. 'Move ORD-2042 from Pending to Shipped'). Before proposing a "
        "change to an existing record, fetch it and confirm it exists and allows that change; if "
        "it doesn't, say so and offer to search — never propose a change to a record you haven't "
        "found. Then tell the user what will change and to approve it in the assistant panel — "
        "never say it is done. "
        f"A message starting with {ACTION_APPROVED_PREFIX!r} means the user approved and it was "
        "saved: confirm briefly using the result. "
        f"{ACTION_REJECTED_PREFIX!r} means they declined and nothing changed: acknowledge it. "
        f"{ACTION_FAILED_PREFIX!r} means saving failed: say so and why. "
        "When the user wants to create, log, add or edit something and you are missing details "
        "(or they ask for a form), call present_ui with a form whose submit_tool is that write "
        "tool's name: Relay builds the fields from the tool, you may list field names to choose "
        "and order them and pass values to prefill what you know (an id, current values, and "
        "any text the user asked you to write). Submitting that form saves directly. Propose the "
        "tool directly only when you have every value and the user did not ask to choose or "
        "edit them. If they ask for a form, want to pick values ('let me choose…', 'I'll set…') "
        "or want to write or edit text, show the form."
    )


def bind_tool_forms(arguments: dict[str, Any], registry: ToolRegistry) -> str | None:
    """Expand present_ui forms that name a ``submit_tool`` into fields from that tool's schema.

    Returns an error message for the model if a form names a tool that is not a write tool.
    """
    for surface in arguments.get("surfaces") or []:
        if not isinstance(surface, dict) or surface.get("kind") != "form" or not surface.get("submit_tool"):
            continue
        tool = str(surface["submit_tool"])
        definition = registry.get(tool)
        if definition is None or definition.classification != ToolClassification.SIDE_EFFECTING:
            writable = sorted(
                d.name for d in registry.list_tools() if d.classification == ToolClassification.SIDE_EFFECTING
            )
            return f"submit_tool must be one of {writable}"
        chosen = [f for f in surface.get("fields") or [] if isinstance(f, dict) and f.get("name")]
        values = dict(surface.get("values") or {}) if isinstance(surface.get("values"), dict) else {}
        for field in chosen:
            if field.get("default") is not None:
                values.setdefault(str(field["name"]), field["default"])
        surface["fields"] = form_fields_from_schema(
            definition.input_schema, include=[str(f["name"]) for f in chosen] or None, values=values
        )
        surface["id"] = f"{surface.get('id') or tool}-{uuid4().hex[:8]}"
        surface["title"] = surface.get("title") or definition.description or tool
        surface["submit_label"] = surface.get("submit_label") or "Save"
        surface.pop("values", None)
    return None


def proposal_tools_from_registry(registry: ToolRegistry) -> list[dict[str, Any]]:
    """Side-effecting tools as model tools that propose a change (approval required)."""
    tools: list[dict[str, Any]] = []
    for definition in registry.list_tools():
        if definition.classification != ToolClassification.SIDE_EFFECTING:
            continue
        schema = dict(definition.input_schema or {"type": "object", "properties": {}})
        properties = dict(schema.get("properties") or {})
        properties["summary"] = {
            "type": "string",
            "description": "One sentence describing the exact change, shown to the user to approve",
        }
        schema["properties"] = properties
        schema["required"] = [*schema.get("required", []), "summary"]
        description = definition.description or definition.name.replace("_", " ")
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": definition.name,
                    "description": f"Requires the user's approval. {description}",
                    "parameters": schema,
                },
            }
        )
    return tools


CLIENT_TOOL_PREFIX = "ui_"


def client_action_tools(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """App-advertised UI actions (screen changes) as model tools named ``ui_<NAME>``."""
    return [
        {
            "type": "function",
            "function": {
                "name": f"{CLIENT_TOOL_PREFIX}{action['name']}",
                "description": f"Change the user's screen in the app: {action['description']}",
                "parameters": action.get("parameters") or {"type": "object", "properties": {}},
            },
        }
        for action in actions
    ]


def screen_first_instructions() -> str:
    return (
        "The ui_* tools change what the user already sees in the app (for example filter a table "
        "that is on screen). When one of them can show what the user asked for, use it instead of "
        "present_ui; use present_ui only when nothing on screen fits. After a ui_* tool, say in "
        "one sentence what changed on screen, using its result (e.g. how many rows are shown). If "
        "it did not apply, fall back to present_ui. When the user asks to go to, open or show a "
        "page, screen or record of the app, call the matching ui_* navigation or open tool instead "
        "of describing where it is. Forms: to create or change a record, use the canvas form "
        "(present_ui form or a proposal) unless the user asks to open or fill the app's own page "
        "or form, or a ui_PAGE_FORM_* tool for it is already available. In that case open the "
        "page first if needed (its forms then appear as ui_PAGE_FORM_* tools in your next step) "
        "and fill it with that tool. A ui_PAGE_FORM_* tool never submits: tell the user to "
        "review the form and submit it themselves."
    )


def default_screen_formatter(state: dict[str, Any]) -> str | None:
    if not state:
        return None
    text = json.dumps(state, default=str)[:_MAX_SCREEN_STATE_CHARS]
    return f"What the user currently sees (app state): {text}"


class ToolUsingAgent(AgentAdapter):
    def __init__(
        self,
        model_router: ModelRouter,
        *,
        system_prompt: str,
        registry: ToolRegistry,
        instructions: str = "",
        screen_formatter: ScreenFormatter | None = default_screen_formatter,
        token_filter: TokenFilter | None = None,
        max_rounds: int = MAX_MODEL_TOOL_ROUNDS,
        allow_proposals: bool = True,
    ) -> None:
        """``allow_proposals=False`` keeps side-effecting tools away from the model entirely (for
        custom agents that run their own approval flow)."""
        self._model_router = model_router
        self._system_prompt = system_prompt
        self._instructions = instructions
        self._screen_formatter = screen_formatter
        self._token_filter = token_filter
        self._max_rounds = max_rounds
        self._registry = registry
        self.model_tools = model_tools_from_registry(registry)
        self.model_tool_names = frozenset(tool["function"]["name"] for tool in self.model_tools)
        self._allow_proposals = allow_proposals
        self.proposal_tools = proposal_tools_from_registry(registry) if allow_proposals else []
        self.proposal_tool_names = frozenset(t["function"]["name"] for t in self.proposal_tools)
        # Voice latency: when the model already said its sentence next to display-only calls
        # (present_ui, fill_form, screen actions) and they all worked, end the turn instead of
        # asking the model again just for the reply.
        self._end_after_display = os.environ.get("RELAY_END_TURN_AFTER_DISPLAY", "").lower() in ("1", "true", "yes")

    async def on_turn(self, session_id: str, *, context: dict[str, Any]) -> list[RelayEvent]:
        async for _token in self.stream_turn(session_id, context=context):
            pass
        return []

    async def stream_turn(self, session_id: str, *, context: dict[str, Any]) -> AsyncIterator[str]:
        async for token in self.stream_model_turn(session_id, context):
            yield token

    async def stream_model_turn(
        self,
        session_id: str,
        context: dict[str, Any],
        *,
        extra_system: Sequence[str] = (),
    ) -> AsyncIterator[str]:
        """Model turn with up to ``max_rounds`` of tool calls; yields spoken/text tokens."""
        run_tool = context.get("run_tool")
        request_action = context.get("request_action")
        request_approval = context.get("request_hitl_approval")
        request_action_result = context.get("request_action_result")
        record_usage = context.get("record_model_usage")
        client_actions = (context.get("client_actions") or []) if request_action_result else []
        client_tools = {
            f"{CLIENT_TOOL_PREFIX}{action['name']}": action["name"] for action in client_actions
        }
        open_forms = (context.get("open_forms") or []) if request_action_result else []
        messages: list[dict[str, Any]] = [{"role": "system", "content": self._system_prompt}]
        if self._screen_formatter is not None:
            screen = self._screen_formatter(_screen_state(context))
            if screen:
                messages.append({"role": "system", "content": screen})
        messages.extend({"role": "system", "content": text} for text in extra_system if text)
        tools: list[dict[str, Any]] | None = None
        proposals_enabled = bool(self.proposal_tools) and request_approval is not None
        if request_action is not None:
            # present_ui and app screen actions need only the client; data tools need run_tool.
            tools = [present_ui_tool(), *(self.model_tools if run_tool is not None else [])]
            canvas = canvas_instructions()
            if proposals_enabled:
                tools.extend(self.proposal_tools)
                canvas = f"{canvas} {approval_instructions()}"
            if client_tools:
                tools.extend(client_action_tools(client_actions))
                canvas = f"{canvas} {screen_first_instructions()}"
            if open_forms:
                tools.append(fill_form_tool(open_forms))
                canvas = f"{canvas} {fill_form_instructions(open_forms)}"
            if self._end_after_display:
                canvas = (
                    f"{canvas} When you call present_ui, fill_form or a screen action, write your "
                    "one-sentence reply in the same message as that call, unless you still need "
                    "to look something up afterwards."
                )
            if self._instructions:
                canvas = f"{canvas} {self._instructions}"
            messages.append({"role": "system", "content": canvas})
        for item in context.get("messages", []):
            messages.append({"role": item["role"], "content": item["content"]})

        provider = self._model_router.get_provider()
        live_client_actions = context.get("live_client_actions") if request_action_result else None
        for _round in range(self._max_rounds):
            if _round and tools is not None and live_client_actions is not None:
                # A screen action may have changed the screen (another page, a form opened): offer
                # the actions the app advertises now.
                current = live_client_actions()
                if current != client_actions:
                    if current and not client_actions:
                        messages.append({"role": "system", "content": screen_first_instructions()})
                    client_actions = current
                    client_tools = {f"{CLIENT_TOOL_PREFIX}{action['name']}": action["name"] for action in current}
                    tools = [
                        tool for tool in tools if not tool["function"]["name"].startswith(CLIENT_TOOL_PREFIX)
                    ] + client_action_tools(current)
            calls: list[dict[str, str]] = []

            async def _raw_tokens() -> AsyncIterator[str]:
                async for chunk in provider.stream_completion(
                    session_id, messages=messages, tools=tools
                ):
                    if chunk.get("type") == "tool_calls":
                        calls.extend(chunk.get("calls") or [])
                        continue
                    if chunk.get("type") == "usage":
                        if record_usage is not None:
                            await record_usage(chunk)
                        continue
                    token = str(chunk.get("text", ""))
                    if token:
                        yield token

            stream = _raw_tokens()
            if self._token_filter is not None:
                stream = self._token_filter(stream)
            spoken: list[str] = []
            async for token in stream:
                spoken.append(token)
                yield token
            if not calls:
                return
            messages.append(
                {
                    "role": "assistant",
                    "content": "".join(spoken) or None,
                    "tool_calls": [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {"name": call["name"], "arguments": call["arguments"]},
                        }
                        for call in calls
                    ],
                }
            )
            # Read-only tools are independent, so a multi-call round runs concurrently.
            results = await asyncio.gather(
                *(
                    run_model_tool_call(
                        call,
                        run_tool=run_tool,
                        request_action=request_action,
                        allowed_tools=self.model_tool_names,
                        proposal_tools=self.proposal_tool_names if proposals_enabled else frozenset(),
                        # No registry → no proposals and no tool-bound (auto-saving) forms.
                        registry=self._registry if self._allow_proposals else None,
                        request_approval=request_approval,
                        client_tools=client_tools,
                        request_action_result=request_action_result,
                        open_forms=open_forms,
                    )
                    for call in calls
                )
            )
            for call, result in zip(calls, results):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(result, default=str)[:MAX_TOOL_RESULT_CHARS],
                    }
                )
            if (
                self._end_after_display
                and "".join(spoken).strip()
                and all(_display_call_succeeded(call, result, client_tools) for call, result in zip(calls, results))
            ):
                return


async def run_model_tool_call(
    call: dict[str, str],
    *,
    run_tool: Any,
    request_action: Any,
    allowed_tools: frozenset[str],
    proposal_tools: frozenset[str] = frozenset(),
    registry: ToolRegistry | None = None,
    request_approval: Any = None,
    client_tools: dict[str, str] | None = None,
    request_action_result: Any = None,
    open_forms: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute one model tool call; errors go back to the model instead of raising.

    Calls to ``proposal_tools`` never execute here: they are validated and turned into an
    approval request; the runtime runs the tool only after the user grants it.
    """
    try:
        arguments = json.loads(call.get("arguments") or "{}")
    except json.JSONDecodeError:
        return {"error": "arguments_not_json"}
    if not isinstance(arguments, dict):
        return {"error": "arguments_not_object"}
    name = call.get("name", "")
    if name == PRESENT_UI_TOOL_NAME:
        if registry is not None:
            form_error = bind_tool_forms(arguments, registry)
            if form_error:
                return {"error": form_error}
        else:
            for surface in arguments.get("surfaces") or []:
                if isinstance(surface, dict):
                    surface.pop("submit_tool", None)  # writes not allowed for this agent
        params = sanitize_present_ui_arguments(arguments)
        if not params["surfaces"]:
            return {"error": "no_valid_surfaces", "allowed_kinds": list(SURFACE_KINDS)}
        await request_action(PRESENT_UI_ACTION, params)
        return {"shown": len(params["surfaces"])}
    if name == FILL_FORM_TOOL_NAME and open_forms and request_action_result is not None:
        params, report = sanitize_form_fill(arguments, open_forms)
        if params is None:
            return report
        outcome, result = await request_action_result(FILL_FORM_ACTION, params)
        return {"outcome": outcome, **report, **result, "note": "Nothing is saved until the user submits the form."}
    if client_tools and name in client_tools and request_action_result is not None:
        outcome, result = await request_action_result(client_tools[name], arguments)
        return {"outcome": outcome, **result}
    if name in proposal_tools and request_approval is not None:
        summary = str(arguments.pop("summary", "") or "").strip()
        if registry is not None:
            invalid = registry.validate_input(name, arguments)
            if invalid:
                return {"error": invalid}
        approval_id = str(uuid4())
        await request_approval(
            name,
            arguments,
            summary=summary or f"{name} {json.dumps(arguments, default=str)}",
            approval_id=approval_id,
            followup=True,
        )
        return {
            "status": "awaiting_user_approval",
            "approval_id": approval_id,
            "note": "Nothing has changed yet. The user sees an approval dialog for this change.",
        }
    if name not in allowed_tools:
        return {"error": f"tool_not_available:{name}"}
    return await run_tool(name, arguments)


def _display_call_succeeded(call: dict[str, str], result: dict[str, Any], client_tools: dict[str, str]) -> bool:
    """A call that only changed the screen and worked, so the model has nothing left to read."""
    name = call.get("name", "")
    if result.get("error"):
        return False
    if name == PRESENT_UI_TOOL_NAME:
        return True
    if name == FILL_FORM_TOOL_NAME or name in client_tools:
        return result.get("outcome") == "applied" and not result.get("rejected")
    return False


def _screen_state(context: dict[str, Any]) -> dict[str, Any]:
    live = context.get("live_state")
    if callable(live):
        return dict((live() or {}).get("state") or {})
    return dict((context.get("state") or {}).get("state") or {})
