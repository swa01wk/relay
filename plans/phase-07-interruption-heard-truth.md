# Relay — Phase 7: Interruption + heard-truth

## Summary

Implement **InterruptionManager**, barge-in during agent playout, cancellation policy (§7.3), and **HEARD_TEXT_COMMITTED** so ContextManager uses heard—not generated—text.

**PRD:** §7, §6.2 (INTERRUPTED path), §15.1 phase 7.

**Status:** Signed off (2026-09-25) — [STATUS.md](./STATUS.md), [VOICE_LIFECYCLE.md](./VOICE_LIFECYCLE.md).

## Depends on

- [Phase 4: LLM + streaming TTS](./phase-04-llm-streaming-tts.md) (playback)
- [Phase 6: Parallel tools](./phase-06-parallel-async-tools.md) recommended for demo step 7–9 flow

## Relay deliverables

| Area | Target artifact |
|------|-----------------|
| InterruptionManager | VAD during AGENT_SPEAKING → interrupt flow (§7.1) |
| PlaybackTracker | Finalize heard prefix; separate `generated_text` vs `heard_text` |
| Cancellation | TTS immediate; LLM cancel; tool policy per §7.3 table |
| ContextManager | Subsequent turns use heard_text + new utterance |
| TurnManager | Barge-in: `AGENT_SPEAKING` → `USER_SPEAKING` (§6.2) |

## Mortgage deliverables

| Area | Target artifact |
|------|-----------------|
| Demo | Step 7–8: interrupt EMI explanation; ask for rate history |
| UI | Open rate history view on action after interrupt |
| Voice | Real barge-in during TTS (not button-only stub) |

## Key RP events

`INTERRUPTION_DETECTED`, `RESPONSE_INTERRUPTED`, `HEARD_TEXT_COMMITTED`, `RESPONSE_CANCELLED`.

## Tasks

- [x] Detect user speech during agent playout via transport/VAD.
- [x] Stop TTS immediately; cancel or ignore trailing LLM tokens.
- [x] Persist §7.2 example fields on interrupted response.
- [x] Apply cancellation rules to in-flight read-only tools (§7.3).
- [x] E2E: interrupt long spoken EMI answer; verify context length < full generation (pytest integration).
- [x] Deterministic unit tests for InterruptionManager FSM.

## Test cases

| ID | Type | Description | Expected |
|----|------|-------------|----------|
| P07-TC-001 | E2E | Barge-in during agent speech | Audio stops quickly |
| P07-TC-002 | Integration | HEARD_TEXT_COMMITTED payload | heard ⊂ generated |
| P07-TC-003 | E2E | After interrupt, “show rate history” | Correct UI + agent context |
| P07-TC-004 | Unit | Side-effecting tool in flight + interrupt | Tool does not commit |

## Acceptance criteria

- [x] PRD §14.3: interruption commits heard/delivered content only.
- [x] Event history preserves generated vs heard representations (§7 intro).
- [ ] Demo steps 7–9 (§12.1) achievable by voice @ :3000 (manual UAT — Phase 11).
- [x] No frontend-only interrupt—runtime state change (§7 intro).

## Out of scope

STATE_CONFLICT (Phase 8), HITL commit.

## Risk mitigation

Interrupt races → central cancellation tokens (§15.2).

**Post-sign-off (2026-09-25):** Barge-in must not mute the **next** reply — [D-004-004](./DECISIONS.md#d-004-004-tts-cancel-vs-next-utterance); gate `test_mock_tts_speaks_after_cancel`. Debugging: [VOICE_LIFECYCLE.md](./VOICE_LIFECYCLE.md).

**Manual UAT:** Script + issue log — [UAT_VOICE_SCRIPT.md](./UAT_VOICE_SCRIPT.md). Open: EMI/rate agent routing (UAT-001, UAT-003), full §12.1 7–9 (UAT-004). Closed: post-interrupt TTS silence (UAT-005).
