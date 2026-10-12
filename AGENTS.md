# Relay — instructions for coding agents working on this repository

Relay is a **self-hosted**, domain-agnostic platform for realtime voice + text AI assistants that drive an app's UI. Browser apps use `@relay/web-sdk`; a Python gateway runs sessions (speech → LLM + tools → speech) and streams typed Relay Protocol (RP) events. Status: proof of concept.

- **Integrating Relay into an app** (frontend, tools service, agent manifest)? Read [packages/web-sdk/AGENTS.md](packages/web-sdk/AGENTS.md) instead — it is the integration guide.
- **Changing Relay itself** (runtime, gateway, SDK, adapters, examples)? This file.
- Doc index for LLMs: [llms.txt](llms.txt).

## Layout

| Path | What | Language |
|---|---|---|
| `packages/protocol/` | RP event catalog, envelope, JSON schema | Python |
| `packages/web-sdk/` | Browser SDK (session, WebSocket/WebRTC, actions, state, surfaces) + agent docs (`AGENTS.md`, `docs/`) | TypeScript |
| `runtime/` | `SessionManager` (one actor queue per session), turns, `ToolUsingAgent`, tool registry/executor, approvals (HITL), ports | Python |
| `adapters/` | Port implementations: Pipecat SmallWebRTC, OpenAI, Deepgram, Silero, Postgres, Redis, HTTP tools; `observability/` (Prometheus metrics, OpenTelemetry traces — subscribers on the event stream) | Python |
| `services/gateway/` | FastAPI app: routes, wiring (`deps.py`), agent manifests loader (`manifests.py`) | Python |
| `agents/` | Declarative agents (`*.yaml` + prompt files), mounted into the gateway | YAML |
| `examples/sales-crm/` | **Primary reference**: `frontend/` (Next.js 16 + shadcn), `tools/` (tools service) — agent is `agents/sales-crm.yaml` | TS / Python |
| `examples/mortgage-servicing/` | Custom Python agent example (deterministic routes, approve → commit → verify) | TS / Python |
| `infra/docker/` | Compose stack, Dockerfiles, `.env`; `docker-compose.observability.yml` (optional Prometheus + Grafana) | — |
| `infra/observability/` | Prometheus scrape config + alert rules, Grafana dashboard (a test checks they only use exported metrics) | YAML / JSON |
| `plans/` | PRD phases, status, decisions, UAT scripts | Markdown |

## Run

```bash
cp infra/docker/.env.example infra/docker/.env        # set OPENAI_API_KEY (+ DEEPGRAM_API_KEY for voice)
docker compose -f infra/docker/docker-compose.yml up -d --build   # gateway :8080, postgres, redis, mortgage-tools :8090, crm-tools :8091
pnpm install
pnpm --filter @relay/crm-frontend dev                 # http://localhost:3002
pnpm --filter @relay/mortgage-frontend dev            # http://localhost:3000
```

