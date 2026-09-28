# Relay — Phase 0: Foundation (repo, RP, adapter ports)

## Summary

Bootstrap the monorepo, define **Relay Protocol (RP)** identifiers and event schemas, and publish stable **adapter port** interfaces so Pipecat, OpenAI, Deepgram, and LangGraph remain replaceable implementation details. Mortgage validates only generic **health** and **session connection**—no domain tools yet.

**PRD:** §5.2 (runtime ports), §8 (RP), §13.2 (repository layout), §15.1 phase 0.

## Depends on

None.

## Relay deliverables

| Area | Target artifact |
|------|-----------------|
| Monorepo | Root workspace: npm/pnpm workspaces + Python packaging per §13.2 |
| Protocol | `packages/protocol/` — event enums, JSON schemas, `protocol_version`, canonical metadata (§8.2) |
| Python SDK types | `packages/python-sdk/` — shared event models for runtime/agents |
| Port interfaces | `runtime/ports/` or `adapters/` base ABCs: `RealtimeTransport`, `SpeechToTextProvider`, `TextToSpeechProvider`, `TurnDetector`, `ModelProvider`, `AgentAdapter`, `ToolExecutor`, `StateStore`, `EventStore`, `EventPublisher` |
| Gateway shell | `services/gateway/` — FastAPI app, `/health`, `/ready` |
| Infra | `infra/docker/docker-compose.yml` — Redis + PostgreSQL placeholders |
| CI | Lint, protocol contract tests, import-linter rules blocking adapter leakage into `packages/protocol` |

## Mortgage deliverables

| Area | Target artifact |
|------|-----------------|
| Example shell | `examples/mortgage-servicing/frontend/` — Next.js + shadcn placeholder page |
| Config | `projectId`, `agentId` env wiring only (no business UI) |

## Runtime components touched

SessionManager (skeleton), EventGateway (publish/subscribe stub), TraceManager (correlation ID helper).

## Key RP events (subset)

`SESSION_STARTED`, `SESSION_READY`, `SESSION_ERROR`, `TRACE_LINK`.

## Tasks

- [ ] Create directory tree per PRD §13.2 with README pointers to this plan.
- [ ] Implement RP schema package with validation tests for all event families in §8.1 (payloads may be minimal).
- [ ] Define port interfaces; document that Pipecat types must not appear in protocol or web-sdk exports.
- [ ] Add dev session token mint endpoint (short-lived, POC-only).
- [ ] Docker Compose: Redis, Postgres, gateway healthcheck.
- [ ] Contract test suite: every RP event serializes/deserializes with required metadata fields.

## Test cases

| ID | Type | Description | Expected |
|----|------|-------------|----------|
| P00-TC-001 | Unit | Invalid RP payload missing `session_id` | Validation error |
| P00-TC-002 | Contract | Round-trip all §8.1 event type names | Pass schema tests |
| P00-TC-003 | Integration | `GET /health` with Compose up | 200 OK |
| P00-TC-004 | Integration | Client obtains dev token + `SESSION_READY` | Session id returned |

## Acceptance criteria

- [ ] Repo layout matches §13.2; no mortgage logic under `runtime/` or `packages/protocol`.
- [ ] RP is versioned; event catalog matches §8.1 names and §8.2 metadata.
- [ ] All §5.2 ports defined with docstrings referencing adapter implementations later.
- [ ] Health + session connection demonstrable from mortgage frontend shell.
- [ ] CI runs protocol contract tests on every change.

## Out of scope

Pipecat integration, voice, agent LLM calls, tool registry, state versioning, observability backend (later phases).

## Post-POC note

Protobuf/compact serialization adapters may wrap RP without changing event semantics (§8 intro).
