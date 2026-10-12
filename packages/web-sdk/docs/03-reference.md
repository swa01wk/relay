# Reference

## Gateway HTTP / WebSocket

| Method & path | Purpose |
|---|---|
| `GET /health`, `GET /ready` | Liveness / readiness |
| `GET /metrics` | Prometheus metrics. Off (404) unless `RELAY_METRICS_TOKEN` is set (scrape with `Authorization: Bearer <token>`) or `RELAY_METRICS_ENABLED=1` (no auth; private networks only) |
| `GET /admin` | Session inspector page for operators (sessions, conversation, tools, usage/cost, approvals & saves). Off (404) unless `RELAY_ADMIN_TOKEN` is set; the page asks for the token |
| `GET /admin/sessions?limit=` | Recent sessions: `session_id`, `agent_id`, `project_id`, `trace_id`, `started_at`, `last_event_at`, `event_count`, `turns`, `errors`, `ended`, `live`. `Authorization: Bearer <RELAY_ADMIN_TOKEN>` |
| `GET /admin/sessions/{id}` | Any session's timeline (same shape as the dev timeline) plus `audit`. Bearer admin token |
| `GET /admin/audit?limit=&session_id=` | Audit trail, newest first: one entry per approval — `tool_name`, `summary`, `arguments`, `decision` (`pending`/`granted`/`rejected`), `via` (`approval`/`form_submit`), `outcome` (`saved`/`unverified`/`failed`), `error`, timestamps, `session_id`, `trace_id`. Bearer admin token |
| `POST /dev/sessions` `{project_id, agent_id}` | Create a session → `{session_id, dev_token, token_expires_at, events}` (proof-of-concept token; the SDK calls this in `connect()`) |
| `GET /dev/sessions/{id}?token=` | Session info |
| `GET /dev/sessions/{id}/timeline?token=` | Ordered events + metrics/spans for debugging a session, with `usage` totals (model calls, tokens, `cost_usd` when prices are configured) |
| `WS /ws/sessions/{id}?token=` | All Relay Protocol events (server → client) and client messages (below) |
| `POST /sessions/{id}/webrtc/offer?token=` | WebRTC SDP offer → answer (voice); `PATCH` adds ICE candidates |

Client → server WebSocket messages (the SDK sends these for you): `USER_TEXT {text}`, `STATE_SNAPSHOT {state, based_on_version, client_state_version}`, `ACTION_APPLIED {action, action_id, result}`, `ACTION_FAILED {action, action_id, reason}`, `APP_EVENT {name, payload}`, `VOICE_CANCEL`, `PING`.

App events the runtime understands: `ui.capabilities {actions: [{name, description, parameters}]}` (advertised screen actions; sent by `registerAction(..., spec)`), `ui.form_submit {form_id, title, values}` (`submitForm`), `approval.grant {approval_id, auth_proof}`, `approval.reject {approval_id}`.

## Events (server → client)

Every event: `{type, metadata: {session_id, sequence, turn_id?, trace_id, event_id, …}, payload}`. Subscribe with `session.on(type, handler)`.

