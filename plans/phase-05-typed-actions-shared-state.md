# Relay — Phase 5: Typed actions + shared state

## Summary

Add **ActionRouter** and semantic **shared state** sync between runtime and application UI—without optimistic versioning (Phase 8). Agent can request typed UI actions; client publishes state snapshots.

**PRD:** §8.1 (ACTION_*, STATE_SNAPSHOT), §10, §15.1 phase 5.

## Depends on

- [Phase 4: LLM + streaming TTS](./phase-04-llm-streaming-tts.md)

## Relay deliverables

| Area | Target artifact |
|------|-----------------|
| ActionRouter | `ACTION_REQUESTED` → client handler → `ACTION_APPLIED` / `ACTION_FAILED` |
| State sync | `STATE_SNAPSHOT`, `STATE_DELTA`; monotonic `state_version` field present |
| Web SDK | `registerAction`, `sendState`, `sendEvent` (§10.2) |
| EventStore | Persist action + state events |
| AgentAdapter | Emit structured action intents from model tool calls or workflow |

## Mortgage deliverables

| Area | Target artifact |
|------|-----------------|
| UI | Case screen, search results, `OPEN_ENTITY` handler |
| Tools API (read) | `search_customer`, `get_mortgage` FastAPI + Postgres seeds |
| Agent tools | Wire search/open flow for Rajesh / MORT-2931 |
| Shared state shape | §10.1 example (`screen`, `selected_entity`, `workflow`, …) |

## Key RP events

`ACTION_REQUESTED`, `ACTION_APPLIED`, `ACTION_FAILED`, `STATE_SNAPSHOT`, `STATE_DELTA`, `STATE_VERSION_ADVANCED`.

## Tasks

- [x] Define generic action envelope (name + payload); mortgage registers handlers client-side.
- [x] Agent opens mortgage via voice/text: search → `OPEN_ENTITY` → UI navigation.
- [x] Client sends state snapshots after UI transitions; runtime stores latest for ContextManager.
- [x] Playwright: text path open Rajesh mortgage (voice optional).
- [x] Keep mortgage tools HTTP services outside `runtime/`—ToolExecutor calls URLs configured per agent.

## Test cases

| ID | Type | Description | Expected |
|----|------|-------------|----------|
| P05-TC-001 | E2E | “Find Rajesh Sharma” | Search UI or results |
| P05-TC-002 | E2E | Open MORT-2931 | Case screen; selected entity in state |
| P05-TC-003 | E2E | Shared state panel | `screen: mortgage_case` |
| P05-TC-004 | Integration | Unknown action | `ACTION_FAILED` with reason |

## Acceptance criteria

- [x] Typed UI actions work over RP; app owns rendering (§10.3).
- [x] Semantic state visible to agent via ContextManager.
- [x] Demo steps 4 partial: agent search + open case (§12.1).
- [x] No EMI/rate domain types in protocol package.

## Out of scope

`STATE_CONFLICT` / stale rejection (Phase 8), parallel tools (Phase 6), HITL.
