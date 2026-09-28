"""Mortgage reference agent: read tools + typed UI actions (Phase 5–6)."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from relay_protocol import EventType, RelayEvent, RelayEventMetadata
from relay_runtime.model_router import ModelRouter
from relay_runtime.ports.agent import AgentAdapter

from relay_mortgage_agent.response_guardrails import guard_stream


class MortgageServicingAgent(AgentAdapter):
    def __init__(
        self,
        model_router: ModelRouter,
        *,
        system_prompt: str | None = None,
    ) -> None:
        self._model_router = model_router
        self._system_prompt = system_prompt or _default_system_prompt()

    async def on_turn(
        self,
        session_id: str,
        *,
        context: dict[str, Any],
    ) -> list[Any]:
        async for _token in self.stream_turn(session_id, context=context):
            pass
        return []

    async def stream_turn(
        self,
        session_id: str,
        *,
        context: dict[str, Any],
    ) -> AsyncIterator[str]:
        user_text = str(context.get("user_text", ""))
        request_action = context.get("request_action")
        run_tool = context.get("run_tool")
        run_tools_parallel = context.get("run_tools_parallel")
        lower = user_text.lower()
        mortgage_id = _mortgage_id_from_context(context)

        if _is_customer_search_intent(lower):
            query = _extract_search_query(user_text)
            if run_tool is None:
                search = {"customers": []}
            else:
                search = await run_tool("search_customer", {"query": query})
            customers = list(search.get("customers") or [])
            count = len(customers)
            summary = (
                f"I found {count} customer match{'es' if count != 1 else ''} for {query!r}."
                if count
                else f"I couldn't find a customer matching {query!r}."
            )
            if count and request_action is not None:
                await request_action(
                    "SHOW_SEARCH_RESULTS",
                    {"query": query, "customers": customers},
                )
                target = _pick_mortgage_id(customers, preferred="MORT-2931")
                if target:
                    summary += f" Opening mortgage {target} on your screen now."
                    await request_action(
                        "OPEN_ENTITY",
                        {"entity_type": "mortgage", "id": target},
                    )
            for token in _chunk_text(summary):
                yield token
            return

        if "open" in lower and "mort-2931" in lower.replace(" ", ""):
            if request_action is not None:
                await request_action(
                    "OPEN_ENTITY",
                    {"entity_type": "mortgage", "id": "MORT-2931"},
                )
            text = "Opening mortgage MORT-2931 on your screen."
            for token in _chunk_text(text):
                yield token
            return

        if _is_emi_explanation_intent(lower):
            explanation = _long_emi_explanation(mortgage_id)
            for token in _chunk_text(explanation, size=12):
                yield token
            return

        if _is_rate_history_intent(lower) and run_tool is not None:
            rates_result = await run_tool(
                "get_rate_history",
                {"mortgage_id": mortgage_id},
            )
            summary = _summarize_rate_history_only(mortgage_id, rates_result)
            if request_action is not None and rates_result.get("rates"):
                await request_action(
                    "SHOW_RATE_HISTORY",
                    {"mortgage_id": mortgage_id, "rates": rates_result.get("rates")},
                )
            for token in _chunk_text(summary):
                yield token
            return

        if _is_parallel_investigation_intent(lower) and run_tools_parallel is not None:
            for token in _chunk_text(
                "I'm checking recent payments and rate history in parallel — I'll update you as each finishes."
            ):
                yield token
            results = await run_tools_parallel(
                [
                    {"tool_name": "get_payments", "arguments": {"mortgage_id": mortgage_id, "months": 3}},
                    {"tool_name": "get_rate_history", "arguments": {"mortgage_id": mortgage_id}},
                ],
                activity_label="Payment and rate investigation",
            )
            payments_result = results[0] if results else {}
            rates_result = results[1] if len(results) > 1 else {}
            summary = _summarize_parallel_investigation(
                mortgage_id, payments_result, rates_result
            )
            if request_action is not None and rates_result.get("rates"):
                await request_action(
                    "SHOW_RATE_HISTORY",
                    {"mortgage_id": mortgage_id, "rates": rates_result.get("rates")},
                )
            for token in _chunk_text(summary):
                yield token
            return

        if _is_prepare_correction_intent(lower) and run_tool is not None:
            slow_ms = 5000 if "slow" in lower else (1500 if "race" in lower else 0)
            placeholder: dict[str, Any] = {
                "mortgage_id": mortgage_id,
                "effective_date": "2025-01-01",
                "status": "draft",
                "proposed_rate": 6.125,
                "current_rate": 6.125,
                "current_emi": 2847.5,
                "projected_emi": 2847.5,
                "estimated_emi_delta": 0.0,
            }
            if request_action is not None:
                await request_action(
                    "SHOW_CORRECTION_DRAFT",
                    {"mortgage_id": mortgage_id, "draft": placeholder},
                    wait=("slow" in lower),
                )
            for token in _chunk_text("Preparing a draft correction — I'll show the numbers on your screen."):
                yield token
            live_version = context.get("live_state_version")
            version_before_tool = (
                int(live_version()) if callable(live_version) else int(live_version or 0)
            )
            draft_result = await run_tool(
                "prepare_correction",
                {
                    "mortgage_id": mortgage_id,
                    "effective_date": "2025-01-01",
                    "_slow_ms": slow_ms,
                },
            )
            draft = draft_result.get("draft") or placeholder
            await _sync_correction_draft_to_runtime(
                context,
                mortgage_id=mortgage_id,
                draft=draft,
                focus_draft_screen=True,
                pinned_based_on_version=version_before_tool,
            )
            summary = _summarize_correction_draft(mortgage_id, draft)
            for token in _chunk_text(summary):
                yield token
            return

        if _is_active_correction_draft(context) and _is_effective_date_query(lower):
            text = _describe_correction_effective_date(context, mortgage_id)
            for token in _chunk_text(text):
                yield token
            return

        effective_date = _resolve_correction_date_request(user_text, lower, context)
        if effective_date and _is_active_correction_draft(context):
            async for token in _apply_correction_effective_date(
                context,
                mortgage_id=mortgage_id,
                effective_date=effective_date,
            ):
                yield token
            return

        request_hitl = context.get("request_hitl_approval")
        if _is_active_correction_draft(context) and _is_submit_for_approval_intent(lower):
            draft = _draft_from_context(context)
            eff = str(draft.get("effective_date") or "2025-01-01")
            rate = float(draft.get("proposed_rate") or draft.get("current_rate") or 0.0)
            mid = str(draft.get("mortgage_id") or mortgage_id)
            summary = (
                f"Commit rate correction for {mid}: effective {eff}, "
                f"proposed rate {rate:.3f}%."
            )
            if request_hitl is not None:
                await request_hitl(
                    "commit_correction",
                    {
                        "mortgage_id": mid,
                        "effective_date": eff,
                        "proposed_rate": rate,
                    },
                    summary=summary,
                )
            text = (
                "I've sent this draft for your approval — use Approve in the dialog "
                "when you're ready to commit."
            )
            for token in _chunk_text(text):
                yield token
            return

        if _is_active_correction_draft(context) and _is_direct_commit_intent(lower) and run_tool is not None:
            draft = _draft_from_context(context)
            result = await run_tool(
                "commit_correction",
                {
                    "mortgage_id": mortgage_id,
                    "effective_date": str(draft.get("effective_date") or ""),
                    "proposed_rate": float(
                        draft.get("proposed_rate") or draft.get("current_rate") or 0.0
                    ),
                },
            )
            if result.get("error") == "side_effecting_blocked_until_hitl":
                text = (
                    "I can't commit without your explicit approval — "
                    "say Submit for approval and use Approve in the dialog."
                )
                for token in _chunk_text(text):
                    yield token
                return

        if _is_active_correction_draft(context) and _is_unresolved_draft_date_change(
            user_text, lower
        ):
            text = (
                "Which effective date should I set on the draft? "
                "You can say it like March first, twenty twenty-five, or 2025-03-01."
            )
            for token in _chunk_text(text):
                yield token
            return

        if _is_payment_history_intent(lower) and run_tool is not None:
            for token in _chunk_text("Pulling the last three months of payments — one moment."):
                yield token
            payments_result = await run_tool(
                "get_payments",
                {"mortgage_id": mortgage_id, "months": 3},
            )
            summary = _summarize_payments(mortgage_id, payments_result)
            for token in _chunk_text(summary):
                yield token
            return

        rate_answer = await _try_answer_rate_history_question(
            user_text, lower, context, mortgage_id=mortgage_id, run_tool=run_tool
        )
        if rate_answer:
            for token in _chunk_text(rate_answer):
                yield token
            return

        messages: list[dict[str, str]] = [{"role": "system", "content": self._system_prompt}]
        state_block = context.get("state") or {}
        semantic = state_block.get("state") or {}
        if semantic:
            messages.append(
                {
                    "role": "system",
                    "content": _format_screen_context_for_model(semantic, mortgage_id=mortgage_id),
                }
            )
        for item in context.get("messages", []):
            messages.append({"role": item["role"], "content": item["content"]})

        provider = self._model_router.get_provider()

        async def _raw_llm_tokens() -> AsyncIterator[str]:
            async for chunk in provider.stream_completion(session_id, messages=messages):
                token = str(chunk.get("text", ""))
                if token:
                    yield token

        async for token in guard_stream(_raw_llm_tokens()):
            yield token

    async def handle_runtime_event(
        self,
        session_id: str,
        *,
        event: RelayEvent,
        context: dict[str, Any],
    ) -> list[RelayEvent]:
        del session_id
        if event.type != EventType.STATE_CONFLICT:
            return []
        state_block = context.get("state") or {}
        semantic = state_block.get("state") or {}
        draft = semantic.get("correction_draft") or {}
        if not draft:
            return []
        mortgage_id = str(draft.get("mortgage_id") or _mortgage_id_from_context(context))
        effective_date = str(draft.get("effective_date") or "2025-01-01")
        proposed = draft.get("proposed_rate")
        try:
            from mortgage_tools_api import logic
        except ImportError:
            return []
        recalc = logic.recalculate_correction_draft(
            mortgage_id,
            effective_date=effective_date,
            proposed_rate=float(proposed) if proposed is not None else None,
        )
        new_draft = recalc.get("draft") or {}
        if not new_draft:
            return []
        based_on = int(state_block.get("state_version") or 0)
        meta = RelayEventMetadata(
            session_id=str(event.metadata.session_id),
            sequence=0,
            source="mortgage_agent",
            based_on_version=based_on,
            turn_id=event.metadata.turn_id,
        )
        patch = _draft_state_patch(new_draft, semantic_state=semantic, focus_draft_screen=False)
        return [
            RelayEvent(
                type=EventType.STATE_DELTA,
                metadata=meta,
                payload={"patch": patch, "based_on_version": based_on},
            )
        ]


async def _apply_correction_effective_date(
    context: dict[str, Any],
    *,
    mortgage_id: str,
    effective_date: str,
) -> AsyncIterator[str]:
    run_tool = context.get("run_tool")
    draft: dict[str, Any] = {}
    if run_tool is not None:
        recalc = await run_tool(
            "recalculate_correction_draft",
            {"mortgage_id": mortgage_id, "effective_date": effective_date},
        )
        draft = dict(recalc.get("draft") or {})
    if not draft:
        draft = {
            "mortgage_id": mortgage_id,
            "effective_date": effective_date,
            "status": "draft",
        }
    applied = await _sync_correction_draft_to_runtime(
        context,
        mortgage_id=mortgage_id,
        draft=draft,
        focus_draft_screen=True,
    )
    semantic = _semantic_state(context)
    on_screen = dict(semantic.get("correction_draft") or draft)
    eff = str(on_screen.get("effective_date") or effective_date)
    emi = float(on_screen.get("projected_emi") or draft.get("projected_emi") or 0)
    if applied and eff == effective_date:
        summary = (
            f"Updated the draft effective date to {eff} on your screen. "
            f"Projected EMI is ${emi:.2f}."
        )
    else:
        summary = (
            f"The draft on your screen still shows effective date {eff}. "
            f"Projected EMI is ${emi:.2f}."
        )
    for token in _chunk_text(summary):
        yield token


async def _sync_correction_draft_to_runtime(
    context: dict[str, Any],
    *,
    mortgage_id: str,
    draft: dict[str, Any],
    focus_draft_screen: bool,
    pinned_based_on_version: int | None = None,
) -> bool:
    apply_state_delta = context.get("apply_state_delta")
    request_action = context.get("request_action")
    live_version = context.get("live_state_version")

    def _current_version() -> int:
        if callable(live_version):
            return int(live_version())
        return int(live_version or 0)

    if apply_state_delta is not None and draft:
        semantic = (context.get("state") or {}).get("state") or {}
        patch = _draft_state_patch(
            draft,
            semantic_state=semantic,
            focus_draft_screen=focus_draft_screen,
        )
        based_on = (
            int(pinned_based_on_version)
            if pinned_based_on_version is not None
            else _current_version()
        )
        return await apply_state_delta(patch, based_on_version=based_on)

    if request_action is not None and draft:
        await request_action(
            "SHOW_CORRECTION_DRAFT",
            {"mortgage_id": mortgage_id, "draft": draft},
        )
        return True
    return False


def _semantic_state(context: dict[str, Any]) -> dict[str, Any]:
    live = context.get("live_state")
    if callable(live):
        return dict((live() or {}).get("state") or {})
    return dict((context.get("state") or {}).get("state") or {})


def _draft_state_patch(
    draft: dict[str, Any],
    *,
    semantic_state: dict[str, Any],
    focus_draft_screen: bool,
) -> list[dict[str, Any]]:
    patch: list[dict[str, Any]] = [{"key": "correction_draft", "value": draft}]
    if not focus_draft_screen:
        return patch
    if semantic_state.get("screen") == "rate_history":
        return patch
    patch.extend(
        [
            {"key": "workflow", "value": "correction_draft"},
            {"key": "screen", "value": "correction_draft"},
        ]
    )
    return patch


def _is_active_correction_draft(context: dict[str, Any]) -> bool:
    semantic = (context.get("state") or {}).get("state") or {}
    if semantic.get("correction_draft"):
        return True
    return semantic.get("workflow") == "correction_draft" or semantic.get("screen") == "correction_draft"


_MONTH_NAME_TO_NUM: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


def _resolve_correction_date_request(
    user_text: str,
    lower: str,
    context: dict[str, Any],
) -> str | None:
    if not _is_active_correction_draft(context):
        return None
    bare = _bare_correction_date_reply(user_text, lower)
    if bare:
        return bare
    if _mentions_draft_date_change(lower):
        direct = _parse_effective_date(user_text)
        if direct:
            return direct
        month_date = _parse_month_name_date(user_text, lower, context)
        if month_date:
            return month_date
    if _is_date_change_affirmation(lower):
        return _find_recent_correction_date(context, include_month_names=True)
    return None


def _mentions_draft_date_change(lower: str) -> bool:
    if _month_numbers_in_text(lower):
        return any(
            word in lower
            for word in ("change", "update", "set", "move", "switch", "make", "use", "not")
        )
    if "date" not in lower and "effective" not in lower:
        return False
    return any(
        word in lower
        for word in ("change", "update", "set", "move", "switch", "make", "use")
    )


def _month_numbers_in_text(lower: str) -> list[int]:
    found: list[tuple[int, int]] = []
    for name, num in _MONTH_NAME_TO_NUM.items():
        for match in re.finditer(rf"\b{re.escape(name)}\b", lower):
            found.append((match.start(), num))
    found.sort(key=lambda item: item[0])
    return [num for _, num in found]


def _negated_month_numbers(lower: str) -> set[int]:
    negated: set[int] = set()
    for name, num in _MONTH_NAME_TO_NUM.items():
        if re.search(rf"\bnot\s+{re.escape(name)}\b", lower):
            negated.add(num)
    return negated


def _parse_month_name_date(text: str, lower: str, context: dict[str, Any]) -> str | None:
    months = _month_numbers_in_text(lower)
    if not months:
        return None
    negated = _negated_month_numbers(lower)
    candidates = [num for num in months if num not in negated]
    if not candidates:
        return None
    month_num = candidates[-1]
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        year = int(year_match.group(1))
    else:
        semantic = (context.get("state") or {}).get("state") or {}
        draft = semantic.get("correction_draft") or {}
        eff = str(draft.get("effective_date") or "2025-01-01")
        year = int(eff[:4]) if len(eff) >= 4 else 2025
    return f"{year:04d}-{month_num:02d}-01"


def _is_effective_date_query(lower: str) -> bool:
    if any(word in lower for word in ("change", "update", "set", "move", "switch", "make")):
        return False
    if "effective date" in lower:
        return True
    if "current date" in lower or "what date" in lower:
        return True
    if "what" in lower and "date" in lower:
        return True
    return lower.strip() in {"what's the date?", "whats the date?"}


def _bare_correction_date_reply(user_text: str, lower: str) -> str | None:
    parsed = _parse_effective_date(user_text)
    if not parsed:
        return None
    scratch = user_text
    scratch = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", scratch)
    scratch = re.sub(r"\b\d{1,2}/\d{1,2}/\d{4}\b", " ", scratch)
    leftovers = re.sub(r"[^a-z]+", "", scratch.lower())
    if leftovers in {"", "ok", "okay", "yes", "yeah", "yep", "sure", "please", "thanks", "use", "that"}:
        return parsed
    return None


def _is_unresolved_draft_date_change(user_text: str, lower: str) -> bool:
    if not _mentions_draft_date_change(lower):
        return False
    if _parse_effective_date(user_text):
        return False
    if _month_numbers_in_text(lower):
        return False
    return True


def _describe_correction_effective_date(context: dict[str, Any], mortgage_id: str) -> str:
    semantic = (context.get("state") or {}).get("state") or {}
    draft = semantic.get("correction_draft") or {}
    eff = str(draft.get("effective_date") or "2025-01-01")
    projected = draft.get("projected_emi")
    emi_part = (
        f" Projected EMI is ${float(projected):.2f}."
        if projected is not None
        else ""
    )
    return f"The correction draft for {mortgage_id} shows effective date {eff}.{emi_part}"


def _format_screen_context_for_model(semantic: dict[str, Any], *, mortgage_id: str) -> str:
    screen = str(semantic.get("screen") or "home")
    workflow = str(semantic.get("workflow") or "")
    selected = semantic.get("selected_entity") or {}
    entity_id = str(selected.get("id") or mortgage_id)
    lines = [f"The user is viewing mortgage {entity_id}."]
    if workflow:
        lines.append(f"Workflow: {workflow.replace('_', ' ')}.")
    if screen == "correction_draft":
        draft = semantic.get("correction_draft") or {}
        eff = draft.get("effective_date")
        projected = draft.get("projected_emi")
        if eff:
            lines.append(f"Draft effective date on screen: {eff}.")
        if projected is not None:
            lines.append(f"Draft projected EMI on screen: ${float(projected):.2f}.")
    elif screen == "mortgage_case":
        case = semantic.get("case_summary") or {}
        name = case.get("customer_name")
        if name:
            lines.append(f"Customer on screen: {name}.")
    elif screen == "rate_history":
        lines.append(_format_rate_history_context_line(semantic))
    lines.append(
        "Answer in natural language only; do not mention JSON, screen keys, or internal systems."
    )
    return " ".join(lines)


def _is_date_change_affirmation(lower: str) -> bool:
    stripped = lower.strip().strip(".!?")
    if stripped in {"yes", "yeah", "yep", "ok", "okay", "sure", "update", "do it", "go ahead"}:
        return True
    return stripped.startswith("yeah") and "update" in stripped


def _find_recent_correction_date(
    context: dict[str, Any],
    *,
    include_month_names: bool = False,
) -> str | None:
    messages = list(context.get("messages") or [])
    for item in reversed(messages):
        if item.get("role") != "user":
            continue
        content = str(item.get("content", ""))
        parsed = _parse_effective_date(content)
        if parsed:
            return parsed
        if include_month_names:
            lower = content.lower()
            month_date = _parse_month_name_date(content, lower, context)
            if month_date:
                return month_date
    return None


def _parse_effective_date(text: str) -> str | None:
    iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if iso:
        return iso.group(0)
    slash = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", text)
    if slash:
        month, day, year = (int(slash.group(1)), int(slash.group(2)), int(slash.group(3)))
        if month > 12 and day <= 12:
            month, day = day, month
        return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def _mortgage_id_from_context(context: dict[str, Any]) -> str:
    state = (context.get("state") or {}).get("state") or {}
    selected = state.get("selected_entity") or {}
    if str(selected.get("type")) == "mortgage" and selected.get("id"):
        return str(selected["id"])
    match = re.search(r"mort-\d+", str(context.get("user_text", "")), flags=re.IGNORECASE)
    if match:
        return match.group(0).upper()
    return "MORT-2931"


def _is_emi_explanation_intent(lower: str) -> bool:
    if "emi" not in lower:
        return False
    return any(
        word in lower
        for word in ("explain", "why", "increase", "increased", "investigate", "happened")
    )


def _long_emi_explanation(mortgage_id: str) -> str:
    paragraphs = [
        (
            f"For {mortgage_id}, your equated monthly installment reflects principal, interest, "
            "escrow, and any servicing adjustments applied on the billing date."
        ),
        (
            "When the note rate steps up after a rate-change effective date, the interest portion "
            "of each payment rises even if the calendar month looks similar on your statement."
        ),
        (
            "Over the last three billing cycles you may also see small escrow true-ups that "
            "temporarily increase the total amount due until the escrow analysis completes."
        ),
        (
            "I'll walk through each component: first the rate change, then payment history, then "
            "how we project the next cycle so you can compare against prior months."
        ),
    ]
    return " ".join(paragraphs)


def _format_rate_history_context_line(semantic: dict[str, Any]) -> str:
    rates = list(semantic.get("rate_history") or [])
    if not rates:
        return "Rate history screen is open but no rows are loaded yet."
    parts: list[str] = []
    for row in rates:
        eff = row.get("effective_date")
        rate = float(row.get("rate") or 0)
        reason = str(row.get("reason") or "").replace("_", " ")
        parts.append(f"{eff} {rate:.3f}% ({reason})".strip())
    return (
        "Rate history on screen (authoritative — cite these when asked): "
        + "; ".join(parts)
        + "."
    )


async def _load_rate_history_rows(
    context: dict[str, Any],
    *,
    mortgage_id: str,
    run_tool: Any | None,
) -> list[dict[str, Any]]:
    semantic = _semantic_state(context)
    rates = list(semantic.get("rate_history") or [])
    if rates or run_tool is None:
        return rates
    result = await run_tool("get_rate_history", {"mortgage_id": mortgage_id})
    return list(result.get("rates") or [])


async def _try_answer_rate_history_question(
    user_text: str,
    lower: str,
    context: dict[str, Any],
    *,
    mortgage_id: str,
    run_tool: Any | None,
) -> str | None:
    """Deterministic answers from on-screen (or tool) rate rows — avoids LLM denying visible data."""
    semantic = _semantic_state(context)
    rates = await _load_rate_history_rows(
        context, mortgage_id=mortgage_id, run_tool=run_tool
    )
    if not rates:
        return None

    on_rate_view = semantic.get("screen") == "rate_history" or bool(semantic.get("rate_history"))
    if not on_rate_view and not _mentions_rate_fact_question(lower):
        return None

    if "origination" in lower:
        for row in rates:
            reason = str(row.get("reason") or "").lower()
            if reason == "origination" or "origin" in reason:
                return (
                    f"The origination rate was {float(row.get('rate', 0)):.3f}% "
                    f"effective {row.get('effective_date')}."
                )
        first = rates[0]
        return (
            f"The earliest rate on file is {float(first.get('rate', 0)):.3f}% "
            f"effective {first.get('effective_date')} ({str(first.get('reason') or '').replace('_', ' ')})."
        )

    year_match = re.search(r"\b(20\d{2})\b", user_text) or re.search(
        r"\bin\s+(20\d{2})\b", lower
    )
    if year_match:
        year = year_match.group(1)
        matches = [
            row
            for row in rates
            if str(row.get("effective_date") or "").startswith(f"{year}-")
        ]
        if matches:
            row = matches[-1]
            reason = str(row.get("reason") or "").replace("_", " ")
            return (
                f"In {year}, the rate on file is {float(row.get('rate', 0)):.3f}% "
                f"effective {row.get('effective_date')} ({reason})."
            )
        return (
            f"I don't see a rate change effective in {year} on this history — "
            f"the listed dates are {', '.join(str(r.get('effective_date')) for r in rates)}."
        )

    if _mentions_rate_fact_question(lower) and any(
        word in lower for word in ("detail", "details", "history", "timeline", "see")
    ):
        return _format_rate_history_context_line(semantic).replace(
            "Rate history on screen (authoritative — cite these when asked): ",
            "Here's what's on the rate history: ",
        )

    return None


def _mentions_rate_fact_question(lower: str) -> bool:
    if "rate" not in lower and "origination" not in lower:
        return False
    return any(
        word in lower
        for word in (
            "origination",
            "what was",
            "what's",
            "whats",
            "tell me",
            "in 202",
            "history",
            "detail",
            "percentage",
            "percent",
        )
    )


def _summarize_rate_history_only(mortgage_id: str, rates_result: dict[str, Any]) -> str:
    rates = list(rates_result.get("rates") or [])
    if not rates:
        return f"I couldn't load rate history for {mortgage_id}."
    latest = rates[-1]
    return (
        f"Opening rate history for {mortgage_id}: {len(rates)} changes on file; "
        f"current rate {float(latest.get('rate', 0)):.3f}% effective {latest.get('effective_date')}."
    )


def _draft_from_context(context: dict[str, Any]) -> dict[str, Any]:
    live = context.get("live_state")
    state_blob = live() if callable(live) else context.get("state") or {}
    if isinstance(state_blob, dict) and "state" in state_blob:
        inner = state_blob.get("state")
        if isinstance(inner, dict):
            state_blob = inner
    draft = state_blob.get("correction_draft") if isinstance(state_blob, dict) else None
    return dict(draft) if isinstance(draft, dict) else {}


def _is_direct_commit_intent(lower: str) -> bool:
    if "approval" in lower or "submit" in lower:
        return False
    if "commit" not in lower:
        return False
    return "correction" in lower or "draft" in lower or "now" in lower


def _is_submit_for_approval_intent(lower: str) -> bool:
    if "approval" in lower and "submit" in lower:
        return True
    if "ready for review" in lower:
        return True
    if "submit for approval" in lower:
        return True
    if "request approval" in lower:
        return True
    return "approve" in lower and ("commit" in lower or "correction" in lower or "draft" in lower)


def _is_prepare_correction_intent(lower: str) -> bool:
    if "correction" not in lower and "adjustment" not in lower:
        return False
    return any(word in lower for word in ("prepare", "draft", "rate", "create", "build"))


def _summarize_correction_draft(mortgage_id: str, draft: dict[str, Any]) -> str:
    if not draft:
        return f"I couldn't build a correction draft for {mortgage_id}."
    eff = draft.get("effective_date")
    projected = draft.get("projected_emi")
    delta = draft.get("estimated_emi_delta")
    return (
        f"Draft correction for {mortgage_id}: effective {eff}, "
        f"projected EMI ${float(projected or 0):.2f} (delta ${float(delta or 0):.2f}). "
        "You can edit the effective date before we commit."
    )


def _is_payment_compare_intent(lower: str) -> bool:
    if "payment" not in lower:
        return False
    return any(word in lower for word in ("compare", "last", "month", "three", "3"))


def _is_payment_history_intent(lower: str) -> bool:
    if "payment histor" in lower:
        return True
    return _is_payment_compare_intent(lower)


def _is_rate_history_intent(lower: str) -> bool:
    if "rate histor" in lower:
        return True
    if "rate" not in lower:
        return False
    return any(
        word in lower
        for word in ("fetch", "show", "open", "check", "pull", "get", "load", "review")
    ) and any(word in lower for word in ("history", "histories", "changes"))


def _is_parallel_investigation_intent(lower: str) -> bool:
    if "rate" in lower and "payment" in lower:
        return True
    if "investigate" in lower and ("rate" in lower or "payment" in lower):
        return True
    if _is_rate_history_intent(lower):
        return True
    return False


def _summarize_payments(mortgage_id: str, result: dict[str, Any]) -> str:
    payments = list(result.get("payments") or [])
    if not payments:
        return f"I couldn't find payment history for {mortgage_id}."
    lines = [
        f"For {mortgage_id}, here are the last {len(payments)} payments:",
    ]
    for row in payments:
        lines.append(
            f"- {row.get('month')}: ${float(row.get('amount', 0)):.2f} ({row.get('status', 'unknown')})"
        )
    amounts = [float(row.get("amount") or 0) for row in payments]
    if len(amounts) >= 2 and len(set(amounts)) > 1:
        lines.append(
            f"The most recent amount differs from earlier months (${amounts[0]:.2f} vs ${amounts[-1]:.2f})."
        )
    else:
        lines.append("Amounts are consistent across these months.")
    return " ".join(lines)


def _summarize_parallel_investigation(
    mortgage_id: str,
    payments_result: dict[str, Any],
    rates_result: dict[str, Any],
) -> str:
    payment_part = _summarize_payments(mortgage_id, payments_result)
    rates = list(rates_result.get("rates") or [])
    if not rates:
        return payment_part
    latest = rates[-1]
    rate_part = (
        f"Rate history shows {len(rates)} changes; the current rate is "
        f"{float(latest.get('rate', 0)):.3f}% effective {latest.get('effective_date')}."
    )
    return f"{payment_part} {rate_part}"


def _is_customer_search_intent(lower: str) -> bool:
    if "rajesh" in lower:
        return True
    if "find" in lower and ("customer" in lower or "sharma" in lower):
        return True
    if lower.strip().startswith("search "):
        return True
    return False


def _extract_search_query(text: str) -> str:
    if "rajesh" in text.lower():
        return "Rajesh Sharma"
    match = re.search(r"search(?:\s+for)?\s+(.+)", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip(" ?.")
    match = re.search(r"find\s+(.+)", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip(" ?.")
    return text.strip()


def _pick_mortgage_id(customers: list[dict[str, Any]], *, preferred: str) -> str | None:
    for customer in customers:
        for mortgage in customer.get("mortgages") or []:
            if str(mortgage.get("id")) == preferred:
                return preferred
        mortgages = customer.get("mortgages") or []
        if mortgages:
            return str(mortgages[0].get("id"))
    return None


def _chunk_text(text: str, size: int = 16) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def _default_system_prompt() -> str:
    bundled = Path(__file__).resolve().parent / "system_prompt.txt"
    if bundled.is_file():
        return bundled.read_text(encoding="utf-8").strip()
    return "You are the mortgage servicing reference assistant."
