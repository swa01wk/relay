# Relay — Phase 10: Observability + evals

## Summary

Instrument the **latency waterfall** (§14.1), distributed **OpenTelemetry** traces across media, speech, model, tools, state, and HITL, plus session timeline reconstruction for evals and debugging.

**PRD:** §14.1, §4.1 persistence plane, §15.1 phase 10.

## Depends on

- [Phase 9: HITL commit + verify](./phase-09-hitl-commit-verify.md) (full path to trace)
- Voice stack from Phases 2–4 for media spans

## Relay deliverables

| Area | Target artifact |
|------|-----------------|
| TraceManager | Correlate `trace_id` across components (§9) |
| OpenTelemetry | `infra/otel/` + runtime/gateway instrumentation |
| Metrics | RP `METRIC` events or OTLP equivalents for §14.1 stages |
| Event timeline | Query API or CLI: session → ordered RP events + spans |
| Dashboards | Optional Grafana/Tempo compose profile |

## Mortgage deliverables

| Area | Target artifact |
|------|-----------------|
| Demo | Run §12.1 scenario; export trace timeline artifact for stakeholders |
| No new features | Observability only |

## Latency stages to instrument

Transport, turn detection, STT, model (TTFT), tools, TTS, end-to-end, UX/state metrics (§14.1 table).

## Tasks

- [x] Propagate `trace_id` / `correlation_id` from session start through tools and HITL.
- [x] Span around each §14.1 stage with standard attribute names (`TRACE_LINK` + `relay.stage.*`).
- [x] Trace completeness test: rebuild turn narrative from store (§14.2).
- [x] Document eval procedure: [OBSERVABILITY_EVAL.md](./OBSERVABILITY_EVAL.md).
- [x] Wire CI to run Phase 10 pytest (timeline tests).

## Test cases

| ID | Type | Description | Expected |
|----|------|-------------|----------|
| P10-TC-001 | Integration | Single voice turn | Spans for STT, model, TTS present |
| P10-TC-002 | Integration | Parallel tools | Child spans per tool_call_id |
| P10-TC-003 | Integration | HITL commit | Approval + commit spans linked |
| P10-TC-004 | Unit | Event log + trace join | Full turn reconstructable |

## Acceptance criteria

- [x] PRD §14.3: complete session reconstructable from events/traces.
- [x] Latency waterfall visible for POC demo tuning (`waterfall_ms` + metrics).
- [x] Failures and interruptions appear as observable product metrics (§2.1 goals) — METRIC + injection hooks Phase 11.

## Out of scope

Full replay studio, automated conversation eval marketplace (post-POC §15.3).
