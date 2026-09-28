# Relay — Phase 1: SessionManager + text loop

## Summary

Deliver a **text-only** conversation path: browser ↔ EventGateway ↔ SessionManager ↔ TurnManager ↔ AgentRuntime with streaming model output as RP events. Proves actor-like session serialization and turn lifecycle before realtime media.

**PRD:** §6.2–§6.3 (turn rules), §9 (SessionManager, TurnManager, AgentRuntime, EventGateway), §15.1 phase 1.

## Depends on

- [Phase 0: Foundation](./phase-00-foundation.md)

## Relay deliverables

| Area | Target artifact |
|------|-----------------|
| SessionManager | Create/end session, bind agent + auth context (§9) |
| TurnManager | Text turn FSM: IDLE → PROCESSING → TURN_COMPLETE (§6.2) |
| EventGateway | WebSocket (or SSE) carrying RP JSON; sequence numbers |
| ContextManager | Minimal transcript + state slot for text |
| AgentRuntime + ModelRouter | `OpenAIProvider` behind `ModelProvider` |
| AgentAdapter | LangGraph or thin async handler in `adapters/agents/` |
| Web SDK | `createRelaySession`, `on("transcript")`, send user text, connection state (§10.2 subset) |
| Persistence | Append-only event log to PostgreSQL via `EventStore` |
| Active session | Redis for session routing / single-writer lock |

## Mortgage deliverables

| Area | Target artifact |
|------|-----------------|
| Frontend | Connect button, text input, message list via Web SDK only |
| Agent | Reference prompt in `examples/mortgage-servicing/agent/` — generic assistant tone, no tools yet |
| Fixture mention | Optional copy of Rajesh scenario as text-only smoke |

## Key RP events

`TURN_STARTED`, `TURN_PROCESSING`, `TRANSCRIPT_FINAL`, `RESPONSE_STARTED`, `RESPONSE_DELTA`, `RESPONSE_COMPLETED`, `TURN_COMPLETED`.

## Tasks

- [x] Implement per-session asyncio queue (actor-like ownership §3.3).
- [x] Wire Web SDK to EventGateway; map AG-UI adapter if used—RP remains source of truth (§8.3).
- [x] Persist all turn/response events with `turn_id`, `trace_id`.
- [x] OpenAI adapter: streaming tokens → `RESPONSE_DELTA`.
- [x] Mortgage UI: single text round-trip (“hello” / “who are you?”).
- [x] Integration test: one full text turn without browser.

## Test cases

| ID | Type | Description | Expected |
|----|------|-------------|----------|
| P01-TC-001 | E2E | Connect + send text | Agent response visible |
| P01-TC-002 | Integration | Two rapid messages same session | Ordered turns; no interleaved corruption |
| P01-TC-003 | Unit | Turn FSM illegal transition | Rejected / logged |
| P01-TC-004 | Integration | Event log replay | Turn reconstructable from DB |

## Acceptance criteria

- [x] Text-only mortgage turn completes through public Web SDK contract.
- [x] One session owner; concurrent events serialized (§6.3).
- [x] No Pipecat/LangGraph types in RP or web-sdk public API.
- [x] Provider keys server-side only (§11.3).

## Out of scope

Voice transport, UI actions, shared semantic state, tools, interruption, HITL.