| Event | Payload (main fields) | Use in the UI |
|---|---|---|
| `SESSION_READY` | — | Connected |
| `SESSION_ERROR` | `code`, `message` | Show `message`; clear busy state. Codes: `turn_failed` (model/tool error — the session still works), `turn_in_progress` (text sent while a voice utterance is open) |
| `TURN_STARTED` / `TURN_COMPLETED` | — | Busy indicator on / off |
| `TRANSCRIPT_DELTA` | `text` | Live "you are saying…" transcript |
| `TRANSCRIPT_FINAL` | `text` | User bubble (typed and spoken). Text starting with `[Form submitted]` is a form submission |
| `RESPONSE_STARTED` / `RESPONSE_DELTA` / `RESPONSE_COMPLETED` | `text` (delta chunk / full text) | Streamed assistant bubble |
| `RESPONSE_CANCELLED` | `reason` | Response aborted (`turn_failed`, `interrupt`) |
| `RESPONSE_INTERRUPTED` | `heard_text` | User barged in; keep only what was heard |
| `SPEECH_STARTED` / `SPEECH_PROGRESS` / `SPEECH_STOPPED` | `heard_text` (progress) | Agent voice playback; also `agent_activity {speaking}` |
| `TOOL_CALL_STARTED` / `TOOL_CALL_PROGRESS` / `TOOL_CALL_COMPLETED` / `TOOL_CALL_FAILED` | `name`, `arguments` / `progress` / `result` / `error` | Optional activity indicator ("Fetching deals…") |
| `ACTIVITY_STARTED` / `ACTIVITY_PROGRESS` / `ACTIVITY_COMPLETED` | `activity_id`, `label`, `progress` | Parallel-work progress |
| `ACTION_REQUESTED` | `action`, `action_id`, `params` | Handled by `registerAction` / `registerPlaygroundSurfaces` |
| `STATE_SNAPSHOT` / `STATE_DELTA` / `STATE_VERSION_ADVANCED` | `state` / `patch` / `state_version` | Shared state sync |
| `STATE_CONFLICT` | `expected_version`, `actual_version`, `patch` | `onStateConflict`: a human edit won over a stale agent update |
| `APPROVAL_REQUESTED` | `approval_id`, `summary`, `tool_name`, `arguments` | `onApprovalRequested` → approval dialog |
| `APPROVAL_GRANTED` / `APPROVAL_REJECTED` / `COMMIT_STARTED` / `COMMIT_VERIFIED` | `approval_id`, `tool_name`, `form_id` (when from a saved form; `APPROVAL_GRANTED.via = "form_submit"`) / `commit_id`, `verified`, `result` (the tool's response) | Approval outcome |
| `ERROR` | `message`; for a failed save `message: "commit_failed"`, `error`, `approval_id`, `tool_name`, `form_id` | Show failed saves; otherwise diagnostics |
| `METRIC` | `name`, `value`, `details?` | Measurements: `model.ttft_ms`, `voice.first_tts_byte_ms`, `voice.user_stop_to_first_audio_ms`, `turn.endpointing_delay_ms`, and `model.usage` (one per model call: `value` = total tokens, `details` = `{model, input_tokens, output_tokens, cached_input_tokens, total_tokens, cost_usd?}`). Usually ignore in the UI |
| `TRACE_LINK` / `WARNING` | — | Diagnostics; usually ignore |

## UI actions

| Action | Params | Handled by |
|---|---|---|
| `PRESENT_UI` | `{surfaces: Surface[], replace: boolean}` | `registerPlaygroundSurfaces` |
| `SHOW_TABLE` | one table surface | `registerPlaygroundSurfaces` |
| App-defined with a spec (e.g. `FILTER_DEALS_TABLE`) | per the spec's JSON schema | `registerAction(name, handler, spec)` — offered to the model as tool `ui_<NAME>`; the handler's return value is the result the model reads |
| App-defined without a spec | whatever a custom agent sends | `registerAction(name, handler)` |

## Surface specs

The backend/model sends **snake_case JSON**; `registerPlaygroundSurfaces` delivers **normalized camelCase TypeScript objects** (`src/ui-surfaces.ts`). The SDK also accepts common aliases and infers missing chart axes/series and table columns.

| `kind` | Wire format (backend / `present_ui`) | Delivered to the app (`UiSurface`) |
|---|---|---|
| `table` | `title, caption?, columns: string[], rows: object[]` | `columns: {key,label}[]`, `rows`, `caption?` |
| `chart` | `title, chart_type: bar\|line\|area\|pie, x_key, series: {key,label?}[], data: object[], y_label?, stacked?` | `chartType, xKey, series: {key,label}[], data` (numbers coerced), `yLabel?, stacked` |
| `kv` | `title, items: {label,value}[]` | `items: {label,value}[]` |
| `cards` | `title, cards: {title, body?, fields?}[]` | same, `fields` as `{label,value}[]` |
| `comparison` | `title, compare: {name, fields: {label: value}}[]` (2–4) | `entities: string[]`, `rows: {label, values[], differs}[]` |
| `markdown` | `title?, markdown` | `markdown` |
| `notice` | `title?, body` | `title?, body` |
| `form` | `id, title, description?, fields: {name,label?,type?,required?,options?,default?,placeholder?}[], submit_label?, submit_tool?, values?` — with `submit_tool` (a side-effecting tool) Relay builds the fields from that tool's schema (`fields` then only picks/orders names; `values` prefill) | `id, fields: UiFormField[]` (`defaultValue`), `submitLabel` |

Field types for forms: `text`, `textarea`, `number`, `date`, `email`, `select` (needs `options`), `checkbox`. The server keeps at most 4 surfaces per call, 50 table rows, 200 chart points, 6 series, 4 compared entities, 20 form fields.

## SDK exports (`@relay/web-sdk`)

Session: `createRelaySession(options)` → `connect`, `disconnect`, `sendText`, `on`, `onConnectionState`, `onVoiceState`, `onAudioLevel`, `connectVoice`, `disconnectVoice`, `setMicMuted`, `cancelVoiceUtterance`, `registerAction`, `sendState`, `onStateConflict`, `sendEvent`, `onApprovalRequested`, `grantApproval`, `rejectApproval`, and getters `connectionState`, `voiceState`, `sessionId`, `stateVersion`. Also `fetchHealth(gatewayUrl)`, `createDevSession(...)`.

Surfaces: `registerPlaygroundSurfaces`, `submitForm`, `surfaceToCsv`, `normalizeUiSurface`, `normalizePresentUiParams`, `normalizeTableSurface`, `normalizeChartSurface`, constants `PRESENT_UI_ACTION`, `SHOW_TABLE_ACTION`, `FORM_SUBMIT_EVENT`, and the `Ui*` types.

## Configuration (self-hosted gateway)

Set in `infra/docker/.env` (or the gateway container's environment). The gateway reads `.env` only when its container is created: after edits run `docker compose -f infra/docker/docker-compose.yml up -d --force-recreate gateway`.

| Variable | Default | Purpose |
|---|---|---|
| **Required** | | |
| `OPENAI_API_KEY` | — | LLM calls. Missing → a mock model answers |
| `DEEPGRAM_API_KEY` | — | Speech-to-text and text-to-speech (voice). Text works without it |
| **Model** | | |
| `RELAY_OPENAI_MODEL` / `OPENAI_MODEL` | `gpt-4o-mini` | Chat model (`RELAY_` wins) |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible endpoint |
| `RELAY_MODEL_PRICES` | — | JSON, USD per 1M tokens by model id (`"*"` = fallback): `{"<model>": {"input": …, "output": …, "cached_input": …}}`. Enables `cost_usd` on usage metrics; without it only tokens are reported |
| `RELAY_OPENAI_STREAM_USAGE` | `1` | `0` stops asking the API for token usage (for OpenAI-compatible servers that reject `stream_options`) |
| **Agents and tools** | | |
| `RELAY_AGENTS_DIR` | `agents` (`/app/agents` in Docker) | Folder of agent manifests (`*.yaml`) |
| `RELAY_<NAME>_TOOLS_URL` | — | Tools service URLs referenced by manifests as `${VAR}` (e.g. `RELAY_CRM_TOOLS_URL`) |
| `RELAY_MORTGAGE_TOOLS_URL` | in-process | Tools URL for the built-in mortgage example agent |
| `RELAY_TOOL_TIMEOUT_SECONDS` | `30` | Default per-tool-call timeout |
| **Storage** | | |
| `RELAY_DATABASE_URL` | in-memory | Postgres for the event log (`postgresql://…`); unset → memory (lost on restart) |
| `RELAY_REDIS_URL` | local lock | Redis for session locks; unset → in-process lock |
| **Gateway** | | |
| `RELAY_GATEWAY_HOST` / `RELAY_GATEWAY_PORT` | `0.0.0.0` / `8080` | Listen address |
| `RELAY_LOG_LEVEL` | `INFO` | Log level for Relay and the HTTP server |
| `RELAY_LOG_FORMAT` | `text` | `json` writes one JSON object per line: `ts`, `level`, `logger`, `message`, plus `session_id` / `turn_id` / `agent_id` (and `tool`, `approval_id`, … when present) |
| **Observability** | | |
| `RELAY_METRICS_TOKEN` | — | Enables `GET /metrics` and requires this bearer token |
| `RELAY_METRICS_ENABLED` | — | `1` enables `GET /metrics` without auth (the gateway port is browser-facing — use only on a private network) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | Enables OpenTelemetry traces over OTLP/HTTP (e.g. `http://otel-collector:4318`); other standard `OTEL_*` variables apply. `OTEL_SERVICE_NAME` defaults to `relay-gateway` |
| `RELAY_ADMIN_TOKEN` | — | Enables the session inspector and audit API under `/admin` and is the bearer token they require |
| `RELAY_EVENT_RETENTION_DAYS` | — (keep forever) | Delete stored events older than this many days (checked at startup, then hourly). Removes those sessions from the timeline, inspector and audit trail |
| `RELAY_EVENT_STORE_REDACT` | — (store everything) | Comma-separated: `text` (transcripts and assistant replies), `data` (tool arguments/results, UI payloads, app state, approval details). Applies to the stored copy only; the live stream to the app is unchanged |
| `RELAY_SESSION_GRACE_SECONDS` | `60` | End a session this long after its last client disconnects; `0` disables |
| `RELAY_DEV_APPROVER_TOKEN` | `dev-approver` | Proof-of-concept approver credential checked on `approval.grant` (the SDK sends `dev-approver` by default) |
| **Voice / WebRTC** | | |
| `RELAY_DISABLE_WEBRTC` | — | `1` disables voice (text only) |
| `RELAY_ICE_STUN_URL` | `stun:stun.l.google.com:19302` | STUN server (production behind strict firewalls also needs TURN) |
| `DEEPGRAM_STT_MODEL` | `nova-3-general` | Speech-to-text model |
| `DEEPGRAM_TTS_MODEL` / `DEEPGRAM_TTS_ENCODING` / `DEEPGRAM_TTS_SAMPLE_RATE` | `flux-haley-en` / `linear16` / `24000` | Text-to-speech voice and audio format |
| `RELAY_TURN_DETECTOR` | `hybrid` | `hybrid` (Silero start + Smart Turn stop) or `silero` |
| `RELAY_VAD_MIN_VOLUME` | `0.35` | Voice activity threshold (raise if speaker echo triggers interruptions) |
| `RELAY_ENDPOINTING_SILENCE_MS`, `RELAY_DEEPGRAM_ENDPOINTING_MS`, `RELAY_STT_FINAL_ENDPOINT_MS`, `RELAY_UTTERANCE_COMMIT_DELAY_MS` | `400`, `500`, `500`, `350` | End-of-utterance timing |
| `RELAY_SMART_TURN_STOP_SECS`, `RELAY_SMART_TURN_PRE_SPEECH_MS`, `RELAY_SMART_TURN_MAX_DURATION_SECS`, `RELAY_USER_TURN_STOP_TIMEOUT_SECS` | `2.0`, `500`, `8`, `8` | Smart Turn tuning |
| `RELAY_PIPELINE_IDLE_TIMEOUT_SECS` | — | Stop an idle voice pipeline after N seconds |
| **Testing only** | | |
| `RELAY_INJECT_MODEL_TIMEOUT`, `RELAY_INJECT_STT_TIMEOUT`, `RELAY_INJECT_TTS_FAILURE`, `RELAY_INJECT_TRANSPORT_DISCONNECT`, `RELAY_INJECT_TOOL_TIMEOUT_SEC` | — | Fault injection for hardening tests; never set in production |

Frontend (browser-visible, `NEXT_PUBLIC_*`): `NEXT_PUBLIC_GATEWAY_URL`, `NEXT_PUBLIC_PROJECT_ID`, `NEXT_PUBLIC_AGENT_ID`. The CRM example also reads `CRM_TOOLS_URL` server-side for its dashboard. The CRM tools service stores its data in SQLite at `CRM_DB_PATH` (default `crm.db`; `/data/crm.db` on the `crm-data` volume in Docker — `docker compose … down -v` resets it to the demo seed).

## Observability

Everything below is derived from the event stream; nothing needs instrumenting in apps or tools.

**Metrics** (`GET /metrics`, Prometheus format). Counters end in `_total`; durations are histograms in seconds.

| Metric | Labels | Meaning |
|---|---|---|
| `relay_sessions_total`, `relay_sessions_active` | `agent`, `event` | Sessions started/ended; sessions currently open |
| `relay_turns_total`, `relay_turn_duration_seconds` | `agent`, `outcome` (`completed`/`failed`) | Turns and how long they took |
| `relay_session_errors_total` | `code` | `SESSION_ERROR`s (`turn_failed` = model/tool failure) |
| `relay_model_calls_total`, `relay_model_tokens_total`, `relay_model_cost_usd_total` | `model`, `kind` (`input`/`cached_input`/`output`) | Model usage; cost needs `RELAY_MODEL_PRICES` |
| `relay_model_ttft_seconds` | — | Time to first model token |
| `relay_tool_calls_total`, `relay_tool_duration_seconds` | `tool`, `outcome` | Tool calls — a slow or failing tools service shows here, separate from Relay |
| `relay_ui_actions_total` | `action`, `outcome` (`requested`/`applied`/`failed`) | `PRESENT_UI` and app screen actions |
| `relay_approvals_total` | `outcome` (`requested`/`granted`/`form_submitted`/`rejected`) | Approval decisions |
| `relay_commits_total` | `tool`, `outcome` (`saved`/`unverified`/`failed`) | Changes saved after approval or form submit |
| `relay_voice_response_seconds`, `relay_voice_first_tts_byte_seconds`, `relay_voice_endpointing_delay_seconds`, `relay_transport_connect_seconds`, `relay_interruptions_total` | — | Voice latency and barge-ins |

`agent` is a registered `agent_id` or `default`; label values are capped (overflow → `other`).

**Traces** (OpenTelemetry). One trace per session whose trace id is the session's Relay `trace_id` (the same id on every event and in the timeline): `relay.session` → `relay.turn` (status `ERROR` on `turn_failed`; events `model.first_token`, `model.usage`, `interruption`) → `relay.tool <name>`; plus `relay.approval <tool>` spans. Spans carry names, counts, durations and status only — never message text, tool arguments or tool results.

**Logs**. Relay and HTTP access logs share one handler. Credentials are redacted before anything is written — `?token=` (session tokens in WebSocket and timeline URLs), `api_key=`, `secret=`, `password=` and `Bearer` values — in both formats, including tracebacks. Set `RELAY_LOG_FORMAT=json` to ship logs to a log store and join them to metrics and traces by `session_id`.

**Session inspector and audit trail**. Set `RELAY_ADMIN_TOKEN` and open `http://<gateway>/admin`: recent sessions, each conversation turn by turn (what was asked, what was answered, which tools ran, failures), tokens and cost, and every approval or form save with its result. The same data is available as JSON (`/admin/sessions`, `/admin/sessions/{id}`, `/admin/audit`). Both read the event log, so with Postgres they cover past sessions too. Relay has no end-user identity yet: audit entries identify the session, not a person.

**What the event log keeps**. The log holds conversation text and tool data. `RELAY_EVENT_STORE_REDACT=text,data` stores placeholders (`[redacted]`) instead — names, ids, statuses, errors, timings and token counts remain, so metrics, traces and the who/what/when of the audit trail still work, but the inspector no longer shows what was said or which values were saved. `RELAY_EVENT_RETENTION_DAYS` deletes old events. Metrics, traces and logs never contain message text or tool data in either case.

**Dashboard and alerts**. `infra/observability/` has a Grafana dashboard (`grafana/dashboards/relay-overview.json`; import it and pick your Prometheus data source), Prometheus alert rules (`alerts.yml`: gateway down, failing/slow turns, failing/slow tools, slow voice replies, saves failing, model spend) and a scrape config. To run Prometheus and Grafana locally next to the stack:

```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.observability.yml up -d
# Prometheus http://localhost:9090 · Grafana http://localhost:3003 (Relay → Relay overview)
```

**Per-session view (dev)**: `GET /dev/sessions/{id}/timeline?token=` (ordered events, metrics, spans, `usage` totals) with the session's own token. `SESSION_STARTED` carries the session's `agent_id`.