- Python code runs inside the images: after changing `runtime/`, `adapters/`, `services/gateway/` or `examples/*/tools`, rebuild (`up -d --build <service>`).
- After editing `infra/docker/.env`: `up -d --force-recreate gateway` (env is read at container creation).
- After editing `agents/*.yaml`: restart the gateway; check its log for `agent <id> loaded … (<n> tools)` or `agent manifest skipped: <reason>`.
- All configuration variables: [packages/web-sdk/docs/03-reference.md#configuration-self-hosted-gateway](packages/web-sdk/docs/03-reference.md).

Local Python environment (tests, running the gateway outside Docker):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e "packages/protocol[dev]" -e packages/python-sdk -e runtime \
  -e adapters/realtime/pipecat -e adapters/models/openai -e adapters/agents/reference -e adapters/tools/http \
  -e adapters/persistence/postgres -e adapters/persistence/redis -e adapters/speech/silero -e adapters/speech/deepgram \
  -e adapters/observability/prometheus -e adapters/observability/otel \
  -e examples/mortgage-servicing/tools -e examples/mortgage-servicing/agent -e examples/sales-crm/tools \
  -e "services/gateway[dev]"
```

## Test — run what covers your change, not everything

```bash
pytest runtime/tests/test_<area>.py -q                 # e.g. test_client_actions, test_model_proposed_actions, test_generative_ui
pytest services/gateway/tests/test_agent_manifests.py -q
pnpm --filter @relay/web-sdk test && (cd packages/web-sdk && npx tsc --noEmit)
(cd examples/sales-crm/frontend && pnpm exec tsc --noEmit -p . && pnpm exec eslint .)
```

- Full Python suite (~30 s): `pytest packages/protocol/tests runtime/tests services/gateway/tests adapters/realtime/pipecat/tests adapters/speech/deepgram/tests adapters/observability -q`. Run it before finishing a large change, not after every edit.
- Do not start Playwright suites unless asked (slow; needs the full stack).
- Test the agent loop with a scripted `ModelProvider` (yield `{"type": "tool_calls", ...}` / `{"type": "token", ...}`), never the real API. Examples: `runtime/tests/test_model_proposed_actions.py`, `runtime/tests/test_client_actions.py`.
- Gateway tests set `RELAY_AGENTS_DIR` to a non-existent folder and `CRM_DB_PATH` to a temp file (`services/gateway/tests/conftest.py`) so startup never calls real tools services and tests never write a `crm.db` into the repo.

## Architecture rules (CI and reviews enforce these)

- `packages/protocol` and the Web SDK's public API must not reference adapter/framework types (Pipecat, OpenAI, Deepgram). `import-linter` runs in CI.
- `runtime/` is domain-agnostic: no CRM/mortgage logic. Domains live in `examples/` or as manifests in `agents/`.
- Adapters implement `runtime/src/relay_runtime/ports/*`; the runtime depends only on ports.
- The SDK never renders; apps own UI. Model output is never rendered as raw HTML.
- Observability is derived from events (`event_gateway.subscribe("*", …)`), not sprinkled through the runtime: to measure something new, emit an event or `METRIC` and map it in the bridges. Never put message text, tool arguments or results in metrics labels or span attributes; cap label values (client- and model-supplied strings are unbounded).
- Side-effecting tools run only with a granted approval for that exact tool (`RegistryToolExecutor` + `HITLManager`); the model can only propose them or show a tool-bound form (submit = approval). Form→tool bindings are recorded server-side when `PRESENT_UI` is published (`SessionManager._remember_form_bindings`). Custom agents with their own approval flow pass `ToolUsingAgent(..., allow_proposals=False)`, which also strips `submit_tool`.
- Every public behaviour change updates, in the same change: `packages/web-sdk/AGENTS.md` + `docs/`, `llms.txt`, and (if relevant) `agents/README.md`. Doc code samples must be verified against the real API.

## Pitfalls already hit here

- The WebSocket read loop (`services/gateway/src/relay_gateway/routes/ws.py`) must never await work queued on the session actor — spawn a task (otherwise acks and human edits stall behind a running turn).
- `session.context_lock` is an `asyncio.Lock` (not re-entrant). Approval grant/reject run while holding it; code called from there must not acquire it again.
- A failed model/tool call must still complete the turn (`SESSION_ERROR` `turn_failed` + `TURN_COMPLETED`), or the session rejects every later message.
- SDK sends (`sendState`, `sendText`, …) throw before `connect()` resolves; `SESSION_READY` is delivered from the HTTP session response, before the socket opens.
- Event sequence numbers start at 0; stores' `after_sequence` defaults to -1.
- The event store is read only by operator views (timeline, `/admin`); redaction (`stored_copy` on `PersistingEventGateway`) changes the stored copy, never the live stream. If you start replaying stored events to clients, redaction would leak placeholders into the app — revisit it first.
- Two test files with the same basename in different `tests/` folders break a combined pytest run (no `__init__.py`); give test modules unique names.
- Next.js 16 (CRM app) and TanStack Table v9 differ from older versions — read `node_modules/next/dist/docs/` and `node_modules/@tanstack/react-table/skills/` before changing that code.
- Session tokens travel in URLs (`?token=`). The gateway's log handler redacts them (`services/gateway/src/relay_gateway/logging_setup.py`); uvicorn must keep running with `log_config=None` or its own handlers bypass the redaction. Log ids as `session_id=… turn_id=…` — the JSON formatter turns those pairs into fields.

## Known gaps (don't assume these exist)

- No production auth: browsers mint dev sessions (`POST /dev/sessions`); per-deployment API keys are planned. Operator endpoints use static tokens (`RELAY_ADMIN_TOKEN`, `RELAY_METRICS_TOKEN`).
- No end-user identity: the audit trail identifies sessions, not people.
- `EventStore.list_sessions` on Postgres aggregates the whole table (fine with retention set; needs a sessions table at scale).
- Tool calls to tools services are unauthenticated and carry no end-user identity.
- CRM writes work (SQLite via `CRM_DB_PATH`, Docker volume `crm-data`; `down -v` resets to the seed). Approval auth is a proof-of-concept token (`RELAY_DEV_APPROVER_TOKEN`).
- `@relay/web-sdk` is not published to npm (workspace package only); the gateway image is built locally, not published.
- The voice reply path has not received the text-turn failure handling.
