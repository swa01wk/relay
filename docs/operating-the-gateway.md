# Operating the Relay gateway

For whoever runs the gateway (not for app developers — their docs ship with the SDK in
`packages/web-sdk/`). Covers configuration, operator endpoints, observability, gateway-wide
agents and custom Python agents.

## Operator endpoints

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

## Gateway-wide agents (local development)

Files in `agents/` (`RELAY_AGENTS_DIR`) are agents every dev session can use; `${VAR:-default}`
expands in `tools_url`. They serve `POST /dev/sessions` (`RELAY_DEV_SESSIONS=1`) and the example
apps only — a session started with a project key uses that project's own agents and never these.
Format: [agents/README.md](../agents/README.md). After editing, restart the gateway and look for
`agent <id> loaded … (<n> tools)` or `agent manifest skipped: <reason>` in its log.

With `RELAY_EXAMPLE_MORTGAGE=1` the mortgage example is the default agent for dev sessions whose
`agent_id` is not registered; otherwise the default is a plain assistant with no tools.

## Custom Python agents

Only when an agent needs behaviour a prompt cannot express (deterministic routes, multi-step approval → commit → verify flows), write a Python `AgentAdapter` (usually wrapping `relay_runtime.ToolUsingAgent`) and register it in `services/gateway/src/relay_gateway/core/container.py` with `add_tool_agent(agent_id, build_agent=..., register_tools=..., tools_url_env=..., local_executor=...)`. The mortgage example (`examples/mortgage-servicing/agent/`) is the reference.

## Configuration

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
| `RELAY_EXAMPLE_MORTGAGE` | — (off) | `1` makes the mortgage example the default agent for dev sessions (demos and tests; needs the example packages installed). Off: the default is a plain assistant with no tools |
| `RELAY_MORTGAGE_TOOLS_URL` | in-process | With the example on: its tools service URL |
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
| `RELAY_SECRETS_KEY` | — | Long random string (24+ characters) that encrypts customers' model keys and signing secrets at rest. Without it secrets cannot be stored. Changing or losing it makes stored secrets unreadable |
| `RELAY_ALLOW_PRIVATE_TOOLS_URLS` | — (off) | `1` lets projects use `http://` and private/loopback tools URLs. Local development only: with it on, a customer can make the gateway call hosts inside your network |
| `RELAY_DEV_SESSIONS` | — (off) | `1` enables `POST /dev/sessions` (no key; the caller names the project). Local development and tests only — the compose stack sets it |
| `RELAY_PUBLIC_URL` | request host | Public address of the gateway, used in the `relay login` link (set it behind a proxy) |
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
