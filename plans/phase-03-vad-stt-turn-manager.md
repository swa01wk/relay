# Relay — Phase 3: VAD/STT + TurnManager (voice turns)

## Summary

Complete the **voice input** path: VAD/endpointing, streaming STT, and TurnManager integration so user speech produces finalized transcripts and explicit turn events—still without spoken agent replies (Phase 4).

**PRD:** §6.1 (pipeline), §6.2–§6.3, §15.1 phase 3.

## Depends on

- [Phase 2: Pipecat SmallWebRTC](./phase-02-pipecat-small-webrtc.md)

**Decisions:** [DECISIONS.md](./DECISIONS.md) (D-003-001–005; mic bind + idle receiver [D-003-004](./DECISIONS.md#d-003-004-smallwebrtc-mic-track-binding-race), [D-003-005](./DECISIONS.md#d-003-005-smallwebrtc-audio-receiver-idle)).

## Relay deliverables

| Area | Target artifact |
|------|-----------------|
| Speech adapters | `SpeechToTextProvider` + Deepgram (or Pipecat STT service) behind port |
| TurnDetector | VAD/endpointing signals → `USER_SPEECH_STARTED` / `USER_SPEECH_ENDED` |
| TurnManager | Extend FSM: USER_SPEAKING → ENDPOINTING → PROCESSING (§6.2) |
| Pipecat pipeline | Mic → VAD → STT → Relay turn events |
| PlaybackTracker | Stub for Phase 4 |

## Mortgage deliverables

| Area | Target artifact |
|------|-----------------|
| UI | Live transcript panel driven by `TRANSCRIPT_DELTA` / `TRANSCRIPT_FINAL` |
| Voice UX | VAD auto-endpoint + **Mute/Unmute** in UI ([DECISIONS.md](./DECISIONS.md) D-003-001) |

## Key RP events

`USER_SPEECH_STARTED`, `USER_SPEECH_ENDED`, `TRANSCRIPT_DELTA`, `TRANSCRIPT_FINAL`, `TURN_STARTED`, `TURN_PROCESSING`.

## Tasks

- [ ] Wire streaming STT partials to EventGateway with sequence ordering.
- [ ] Finalize turn on endpointing; invoke AgentRuntime with transcript text (text response OK in UI until Phase 4).
- [ ] Instrument endpointing delay metrics (§14.1 turn detection).
- [ ] Replaceable TurnDetector—config flag to tune POC endpointing.
- [ ] Integration test: inject audio frames → expect `TRANSCRIPT_FINAL`.

## Test cases

| ID | Type | Description | Expected |
|----|------|-------------|----------|
| P03-TC-001 | E2E | Speak short phrase | Final transcript matches intent (real STT) |
| P03-TC-002 | E2E | Hold-to-talk release | `TURN_PROCESSING` after endpoint |
| P03-TC-003 | Unit | Turn FSM voice path | Matches §6.2 states |
| P03-TC-004 | Integration | Cancel mid-utterance | Clean abort without duplicate turns |

## Acceptance criteria

- [ ] Stable voice turns with explicit endpointing events (§6.3).
- [ ] STT swappable via adapter (§14.3).
- [ ] One active turn owner per session.
- [ ] Mortgage UI shows streaming + final transcript.

## Out of scope

Streaming TTS, agent speaking, tools, interruption (Phase 7).
