# Relay — Phase 2: Pipecat SmallWebRTC transport

## Summary

Integrate **Pipecat** as the realtime substrate with **SmallWebRTC** POC transport. Goal is bidirectional **audio connection** between browser and runtime with RP session binding—not yet full STT/TTS agent loop.

**PRD:** §5.1–§5.3, §13.1 (Pipecat + SmallWebRTC), §15.1 phase 2.

## Depends on

- [Phase 1: Text session loop](./phase-01-text-session-loop.md)

## Relay deliverables

| Area | Target artifact |
|------|-----------------|
| Realtime adapter | `adapters/realtime/pipecat/small_webrtc.py` implementing `RealtimeTransport` |
| Pipecat pipeline shell | Frame ingress/egress wired to SessionManager session id |
| Web SDK | `transport: "small-webrtc"` — attach voice to existing session (§10.2) |
| LiveKit placeholder | `livekit.py` interface stub + doc pointing to §5.4 migration triggers |
| Media health | RP `connection_state` / transport metrics hooks |

## Mortgage deliverables

| Area | Target artifact |
|------|-----------------|
| UI | Mic permission, connect voice, audio level or “connected” indicator |
| No STT yet | Optional loopback or silence verification |

## Runtime components touched

SessionManager (bind transport), Realtime adapter layer only—TurnManager receives transport events later.

## Key RP events

`SESSION_READY` (transport ready), observability `METRIC` for connection setup (§14.1 transport).

## Tasks

- [x] Implement Pipecat SmallWebRTC bot + browser client pairing per Pipecat docs.
- [x] Correlate WebRTC session with RP `session_id` from Phase 1.
- [x] Ensure Pipecat types stop at adapter boundary—contract test imports `packages/protocol` without pipecat.
- [x] Document two-plane architecture: media (WebRTC) vs control (RP WebSocket/data channel).
- [x] Add reconnect/basic error surfacing to Web SDK.

## Test cases

| ID | Type | Description | Expected |
|----|------|-------------|----------|
| P02-TC-001 | Manual/E2E | Connect voice after text session | ICE connected; indicator green |
| P02-TC-002 | Contract | `RealtimeTransport` mock swap | Session logic unchanged |
| P02-TC-003 | Integration | Session end closes WebRTC | Clean teardown |

## Acceptance criteria

- [ ] Browser establishes SmallWebRTC audio path to Relay runtime.
- [ ] Transport replaceable in principle—LiveKit stub present (§5.3).
- [ ] No mortgage-specific code in pipecat adapter.
- [ ] Connection setup latency logged (Phase 10 will aggregate).

## Out of scope

VAD, STT, TTS, turn finalization, agent speech (Phases 3–4).

## Risk mitigation

Pipecat leak into product API → adapter contract tests (§15.2).
