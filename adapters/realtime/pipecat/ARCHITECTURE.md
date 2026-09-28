# Two-plane realtime architecture (Phase 2)

Relay separates **control** from **media** for browser voice sessions:

| Plane | Channel | Purpose |
|-------|---------|---------|
| Control | RP WebSocket (`/ws/sessions/{id}`) | Session lifecycle, text turns, typed actions, observability events |
| Media | SmallWebRTC (`POST/PATCH …/webrtc/offer`) | Bidirectional audio (Pipecat pipeline behind `RealtimeTransport`) |

## Correlation

1. Client obtains `session_id` + dev token via Phase 1 flow (`SESSION_READY` on WebSocket).
2. Voice attach reuses the same `session_id`; WebRTC signaling includes it in `request_data` for adapter binding.
3. Transport metrics (`transport.connect_latency_ms`, `transport.media_connected`) publish on the RP event bus with the same `session_id` / `trace_id`.

## Boundaries

- Pipecat types stop in `adapters/realtime/pipecat/` — runtime depends only on `RealtimeTransport`.
- `@relay/web-sdk` implements signaling with browser WebRTC APIs (no Pipecat client packages).
- Post-POC: swap to `livekit.py` without changing mortgage UI or protocol schemas (§5.3).
