# Observability & eval procedure (Phase 10)

## Latency waterfall (PRD §14.1)

Metrics arrive as RP `METRIC` events (ms). Spans arrive as `TRACE_LINK` with `stage`:

| Stage constant | Meaning |
|----------------|---------|
| `relay.stage.transport` | WebRTC connect / disconnect |
| `relay.stage.turn_detection` | Endpointing (`turn.endpointing_delay_ms`) |
| `relay.stage.stt` | Voice transcript committed to turn |
| `relay.stage.model` | LLM streaming |
| `relay.stage.tool` | Tool executor (start/complete per `tool_call_id`) |
| `relay.stage.tts` | Agent audio playout |
| `relay.stage.hitl` | Approval + commit + verify |
| `relay.stage.ux` | Conflicts, action failures (future) |

Built-in model/voice metrics: `model.ttft_ms`, `voice.first_tts_byte_ms`, `voice.user_stop_to_first_audio_ms`.

## Session timeline API

```bash
curl "http://localhost:8080/dev/sessions/<session_id>/timeline?token=<dev_token>"
```

Returns: ordered turns, metrics list, spans, HITL event trail, `waterfall_ms` aggregate.

CLI: `python scripts/export_session_timeline.py --session-id <id> --token <dev_token>`

## Eval regression (compare runs)

1. Run the §12.1 text demo (or Playwright `phase-11-uat-demo.spec.ts`).
2. Export timeline JSON for the session.
3. Compare against baseline:
   - `waterfall_ms.model.ttft_ms` not regressed > 25% without cause
   - Every turn has `TURN_STARTED` … `TURN_COMPLETED` in `turns[].event_types`
   - HITL path includes `hitl[]` entries through `COMMIT_VERIFIED`
4. On interrupt runs, assert `HEARD_TEXT_COMMITTED` present and `heard_text` ⊆ generated in turn narrative.

## CI artifacts

On pytest failure in `runtime/tests/test_phase10_*`, attach timeline from in-memory store in test logs. Nightly: run voice E2E with secrets and archive timeline JSON.

Optional OTLP: see [`infra/otel/README.md`](../infra/otel/README.md) for collector stub (post-POC wiring).
