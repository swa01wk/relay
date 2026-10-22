# Reference

Everything an app or tools service touches. `<gateway>` is your Relay address (the `gatewayUrl` you pass to the SDK).

## Gateway HTTP / WebSocket

| Method & path | Purpose |
|---|---|
| `GET /health`, `GET /ready` | Liveness / readiness |
| `POST /v1/sessions` | Start a session. `Authorization: Bearer <project key>` (publishable `rpk_…` from a browser, secret `rsk_…` from a server), body `{"agent_id", "user"?}` — `user` (`{"id", "attributes"?}`, secret keys only; `403` with a publishable key) is sent to your tools service as `X-Relay-User` on every call. The key decides the project, and `agent_id` must be one of that project's agents (`404` otherwise; `409` when the project has no model API key). Returns `session_id`, `token`, `token_expires_at`, `events`. `403` when a publishable key is used from an origin outside the project's allowed origins |
| `POST /v1/auth/device` · `POST /v1/auth/device/token` · `GET/POST /v1/auth/device/verify` | `relay login`: start (returns `device_code`, `user_code`, `verification_uri_complete`), poll with `{"device_code", "client_name"?}` (`{"status":"pending"}` then, once, `{"status":"approved","token":"rat_…","email","project"}`), and the browser approval page (sign in or sign up) |
| `GET /v1/me` · `POST /v1/auth/logout` | Account behind an account token; sign out this device (`{"everywhere": true}`: every device) |
| `GET /v1/auth/sessions` · `DELETE /v1/auth/sessions/{id}` | Devices signed in to the account (name, last use and address, expiry); sign one out |
| `POST /v1/auth/reauth` · `POST /v1/auth/password` | Confirm the password for this device (`{"password"}`), needed for changes when the gateway answers `403` with `X-Relay-Reauth: required`; change the password (`{"current_password", "new_password"}`) — signs out every other device |
| `GET/POST /v1/projects` · `PUT /v1/projects/{id}/origins` | List/create projects; set the origins allowed to use publishable keys (`{"allowed_origins": [...]}`; empty = any origin) |
| `GET/POST /v1/projects/{id}/keys` · `DELETE /v1/projects/{id}/keys/{key_id}` | List, create (`{"kind": "publishable"\|"secret", "name"}`; the response is the only time `key` is returned) and revoke project keys. Account token required |
| `GET/POST /v1/projects/{id}/agents` · `DELETE /v1/projects/{id}/agents/{agent_id}` | A project's agents. Push with `{"manifest": "<yaml text>", "system_prompt": "<text>"?}`; the gateway calls `GET <tools_url>/tools` and answers `{agent_id, tools_url, model, updated_at, tools: [names]}` or `400` with the reason. Account token required |
| `GET /v1/projects/{id}/secrets` · `PUT/DELETE /v1/projects/{id}/secrets/openai` | The project's model API key: set with `{"value"}`; listing returns `{name, set, hint, updated_at}` only — the value is never returned. `503` when secret storage is not configured on the gateway |
| `POST /v1/projects/{id}/tools-signing-secret?rotate=` | The secret Relay signs this project's tool calls with (`rts_…`), created on first use |
| `GET /v1/projects/{id}/sessions?limit=` | The project's recent sessions (`relay logs`), most recent first: `session_id`, `agent_id`, `started_at`, `last_event_at`, `event_count`, `turns`, `errors`, `ended`, `live`. `limit` 1–200 (default 50). Account token required |
| `GET /v1/projects/{id}/sessions/{session_id}` | One session (`relay logs <id>`): `agent_id`, `started_at`, `last_event_at`, `live`, `turns` (`user_text`, `assistant_text`, `heard_text`, `tool_names`, `event_types`), `errors` (`at`, `turn_id`, `code` — a `SESSION_ERROR` code or `tool_failed:<tool>` — and `message`), `approvals` (`tool_name`, `decision`, `via`, `outcome`, `error`, …) and `usage` (`model_calls`, `input_tokens`, `output_tokens`, `cached_input_tokens`, `total_tokens`, `cost_usd`?). A session of another project is `404`. Account token required |
| `GET /v1/projects/{id}/usage?days=` | Activity over the last `days` (1–90, default 7; `relay usage`): `total`, `by_day` (UTC dates) and `by_agent`, each with `sessions`, `turns`, `errors` and `model` (the `usage` fields above); `by_model`; `tools` (`name`, `calls`, `failures`, `avg_ms`, `max_ms`); `truncated` is `true` when the period had too many events to count them all. Account token required |
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
| `FILL_FORM` | `{form_id, values}` — values the user gave in the chat for a form on screen, already matched to its fields | `registerFormFill(session, ({ formId, values }) => …)` — merge into the form, never submit; throw if the form is not open. Offered to the model as `fill_form` only while a form it showed is unsubmitted |
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

## SDK exports (`@sumukhj1219-wkt-org/relay-web-sdk`)

Session: `createRelaySession(options)` → `connect`, `disconnect`, `sendText`, `on`, `onConnectionState`, `onVoiceState`, `onAudioLevel`, `connectVoice`, `disconnectVoice`, `setMicMuted`, `cancelVoiceUtterance`, `registerAction`, `sendState`, `onStateConflict`, `sendEvent`, `onApprovalRequested`, `grantApproval`, `rejectApproval`, and getters `connectionState`, `voiceState`, `sessionId`, `stateVersion`. Also `fetchHealth(gatewayUrl)`, `createDevSession(...)`.

Surfaces: `registerPlaygroundSurfaces`, `submitForm`, `registerFormFill` (`UiFormFill`), `surfaceToCsv`, `normalizeUiSurface`, `normalizePresentUiParams`, `normalizeTableSurface`, `normalizeChartSurface`, constants `PRESENT_UI_ACTION`, `SHOW_TABLE_ACTION`, `FORM_SUBMIT_EVENT`, `FILL_FORM_ACTION`, and the `Ui*` types.

## Limits and sign-in rules

- Over a rate limit the gateway answers `429` with a `Retry-After` header (seconds). Starting sessions: 120 per minute per key; with a publishable key also 30 per minute per visitor address.
- 5 wrong passwords lock that sign-in for 15 minutes.
- New accounts confirm their email from a link before the first sign-in. Forgot the password? Use the link on the sign-in page (or `relay password reset`); a reset signs out every device.
- CLI tokens expire after 30 days, or 14 days unused; sign in again with `relay login`.
- Creating keys, changing the model key, agents or allowed origins, and showing the tools signing secret need the password from the last 15 minutes. The CLI asks for it when needed.
- Session tokens are sent as `Authorization: Bearer <token>` (HTTP) and as the WebSocket subprotocol `relay.token.<token>` next to `relay.v1`; the SDK does this for you.
- `relay keys list` shows where each key was last used from. A secret key used from an address it has not used before emails the account owner.

