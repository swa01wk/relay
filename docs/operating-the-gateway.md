# Operating the Relay gateway

For whoever runs the gateway (not for app developers — their docs ship with the SDK in
`packages/web-sdk/`). Covers configuration, operator endpoints, observability, gateway-wide
agents and custom Python agents. To put the whole stack on a server, see [deploying.md](deploying.md).

## Operator endpoints

| Method & path | Purpose |
|---|---|
| `GET /health`, `GET /ready` | Liveness / readiness |
| `GET /metrics` | Prometheus metrics. Off (404) unless `RELAY_METRICS_TOKEN` is set (scrape with `Authorization: Bearer <token>`) or `RELAY_METRICS_ENABLED=1` (no auth; private networks only) |
| `GET /admin` | Session inspector page for operators (sessions, conversation, tools, usage/cost, approvals & saves). Off (404) unless `RELAY_ADMIN_TOKEN` is set; the page asks for the token |
| `GET /admin/sessions?limit=` | Recent sessions: `session_id`, `agent_id`, `project_id`, `trace_id`, `started_at`, `last_event_at`, `event_count`, `turns`, `errors`, `ended`, `live`. `Authorization: Bearer <RELAY_ADMIN_TOKEN>` |
| `GET /admin/sessions/{id}` | Any session's timeline (same shape as the dev timeline) plus `audit`. Bearer admin token |
| `GET /admin/audit?limit=&session_id=` | Audit trail, newest first: one entry per approval — `tool_name`, `summary`, `arguments`, `decision` (`pending`/`granted`/`rejected`), `via` (`approval`/`form_submit`), `outcome` (`saved`/`unverified`/`failed`), `error`, timestamps, `session_id`, `trace_id`. Bearer admin token |
| `POST /dev/sessions` `{project_id, agent_id, user?}` | Create a session (`user` `{id, attributes?}` is sent to tools as `X-Relay-User`, like a secret-key session's; trusted only because dev sessions never run on a public gateway) → `{session_id, dev_token, token_expires_at, events}` (proof-of-concept token; the SDK calls this in `connect()`) |
| `GET /dev/sessions/{id}?token=` | Session info |
| `GET /dev/sessions/{id}/timeline?token=` | Ordered events + metrics/spans for debugging a session, with `usage` totals (model calls, tokens, `cost_usd` when prices are configured) |

## Gateway-wide agents (local development)

Files in `agents/` (`RELAY_AGENTS_DIR`) are agents every dev session can use; `${VAR:-default}`
expands in `tools_url`. They serve `POST /dev/sessions` (`RELAY_DEV_SESSIONS=1`) and the example
apps only — a session started with a project key uses that project's own agents and never these.
Format: [agents/README.md](../agents/README.md). After editing, restart the gateway and look for
`agent <id> loaded … (<n> tools)` or `agent manifest skipped: <reason>` in its log.

Gateway-wide agents (manifests, `add_tool_agent` agents and the mortgage example) send the
session's end user as `X-Relay-User`, like project agents. The example tools services use it for
the Experience Center's per-visitor sandboxes ([experience-center.md](experience-center.md)).

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
| `RELAY_OPENAI_REASONING_EFFORT` | — (model default) | `none`/`minimal`/`low`/`medium`/`high` for reasoning models; lower answers faster (voice). Leave unset for models that reject `reasoning_effort` |
| `RELAY_OPENAI_HEDGE_AFTER_SECS` | — (off) | When a model request has not sent its first chunk after this many seconds, send the same request again and use whichever answers first. Cuts tail latency; the duplicate is billed only for slow requests. `3` suits voice |
| `RELAY_END_TURN_AFTER_DISPLAY` | — (off) | `1` ends a turn after `present_ui` / `fill_form` / screen actions that worked when the model already wrote its reply next to them, saving one model call per display turn |
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
| `RELAY_SIGNUP` | `open` | Who may create an account: `open`, `allowlist` (only `RELAY_SIGNUP_ALLOWLIST`) or `closed`. An unrecognised value means `closed`. Use `allowlist` or `closed` on a public gateway; existing accounts can always sign in |
| `RELAY_EMAIL_VERIFICATION` | `required` | New accounts must confirm their email before their first sign-in. `off` skips it (accounts count as confirmed at sign-up) |
| `RELAY_SMTP_HOST` | — | SMTP server for confirmation and password-reset emails. **Without it, emails are printed to the gateway log** (development only: anyone who can read the log could take over accounts) |
| `RELAY_SMTP_PORT` · `RELAY_SMTP_USERNAME` · `RELAY_SMTP_PASSWORD` · `RELAY_SMTP_STARTTLS` | `587` · — · — · `1` | SMTP connection; STARTTLS on by default |
| `RELAY_EMAIL_FROM` | `Relay <no-reply@localhost>` | Sender of those emails |
| `RELAY_SIGNUP_ALLOWLIST` | — | Comma-separated emails and/or `@domain` entries, e.g. `ana@acme.com,@acme.com` (exact domain only, not subdomains) |
| `RELAY_RATE_LIMITS` | `on` | `off` disables every rate limit and the login lockout (load tests only) |
| `RELAY_TRUST_PROXY_HEADERS` | — (off) | `1` behind a proxy you run (Caddy, nginx, ngrok): client addresses are read from `X-Forwarded-For` (last entry). Leave off when clients reach the gateway directly, or anyone could fake their address and escape per-address limits |
| `RELAY_DEV_SESSIONS` | — (off) | `1` enables `POST /dev/sessions` (no key; the caller names the project). Local development and tests only — the compose stack sets it |
| `RELAY_PUBLIC_URL` | request host | Public address of the gateway, used in the `relay login` link and in emailed links. **Required for emails on a public gateway**: without it, links are only built for `localhost` (or with `RELAY_DEV_SESSIONS`), so a forged `Host` header cannot make the gateway email someone a link to another site |
| `RELAY_ADMIN_TOKEN` | — | Enables the session inspector and audit API under `/admin` and is the bearer token they require |
| `RELAY_EVENT_RETENTION_DAYS` | — (keep forever) | Delete stored events older than this many days (checked at startup, then hourly). Removes those sessions from the timeline, inspector and audit trail |
| `RELAY_EVENT_STORE_REDACT` | — (store everything) | Comma-separated: `text` (transcripts and assistant replies), `data` (tool arguments/results, UI payloads, app state, approval details). Applies to the stored copy only; the live stream to the app is unchanged |
| `RELAY_SESSION_GRACE_SECONDS` | `60` | End a session this long after its last client disconnects; `0` disables |
| `RELAY_DEV_APPROVER_TOKEN` | `dev-approver` | Proof-of-concept approver credential checked on `approval.grant` (the SDK sends `dev-approver` by default) |
| **Voice / WebRTC** | | |
| `RELAY_DISABLE_WEBRTC` | — | `1` disables voice (text only) |
| `RELAY_ICE_STUN_URL` | `stun:stun.l.google.com:19302` | STUN server(s), comma-separated; empty = none. Used by the gateway and handed to browsers |
| `RELAY_TURN_URLS` | — | TURN server(s) for browsers, comma-separated (e.g. `turn:turn.example.com:3478?transport=udp,turn:turn.example.com:3478?transport=tcp`). Needed when the gateway runs behind NAT (Docker, cloud firewalls): without it voice fails with "ICE failed" for many visitors |
| `RELAY_TURN_SECRET` | — | coturn's `static-auth-secret`. The gateway gives each session's browser TURN credentials signed with it (`GET /sessions/{id}/webrtc/ice-servers`, TURN REST scheme: username `<expiry>:<session_id>`); the secret itself never leaves the gateway |
| `RELAY_TURN_TTL_SECONDS` | `3600` | How long those TURN credentials work (minimum 60) |
| `RELAY_STT_PROVIDER` | `deepgram` | Speech-to-text provider for voice sessions: `deepgram`, `cartesia` or `assemblyai`. Needs that provider's key (`DEEPGRAM_API_KEY` / `CARTESIA_API_KEY` / `ASSEMBLYAI_API_KEY`); without it voice runs with no recognition (logged). Text-to-speech stays on Deepgram |
| `CARTESIA_API_KEY` | — | Cartesia key, used when `RELAY_STT_PROVIDER=cartesia` |
| `CARTESIA_STT_MODEL` | `ink-whisper` | Cartesia recognition model. Key terms (manifest `keyterms`, `CARTESIA_STT_KEYTERMS`, else `DEEPGRAM_STT_KEYTERMS`) are sent only to `ink-2*` / `ink-preview*` models |
| `CARTESIA_STT_LANGUAGE` | base of `DEEPGRAM_STT_LANGUAGE`, else `en` | ISO 639-1 code, e.g. `en`, `hi` (`en-IN` becomes `en`) |
| `ASSEMBLYAI_API_KEY` | — | AssemblyAI key, used when `RELAY_STT_PROVIDER=assemblyai` |
| `ASSEMBLYAI_STT_MODEL` | `universal-3-6-pro` | AssemblyAI streaming model, e.g. `assemblyai-stt-3-7-realtime`, `universal-streaming-english`, `universal-streaming-multilingual`. Key terms (manifest `keyterms`, `ASSEMBLYAI_STT_KEYTERMS`, else `DEEPGRAM_STT_KEYTERMS`) are sent as `keyterms_prompt`. Relay's turn detection decides when the user is done |
| `ASSEMBLYAI_STT_LANGUAGE` | base of `DEEPGRAM_STT_LANGUAGE`, else `en` | e.g. `en`, `hi` |
| `DEEPGRAM_STT_MODEL` | `nova-3-general` | Speech-to-text model. Use a nova-3 model: Flux models are not supported for recognition (logged and replaced by `nova-3-general`), and key terms need nova-3 |
| `DEEPGRAM_STT_LANGUAGE` | `en` | Recognition language, e.g. `en-US`, `en-IN` (Indian English), `multi` (several languages in one sentence, e.g. Hindi + English) |
| `DEEPGRAM_STT_KEYTERMS` | — | Comma-separated words every session should listen for, added after the session agent's own manifest `keyterms` (100 in total) |
| `DEEPGRAM_TTS_MODEL` / `DEEPGRAM_TTS_ENCODING` / `DEEPGRAM_TTS_SAMPLE_RATE` | `flux-haley-en` / `linear16` / `24000` | Text-to-speech voice and audio format |
| `RELAY_TURN_DETECTOR` | `hybrid` | `hybrid` (Silero start + Smart Turn stop) or `silero` |
| `RELAY_VAD_MIN_VOLUME` | `0.35` | Voice activity threshold (raise if speaker echo triggers interruptions) |
| `RELAY_ENDPOINTING_SILENCE_MS`, `RELAY_DEEPGRAM_ENDPOINTING_MS`, `RELAY_UTTERANCE_COMMIT_DELAY_MS` | `400`, `500`, `350` | End-of-utterance timing |
| `RELAY_STT_FINAL_ENDPOINT_MS` | `3000` | Ends the utterance this long after a recognizer final if the turn detector never reports the end of speech. Keep it above the Smart Turn wait, or sentences are cut at pauses |
| `RELAY_STT_FINAL_WAIT_MS` | `1200` | How long a finished utterance waits for the final of words still being recognized before using their interim text |
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

**Filling forms from the chat**. The runtime remembers the forms an agent showed (per session, at most 10, cleared by a replacing `present_ui` and by submission) and, while one is open, offers the model a built-in `fill_form` tool. Values are checked against the form's fields before a `FILL_FORM` action goes to the app (text fields up to 500 characters, textareas up to 5,000; submitted form values are capped at 5,000 each); nothing is saved by it, so it needs no approval. It appears as `FILL_FORM` in `relay_ui_actions_total`.

**What developers see of their own project**. Account tokens read their project's sessions, one session's turns/errors/approvals/usage, and a usage report (`GET /v1/projects/{id}/sessions`, `/sessions/{session_id}`, `/usage`; CLI `relay logs`, `relay usage`). They read the same event log as the inspector, filtered by the events' `project_id` (indexed on Postgres), so redaction (`RELAY_EVENT_STORE_REDACT`) and retention apply to them too, and `cost_usd` appears only with `RELAY_MODEL_PRICES`. The usage report counts at most 20,000 events per request and says `truncated` beyond that. Dev sessions (`RELAY_DEV_SESSIONS=1`) take their `project_id` from the client, so on a dev gateway they can show up in any project's activity.

**What the event log keeps**. The log holds conversation text and tool data. `RELAY_EVENT_STORE_REDACT=text,data` stores placeholders (`[redacted]`) instead — names, ids, statuses, errors, timings and token counts remain, so metrics, traces and the who/what/when of the audit trail still work, but the inspector no longer shows what was said or which values were saved. `RELAY_EVENT_RETENTION_DAYS` deletes old events. Metrics, traces and logs never contain message text or tool data in either case.

**Dashboard and alerts**. `infra/observability/` has a Grafana dashboard (`grafana/dashboards/relay-overview.json`; import it and pick your Prometheus data source), Prometheus alert rules (`alerts.yml`: gateway down, failing/slow turns, failing/slow tools, slow voice replies, saves failing, model spend) and a scrape config. To run Prometheus and Grafana locally next to the stack:

```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.observability.yml up -d
# Prometheus http://localhost:9091 · Grafana http://localhost:3013 (Relay → Relay overview)
# Other host ports: RELAY_PROMETHEUS_PORT / RELAY_GRAFANA_PORT in infra/docker/.env
```

**Per-session view (dev)**: `GET /dev/sessions/{id}/timeline?token=` (ordered events, metrics, spans, `usage` totals) with the session's own token. `SESSION_STARTED` carries the session's `agent_id`.

## Sign-in protection

| Protection | Rule |
|---|---|
| Login lockout | 5 wrong passwords for one email → that email is refused for 15 minutes, even with the right password. Unknown emails behave identically, so the response never reveals whether an account exists |
| Login attempts per address | 30 per 15 minutes |
| Sign-ups per address | 5 per hour (plus `RELAY_SIGNUP`) |
| `relay login` starts per address | 10 per 10 minutes; polling 60 per minute per login |
| Sessions | 120 per minute per key; publishable keys also 30 per minute per visitor address |
| Account API | 300 requests per minute per CLI token |
| Wrong passwords when confirming a change | 5 per 15 minutes per account |

Over a limit the gateway answers `429` with `Retry-After`. Counters live in Redis when `RELAY_REDIS_URL` is set (shared by every gateway process), otherwise in memory (per process, reset on restart).

**CLI tokens.** Each `relay login` creates a token for that device only, named after the machine. It expires after 30 days, or after 14 days unused. A copied token can read and can sign devices out or revoke keys, but changes that could hand a project to its holder — creating keys, setting or removing the model key, pushing or deleting agents, changing allowed origins, revealing the tools signing secret, changing the password — need the account password within the last 15 minutes (`403` with `X-Relay-Reauth: required`; the CLI asks for it and retries). Changing the password signs out every other device. Users see their devices with `relay sessions` and can revoke one or all.

**Email confirmation and password reset.** A new account gets a confirmation link (valid 24 hours) and cannot sign in until it is opened; signing in before that resends it. An unconfirmed address can be signed up again by someone else, and whoever confirms it keeps it, so registering another person's email first does not lock them out. *Forgot your password?* on the sign-in page (or `relay password reset`) emails a reset link (valid 1 hour, single use); the answer is the same whether or not the account exists. A reset signs out every device, confirms the email and lifts a login lockout. Links are stored as hashes; requesting a new one cancels the previous one. At most 5 emails per address per hour and 10 reset requests per client address per hour. In development (no SMTP), read the links with `docker compose -f infra/docker/docker-compose.yml logs gateway`. Accounts that existed before confirmation was added count as confirmed.

## Calls to customers' tools services

- **Who is asking.** A business's server may start a session for one of its users (`POST /v1/sessions` with a secret key and `user`). The user is stored on the session, sent as `X-Relay-User` on every tool call, recorded on approval decisions (`end_user_id` in the audit trail) and limited to 30 sessions per minute per user.
- **Signatures.** Every call carries `X-Relay-Signature-V2`, covering timestamp, operation (`tools.list` / `tools.call:<name>`), session, user and body, plus the older body-only `X-Relay-Signature` for existing integrations.
- **Address pinning.** Outside `RELAY_ALLOW_PRIVATE_TOOLS_URLS`, every call (and discovery) resolves the tools host first, refuses it if any address is not public, and connects to exactly the checked address with TLS verified against the real host name — a domain re-pointed at an internal address later (DNS rebinding) is refused on the next call. Each agent has its own HTTP client, so connections are never shared between hosts.
- **Session tokens** are accepted as `Authorization: Bearer`, as the `relay.token.<token>` WebSocket subprotocol, and (for SDK 0.1.x) as `?token=`, which the log handler redacts.
- **Leaked secret keys.** Each secret key remembers the last 20 addresses it was used from; a new address after the first emails the account owner (at most 3 alerts per key per hour). Needs `RELAY_TRUST_PROXY_HEADERS=1` behind a proxy, or every request looks like it comes from the proxy.

