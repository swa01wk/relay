# User-facing guard rails & response sanitization

**Status:** Draft for review — mortgage POC implemented; platform placement TBD  
**Last updated:** 2026-09-25  
**Related:** [UAT-006](./UAT_VOICE_SCRIPT.md#uat-006) · Phase 8 draft/state · Phase 11 hardening

This document describes **what we built**, **why**, **how it behaves** (including streaming pitfalls), and **where to apply it next** so the team can review before promoting patterns into `runtime/` or other agents.

---

## 1. Problem statement

During voice/text UAT on the correction-draft flow, the assistant **leaked Relay implementation details** and **misrepresented outcomes**:

| Symptom | User impact | Typical cause |
|---------|-------------|---------------|
| “I can’t sync the UI / routed handler will apply it” | Breaks the “colleague at the same desk” demo; exposes architecture | LLM fallback when keyword routing missed |
| “I’m updating your screen to March…” while the date field stays January | Loss of trust; worse than silence | LLM-only reply without `run_tool` + `apply_state_delta` / actions |
| Quoting `screen`, `workflow`, raw state blobs | Reads like a debug console | System message contained full JSON state + tool dumps |
| `withthat`, `don'thave` (concatenated words) | Broken TTS/transcript | Streaming sanitizer called `.strip()` on every emitted chunk |

**Goal:** End users (and UAT operators acting as agents) should only hear **business language** and see **UI truth**. Internal vocabulary belongs in logs, traces, and dev-only UI—not in assistant text or speech.

**Non-goal (this pass):** Hiding the mortgage frontend **“Shared state (RP)”** debug panel. That is a **developer affordance**, not assistant output. Guard rails here target **agent-generated** text (and the **prompt/context** that shapes it).

---

## 2. Design principle: defense in depth

Use multiple layers. Relying on only prompts or only regex fails under STT garble and model creativity.

```text
User utterance
    │
    ▼
┌───────────────────────────────────────┐
│ Layer A — Deterministic routing       │  Prefer tools + actions + state sync;
│ (keyword / state-aware handlers)      │  fixed user-facing copy; no LLM.
└───────────────────────────────────────┘
    │ miss
    ▼
┌───────────────────────────────────────┐
│ Layer B — Prompt & context shaping    │  System rules; narrated screen context
│                                       │  (not raw JSON); no tool-result dumps.
└───────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────┐
│ Layer C — Output sanitization         │  Regex redaction on LLM stream only;
│ (streaming-safe)                      │  deterministic paths bypass sanitizer.
└───────────────────────────────────────┘
    │
    ▼
Transcript + TTS
```

**Strategic rule:** **Layer A > B > C.** Sanitization is a **safety net**, not a substitute for routing state-changing intents off the LLM.

---

## 3. Current implementation (mortgage reference agent)

All paths below live under `examples/mortgage-servicing/agent/` unless noted.

### 3.1 Layer A — Deterministic routing (excerpt)

`MortgageServicingAgent.stream_turn` handles high-value demo intents **before** the model is called:

| Intent area | Examples | Mechanism |
|-------------|----------|-----------|
| Customer search | “Find Rajesh Sharma”, bare “Rajesh Sharma” | `search_customer` + `SHOW_SEARCH_RESULTS` / `OPEN_ENTITY` |
| Rate history | “rate history”, “rate histories”, fetch/show rate | `get_rate_history` + `SHOW_RATE_HISTORY` |
| Payments | “payment history”, “compare last 3 months” | `get_payments` |
| Correction draft | prepare correction; month names; `03/01/2025`; affirmations | `recalculate_correction_draft`, `apply_state_delta`, `SHOW_CORRECTION_DRAFT` |
| Draft Q&A | “What’s the effective date?” | Read from `context.state`, fixed reply |

**State-changing draft dates** must never be “LLM-only done.” Routed path: tool recalc → `_sync_correction_draft_to_runtime` → user-facing confirmation string from `_apply_correction_effective_date`.

### 3.2 Layer B — Prompt & context

| Artifact | Role |
|----------|------|
| `system_prompt.txt` | User-facing persona; explicit ban on runtime/handler/STATE_* vocabulary; instructs not to claim inability to update the screen on draft flows. |
| `_format_screen_context_for_model()` | Converts semantic UI state into short prose (“Draft effective date on screen: …”) instead of `Current UI state: {…}`. |
| Removed from LLM messages | Raw `tool_results` blob (was encouraging “I don’t have tool X visible”). |

Deterministic branches use hand-authored strings (`_chunk_text(...)`) and **do not** pass through Layer C.

### 3.3 Layer C — `response_guardrails.py`

| API | Use |
|-----|-----|
| `sanitize_assistant_text(text)` | Whole-string redaction (tests, optional batch use). **Strips** leading/trailing whitespace once. |
| `StreamingAssistantGuard` | Stateful buffer for token/chunk streams. |
| `guard_stream(async_iter)` | Wraps LLM `stream_completion` in `agent.py` only. |

**Redaction catalog (today):**

| Pattern class | Example leak | Action |
|---------------|--------------|--------|
| Sync disclaimers | “I haven’t actually synced the screen state…” | Remove sentence |
| Capability denial | “I can’t directly sync the UI state…” | Remove sentence |
| Handler jargon | “routed handler” | Remove phrase |
| RP / runtime identifiers | `STATE_SNAPSHOT`, `based_on_version`, `apply_state_delta` | Remove token |
| Soft rename | “UI state” → “screen”; “runtime state” → “the draft”; “state sync” → “update” | Replace |

**Streaming semantics (important for review):**

1. **Hold-back window:** Last `_HOLD_BACK` (96) characters stay in buffer so a forbidden phrase split across tokens can be matched before emit.
2. **No edge strip on partial emits:** Intermediate chunks use `_apply_redactions(..., strip_edges=False)` so spaces between model tokens are not eaten. **Only `flush()`** strips edges at end-of-turn.
3. **Regression:** `test_streaming_guard_keeps_spaces_between_chunks` in `runtime/tests/test_mortgage_agent_guardrails.py`.

**Not sanitized today:**

- Deterministic `_chunk_text` outputs (search summaries, tool summaries, draft confirmations).
- `speak_text` markdown stripping in `runtime/` (separate concern: TTS formatting).
- User messages, system errors, frontend conflict banner (“Stale agent update blocked…”) — intentional operator signal.

---

## 4. Verification

| Check | Location |
|-------|----------|
| Unit: redaction | `test_sanitize_strips_internal_sync_language` |
| Unit: streaming spaces | `test_streaming_guard_keeps_spaces_between_chunks` |
| Unit: draft date routing | `test_mortgage_agent_correction_date.py`, `test_mortgage_agent_guardrails.py` |
| Manual UAT | [UAT-006](./UAT_VOICE_SCRIPT.md#uat-006) script row **#11** |

**Pass criteria (UAT-006):** Draft date changes via voice/text; transcript/TTS contains **no** handler/sync/STATE_* leak; effective-date field matches spoken confirmation.

---

## 5. Known gaps & risks

| Gap | Risk | Mitigation direction |
|-----|------|----------------------|
| Regex catalog is POC-small | New leak phrases slip through until added | Eval set + periodic review of transcripts; expand patterns |
| Sanitizer only on LLM path | Deterministic copy could still use bad wording | Code review + shared phrasebook for routed strings |
| Follow-ups without keywords (“fetch it”) | Falls through to LLM | Extend routing with dialog state / last intent (Phase 11) |
| STT garble | Wrong branch or nonsense dates | Routing + clarify prompts; not fixable by sanitization alone |
| Hold-back latency | Up to ~96 chars delay before first emit on long LLM replies | Tune `_HOLD_BACK` vs pattern max length; or sanitize at turn end in non-latency-critical modes |
| Debug UI shows JSON state | Operators confuse with agent leak | Gate panel behind `NODE_ENV`/feature flag in frontend (separate task) |

---

## 6. Strategic placement options (review decisions)

Use this section in review meetings to decide **where** each layer should live long term.

### Option A — Keep agent-local (current)

| Pros | Cons |
|------|------|
| Matches [MODELS_AND_KEYS.md](./MODELS_AND_KEYS.md): business rules stay in `examples/` | Every new agent duplicates guard rails |
| Fast iteration for mortgage UAT | No central enforcement |

**Best for:** POC demo freeze, domain-specific routing.

### Option B — Shared library in `packages/python-sdk` or `relay-runtime` adjunct

Extract:

- `StreamingAssistantGuard` + pattern registry interface
- Optional `AgentAdapter` mixin: “wrap LLM stream with guard”

| Pros | Cons |
|------|------|
| One streaming implementation; tested once | Patterns may still be domain-specific |
| Agents supply their own pattern lists | Risk of pulling domain into core if patterns bundled |

**Best for:** Second reference agent, Phase 11 hardening.

### Option C — Runtime `AgentRuntime` hook

Apply sanitization in `runtime/src/relay_runtime/agent_runtime.py` for **all** `stream_turn` token emissions.

| Pros | Cons |
|------|------|
| Cannot forget to wrap LLM | Sanitizes deterministic tokens too unless adapter marks source |
| Central policy injection point | Violates “runtime domain-agnostic” if default patterns are mortgage-specific |

**Best for:** Platform product only if patterns are **configurable per project/agent** (gateway config or agent manifest).

### Option D — Gateway policy + observability (Phase 10)

Log **pre- and post-sanitizer** text when redaction fires; metric `guardrail_redaction_count`.

| Pros | Cons |
|------|------|
| Audit trail for leaks caught in prod | Does not prevent user hearing leak if regex misses |

**Recommended combo for post-POC:** **A → B** (shared streaming utility) + **D** (telemetry). Promote to **C** only with per-agent pattern config.

---

## 7. Review checklist (before widening scope)

Use when merging guard-rail changes or adding new intents:

- [ ] **State change:** Does this intent mutate UI/state? If yes, is it **fully routed** (tool/action/delta) with a fixed confirmation line?
- [ ] **LLM fallback:** If the model runs, is context **narrated** (Layer B) rather than raw JSON?
- [ ] **Prompt:** Does `system_prompt.txt` (or equivalent) forbid architecture apologies?
- [ ] **Sanitizer:** Is `guard_stream` applied only to **model** tokens, with **strip_edges=False** on partial chunks?
- [ ] **Tests:** New leak phrase → unit test in sanitizer; new route → agent test; demo step → UAT script row?
- [ ] **Voice:** Read reply aloud once—spacing and TTS pacing still OK after hold-back?
- [ ] **Honesty:** After routing, does the assistant describe **what the screen shows** if uncertain—not **why** the platform didn’t update?

---

## 8. How to extend the pattern catalog

1. Capture the **exact** leaked phrase from UAT transcript (voice or text).
2. Add a **longest-first** regex in `_REDACT_PATTERNS` with preferred replacement (delete vs neutral rewrite).
3. Add **`test_sanitize_strips_…`** with the full sentence.
4. If the leak reflects a **missing route**, add Layer A routing first; keep regex as backup.
5. Document in [UAT_VOICE_SCRIPT.md](./UAT_VOICE_SCRIPT.md) if it closes an open UAT item.

Avoid broad patterns that strip legitimate words (e.g. global removal of “handler” in mortgage servicing copy).

---

## 9. File map (quick reference)

| File | Layer |
|------|-------|
| `examples/mortgage-servicing/agent/src/relay_mortgage_agent/agent.py` | A (routing), B (context), C (wrap LLM) |
| `examples/mortgage-servicing/agent/src/relay_mortgage_agent/system_prompt.txt` | B |
| `examples/mortgage-servicing/agent/src/relay_mortgage_agent/response_guardrails.py` | C |
| `runtime/tests/test_mortgage_agent_guardrails.py` | Tests |
| `plans/UAT_VOICE_SCRIPT.md` (UAT-006) | Manual acceptance |

---

## 10. Suggested review agenda (30 min)

1. Confirm **Layer A** coverage for §12.1 demo steps 4–12 (search, tools, draft, date edit).
2. Read **`system_prompt.txt`** aloud—any remaining internal terms?
3. Walk one **LLM fallback** turn in logs: context shape + sanitizer output.
4. Decide **Option A/B/C** for Phase 11 ([phase-11-hardening-uat.md](./phase-11-hardening-uat.md)).
5. Assign owner for **debug Shared state panel** gating (frontend) vs **agent** guard rails.

---

## 11. Changelog

| Date | Change |
|------|--------|
| 2026-09-25 | Initial doc: mortgage agent Layers A–C, UAT-006, streaming strip fix documented |
