# Post-POC boundaries

Explicit scope limits from **PRD §2.2** and evolution path from **§15.3–§15.4**. Implementation plans must **not** expand POC phases to include these unless the PRD is revised.

## POC non-goals (do not build in Phases 0–11)

| Area | PRD reference |
|------|----------------|
| Custom ICE/STUN/TURN/media server | §2.2 |
| Production core banking / real money movement | §2.2 |
| Full SaaS tenant, billing, control plane | §2.2 |
| Native mobile SDKs, PSTN, multi-party conferencing | §2.2 |
| Kubernetes, multi-region, high-scale distributed deploy | §2.2 |
| Every model/STT/TTS provider in V1 | §2.2 |
| Replay studio, advanced routing, policy marketplace | §2.2 |

## In-scope transport evolution (planned adapter only)

| Stage | Transport | What changes | What must not |
|-------|-----------|--------------|---------------|
| POC | Pipecat + SmallWebRTC | Browser ↔ bot media | Session, turn, RP, SDK, mortgage contracts |
| Early production | Pipecat + LiveKit | Media topology, reconnect | Core runtime semantics |
| Future | Telephony, etc. | Adapter only | Business/conversation contracts |

LiveKit stub: `adapters/realtime/pipecat/livekit.py` may exist as interface placeholder in Phase 2—implementation deferred until migration triggers in §5.4.

## Post-POC roadmap (after Phase 11)

1. Pipecat + LiveKit when production media requirements justify it.
2. Native speech-to-speech realtime model adapter.
3. Telephony/SIP transport for call-center use cases.
4. MCP adapter + broader enterprise tool governance.
5. Second reference domain without runtime core changes.
6. Replay/debug studio, automated conversation evals, richer control plane.
7. Kubernetes/NATS/gRPC/Go hot-path services only if profiling requires.

## Final product statement (PRD §15.4)

Relay owns conversation semantics. Pipecat accelerates the media layer. Mortgage is the first proof consumer—not part of the core.
