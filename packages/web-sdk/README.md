# @relay/web-sdk

Thin client SDK (Phase 1 text + Phase 2 optional `transport: "small-webrtc"` + Phase 5 actions/state). Public exports must not reference Pipecat or other adapter types.

Phase 5: `registerAction(name, handler)`, `sendState(snapshot)`, `sendEvent(name, payload)` on the RP WebSocket.

Phase 9 HITL: `onApprovalRequested(handler)` (alias for `APPROVAL_REQUESTED`), `grantApproval(approvalId, authProof?)`, `rejectApproval(approvalId)` — application-owned approval UI; runtime commits only after grant.

Voice attach: `connect()` (RP WebSocket) then `connectVoice()` → `POST/PATCH /sessions/{id}/webrtc/offer`.

Media implementation: [`src/webrtc-media.ts`](src/webrtc-media.ts) — `addTransceiver` (`sendrecv`), remote playout via Web Audio + `<audio>`. When voice is connected, the gateway speaks **voice turns** (streaming TTS) and **text Send** (batch TTS); see [VOICE_LIFECYCLE.md](../../plans/VOICE_LIFECYCLE.md) and [D-004-005](../../plans/DECISIONS.md#d-004-005-spoken-replies-when-webrtc-connected).

See [`plans/phase-00-foundation.md`](../../plans/phase-00-foundation.md).
