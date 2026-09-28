# Relay POC — acceptance & gate test tracker

**Purpose:** Single place for **acceptance criteria**, **gate test IDs**, and **pending vs passed** status.  
**Sign-off rule:** A phase is complete in [STATUS.md](./STATUS.md) only when every **required** row for that phase is **Pass** (or **Pass manual** with evidence link).

**Last updated:** 2026-09-28

## Legend

| Status | Meaning |
|--------|---------|
| **Pass** | Automated test green in CI or local pytest/Playwright (document command) |
| **Pass manual** | Operator/script evidence (date, session id, link to log) |
| **Pending** | Not yet run, flaky in CI, or needs live keys / full stack |
| **N/A** | Out of scope for POC |

## Program-level DoD (PRD §14.3)

| Criterion | Gate / evidence | Status | Notes |
|-----------|-----------------|--------|-------|
| Core mortgage journey primarily by voice (§12.1) | P11-TC-001 | **Pending** | Text UAT staged in Playwright; voice = manual [UAT_VOICE_SCRIPT.md](./UAT_VOICE_SCRIPT.md) |
| Interruption commits heard content only (§7) | P07-TC-002, P07-TC-003 | **Pass** | `runtime/tests/test_phase07_*` |
| No Pipecat/types in public RP or Web SDK | P00-TC-002, P11-TC-004 | **Pass** | import-linter + contract tests |
| Providers swappable via adapters (§9.2) | P11-TC-004, P02-TC-002 | **Pass** | Mock model + transport swap tests |
| Manual UI edits block stale agent (§10) | P08-TC-002, P08-TC-004 | **Pass manual** | Playwright flaky in CI stack — re-run with Docker |
| Parallel read-only tools (§6, §11.1) | P06-TC-002 | **Pass** | pytest + Playwright phase-06 |
| Draft-only until approval (§11.2) | P09-TC-003 | **Pass** | `test_phase09_hitl.py` |
| Protected commit + verify (§12.2) | P09-TC-001, P09-TC-004 | **Pass** | pytest + Playwright (stack @ :3000) |
| Session reconstructable (§14.2) | P10-TC-004, P01-TC-004 | **Pass** | `session_timeline` + event log tests |
| LiveKit swap without runtime API change (§5.3) | P11 LiveKit stub compile | **Pass** | `test_livekit_stub.py` |

---

## Phase gate matrix

| Phase | Gate IDs | Automated command | Status |
|-------|----------|-------------------|--------|
| 0 | P00-TC-001–004 | `pytest packages/protocol/tests services/gateway/tests -q` | **Pass** |
| 1 | P01-TC-001–004 | `pytest runtime/tests/test_text_turn_integration.py -q` | **Pass** |
| 2 | P02-TC-001–003 | `pytest services/gateway/tests/test_p02_webrtc_integration.py -q` | **Pending** | Env/network sensitive |
| 3 | P03-TC-001–004 | `pytest services/gateway/tests/test_p03_voice_smoke.py -q` | **Pending** | Needs voice stack |
| 4 | P04-TC-001–004 | `pytest runtime/tests/test_voice_tts_integration.py -q` | **Pending** | Needs voice stack |
| 5 | P05-TC-001–004 | `pytest runtime/tests/test_phase05_* + e2e/phase-05-actions.spec.ts` | **Pass** / **Pending** E2E | E2E needs `PLAYWRIGHT_E2E=1` + stack |
| 6 | P06-TC-001–004 | `pytest runtime/tests/test_phase06_* + e2e/phase-06-tools.spec.ts` | **Pass** / **Pending** E2E | |
| 7 | P07-TC-001–004 | `pytest runtime/tests/test_phase07_* + e2e/phase-07-interruption.spec.ts` | **Pass** / **Pending** E2E | Voice UAT-001–004 manual |
| 8 | P08-TC-001–004 | `pytest runtime/tests/test_phase08_* + e2e/phase-08-*.spec.ts` | **Pass** / **Pending** E2E | P08-TC-002/003 flaky in CI |
| 9 | P09-TC-001–004 | `pytest runtime/tests/test_phase09_* + e2e/phase-09-hitl.spec.ts` | **Pass** / **Pending** E2E | WS: `test_p09_hitl_ws.py` **Pass** |
| 10 | P10-TC-001–004 | `pytest runtime/tests/test_phase10_observability.py -q` | **Pass** | |
| 11 | P11-TC-002–005 | `pytest runtime/tests/test_phase11_hardening.py -q` | **Pass** | |
| 11 | P11-TC-001 | `e2e/phase-11-uat-demo.spec.ts` + voice script | **Pending** | Text staged pass; voice manual |

---

## Pending items (action queue)

1. **Playwright full stack** — Run all `e2e/phase-*.spec.ts` with Docker (`:8080`, `:8090`, `:3000`) and `PLAYWRIGHT_E2E=1`.
2. **Voice WebRTC integration** — P02/P03/P04 gateway tests green with Pipecat prewarm (local or nightly CI with secrets).
3. **Phase 8 CI flake** — P08-TC-002/003 slow-tool race; re-run or extend timeouts.
4. **P11-TC-001 voice-first** — Full §12.1 via [UAT_VOICE_SCRIPT.md](./UAT_VOICE_SCRIPT.md); record session id + trace export.
5. **Phase 8 + 9 formal sign-off** — Close STATUS milestones after pending E2E above.

---

## Trace export on failure (Phase 10)

```bash
# After a failing pytest session id is known:
python scripts/export_session_timeline.py --session-id <id> --from-store memory
# Or via gateway (dev token):
curl "http://localhost:8080/dev/sessions/<id>/timeline?token=<dev_token>"
```

CI: `.github/workflows/ci.yml` runs Phase 10 timeline tests; nightly workflow can attach timeline JSON as artifact (see [OBSERVABILITY_EVAL.md](./OBSERVABILITY_EVAL.md)).

---

## Related docs

| Doc | Role |
|-----|------|
| [TESTING.md](./TESTING.md) | Acceptance criteria tables per phase |
| [STATUS.md](./STATUS.md) | Milestone checklists & POC DoD |
| [OBSERVABILITY_EVAL.md](./OBSERVABILITY_EVAL.md) | Latency waterfall & eval procedure |
| [UAT_VOICE_SCRIPT.md](./UAT_VOICE_SCRIPT.md) | Manual voice operator script |
