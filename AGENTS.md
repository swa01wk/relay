# Relay — instructions for coding agents working on this repository

Relay is a domain-agnostic platform for realtime voice + text AI assistants that drive an app's UI, delivered as a **hosted service with an SDK and a CLI**: the operator runs the gateway; app developers install `@sumukhj1219-wkt-org/relay-web-sdk`, sign in with `relay login` and use a project API key. A Python gateway runs sessions (speech → LLM + tools → speech) and streams typed Relay Protocol (RP) events. Status: proof of concept; the hosted service is not deployed yet (everything runs locally with Docker Compose).

- **Integrating Relay into an app** (frontend, tools service, agent manifest)? Read [packages/web-sdk/AGENTS.md](packages/web-sdk/AGENTS.md) instead — it is the integration guide.
- **Changing Relay itself** (runtime, gateway, SDK, adapters, examples)? This file.
- Doc index for LLMs: [llms.txt](llms.txt).

## Layout

| Path | What | Language |
|---|---|---|
| `packages/protocol/` | RP event catalog, envelope, JSON schema | Python |
| `packages/cli/` | `@sumukhj1219-wkt-org/relay-cli` — the `relay` command line: `init` (writes `AGENTS.md`/`CLAUDE.md`/Cursor-rule pointers to the installed SDK docs), `login` (browser device-code flow), projects, API keys, allowed origins. Plain Node ESM, no build step | JavaScript |
| `packages/web-sdk/` | `@sumukhj1219-wkt-org/relay-web-sdk` — browser SDK (session, WebSocket/WebRTC, actions, state, surfaces) + agent docs (`AGENTS.md`, `docs/`). Apps import the build in `dist/` (made on `pnpm install`); after editing `src/` run `pnpm --filter @sumukhj1219-wkt-org/relay-web-sdk build` | TypeScript |
| `runtime/` | `SessionManager` (one actor queue per session), turns, `ToolUsingAgent`, tool registry/executor, approvals (HITL), ports | Python |
| `adapters/` | Port implementations: Pipecat SmallWebRTC, OpenAI, Deepgram, Silero, Postgres, Redis, HTTP tools; `observability/` (Prometheus metrics, OpenTelemetry traces — subscribers on the event stream) | Python |
| `services/gateway/` | FastAPI app in three layers — `controllers/` (HTTP + WebSocket), `services/` (logic, incl. the agent manifest loader `agent_service.py`), `repositories/` (stores) — wired in `core/container.py` | Python |
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
- The compose stack sets `RELAY_DEV_SESSIONS=1`, so the example apps start sessions without a key and use the gateway's own agents. To exercise the customer path (`R="node packages/cli/bin/relay.mjs"`): `$R login`, `$R secrets set openai`, `$R agents push <manifest>` (in compose a tools URL like `http://crm-tools:8091` is allowed), `$R keys create --kind publishable`, then set `NEXT_PUBLIC_RELAY_API_KEY` and the agent id in the app.
- After editing `agents/*.yaml`: restart the gateway; check its log for `agent <id> loaded … (<n> tools)` or `agent manifest skipped: <reason>`.
- Configuration variables, operator endpoints (`/admin`, `/metrics`), observability and custom Python agents: [docs/operating-the-gateway.md](docs/operating-the-gateway.md). The docs under `packages/web-sdk/` ship to customers on npm: keep them free of operator settings, repo paths and example domains (a test enforces it).

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
pnpm --filter @sumukhj1219-wkt-org/relay-web-sdk test && (cd packages/web-sdk && npx tsc --noEmit)
pnpm --filter @sumukhj1219-wkt-org/relay-cli test
(cd examples/sales-crm/frontend && pnpm exec tsc --noEmit -p . && pnpm exec eslint .)
```

- Full Python suite (~30 s): `pytest packages/protocol/tests runtime/tests services/gateway/tests adapters/realtime/pipecat/tests adapters/speech/deepgram/tests adapters/observability -q`. Run it before finishing a large change, not after every edit.
- Do not start Playwright suites unless asked (slow; needs the full stack).
- Test the agent loop with a scripted `ModelProvider` (yield `{"type": "tool_calls", ...}` / `{"type": "token", ...}`), never the real API. Examples: `runtime/tests/test_model_proposed_actions.py`, `runtime/tests/test_client_actions.py`.
- Gateway tests start with empty rate-limit counters (autouse fixture in `conftest.py`); a test that needs many sign-ups from one address must expect `429` or reuse one `relay login` start. Gateway tests for the customer path use the `tenant_world` fixture (`conftest.py`): in-process fakes for customers' tools services and the model API. Gateway tests set `RELAY_DEV_SESSIONS=1`, `RELAY_AGENTS_DIR` to a non-existent folder and `CRM_DB_PATH` to a temp file (`services/gateway/tests/conftest.py`) so startup never calls real tools services and tests never write a `crm.db` into the repo.

## Architecture rules (CI and reviews enforce these)

- `packages/protocol` and the Web SDK's public API must not reference adapter/framework types (Pipecat, OpenAI, Deepgram). `import-linter` runs in CI.
- Everything outside `examples/` and `agents/` is domain-agnostic: no CRM/mortgage logic in `runtime/`, `adapters/`, the gateway, the SDK or the CLI (`test_runtime_and_published_packages_contain_no_example_domain`). The one exception is `services/gateway/.../core/example_agents.py`, which wires the mortgage example as the default agent only when `RELAY_EXAMPLE_MORTGAGE=1`. Domain behaviour after a saved change belongs in the agent (`AgentAdapter.state_after_commit`), not the runtime.
- Adapters implement `runtime/src/relay_runtime/ports/*`; the runtime depends only on ports.
- Gateway layers depend downwards only: controllers (HTTP shapes, no logic, no `relay_runtime`/adapter/repository imports) → services (logic; raise `core/errors.py`, never FastAPI types) → repositories (the only code that reads stores). `core/container.py` builds them all; `services/gateway/tests/test_layering.py` enforces it. New endpoint = controller function + service method; new stored data = repository.
- The SDK never renders; apps own UI. The one exception is the opt-in video avatar in the separate `@…/relay-web-sdk/avatar` entry point (`src/avatar.ts`); keep it out of the main entry so apps that don't use it never bundle it. Model output is never rendered as raw HTML.
- Observability is derived from events (`event_gateway.subscribe("*", …)`), not sprinkled through the runtime: to measure something new, emit an event or `METRIC` and map it in the bridges. Never put message text, tool arguments or results in metrics labels or span attributes; cap label values (client- and model-supplied strings are unbounded).
- Sign-in protection (`services/rate_limit_service.py`, `auth_service.py`): every unauthenticated or key-authenticated entry point takes a rate limit (`RateLimitService.take`); new limits go in the table at the top of `rate_limit_service.py`. CLI tokens are per device and expire; account endpoints that could hand a project to a token holder pass `sensitive=True` to `account_principal` (password within 15 minutes). Removing access (revoke a key, sign a device out) must never require it. Client addresses come only from `core/http.client_ip`. Emailed links are built only by `account_email_service.link_base` (never from the request's `Host` on a public gateway). Gateway tests run with `RELAY_EMAIL_VERIFICATION=off` except `test_email_verification_and_reset.py`.
- Auth: a key decides the project — never trust a client-supplied `project_id` outside `RELAY_DEV_SESSIONS`. Three key kinds (`models.py`): account token `rat_…` (CLI; manages projects/keys), secret `rsk_…` (server), publishable `rpk_…` (browser; can only start sessions, limited by the project's allowed origins). Only key hashes and scrypt password hashes are stored; a key's text appears once, in the create response. Another account's project must look exactly like a missing one (404).
- Tool calls (`adapters/tools/http`): sign with `signed_headers` (v2 covers operation, session, user and body — never add a header the tools service relies on without signing it); customer hosts go through `pinned_target` + `public_address` on every call; one HTTP client per tools host.
- Tenancy: a session started with a project key runs only on that project's agent, tools URL and model key (`ProjectAgentService`, wired through `SessionManager.runtime_resolver`); it never falls back to gateway-wide agents or the operator's model key. Customer manifests are parsed with `parse_manifest_text` — no `${VAR}` expansion, no file reads on the gateway. Customer-chosen URLs go through `check_tools_url` (SSRF). Secrets are encrypted by `SecretService` before a repository sees them and are never returned or logged (hint only).
- Side-effecting tools run only with a granted approval for that exact tool (`RegistryToolExecutor` + `HITLManager`); the model can only propose them or show a tool-bound form (submit = approval). Form→tool bindings are recorded server-side when `PRESENT_UI` is published (`SessionManager._remember_form_bindings`). Custom agents with their own approval flow pass `ToolUsingAgent(..., allow_proposals=False)`, which also strips `submit_tool`.
- Every public behaviour change updates, in the same change: `packages/web-sdk/AGENTS.md` + `docs/` (customer-facing), `docs/operating-the-gateway.md` (operator-facing), `llms.txt`, and (if relevant) `agents/README.md`. Doc code samples must be verified against the real API.

## Pitfalls already hit here

- The WebSocket read loop (`controllers/stream_controller.py` → `StreamService.handle_frame`) must never await work queued on the session actor — spawn a task (otherwise acks and human edits stall behind a running turn).
- `session.context_lock` is an `asyncio.Lock` (not re-entrant). Approval grant/reject run while holding it; code called from there must not acquire it again.
- A failed model/tool call must still complete the turn (`SESSION_ERROR` `turn_failed` + `TURN_COMPLETED`), or the session rejects every later message.
- SDK sends (`sendState`, `sendText`, …) throw before `connect()` resolves; `SESSION_READY` is delivered from the HTTP session response, before the socket opens.
- Event sequence numbers start at 0; stores' `after_sequence` defaults to -1.
- The event store is read only by operator views (timeline, `/admin`); redaction (`stored_copy` on `PersistingEventGateway`) changes the stored copy, never the live stream. If you start replaying stored events to clients, redaction would leak placeholders into the app — revisit it first.
- Two test files with the same basename in different `tests/` folders break a combined pytest run (no `__init__.py`); give test modules unique names.
- Next.js 16 (CRM app) and TanStack Table v9 differ from older versions — read `node_modules/next/dist/docs/` and `node_modules/@tanstack/react-table/skills/` before changing that code.
- SDK relative imports are written with the `.js` extension (`from "./ui-surfaces.js"`, the TypeScript ESM convention) so the built `.js` and `.d.ts` files reference real files. Extensionless or `.ts` imports publish a package whose types silently fall back to `any` for customers.
- Session tokens must never travel in URLs from new code: use `core/http.session_token` (Bearer header / `relay.token.*` WebSocket subprotocol). SDK 0.1.x still sends `?token=`; the gateway's log handler redacts it (`services/gateway/src/relay_gateway/core/logs.py`); uvicorn must keep running with `log_config=None` or its own handlers bypass the redaction. Log ids as `session_id=… turn_id=…` — the JSON formatter turns those pairs into fields.

## Known gaps (don't assume these exist)

- The hosted service is not deployed: no public gateway URL (the CLI defaults to `http://localhost:8080`), no HTTPS/TURN setup, no billing, no two-factor login. Emails (confirmation, password reset) need `RELAY_SMTP_HOST` and `RELAY_PUBLIC_URL`; without SMTP they are printed to the gateway log.
- Speech is still gateway-wide: voice sessions of every project use the operator's Deepgram key (only the LLM key is per project). Developers see their project's sessions and usage (`relay logs`, `relay usage`, read from the event log), but there is no metering for billing; `/metrics` has no project label.
- Only OpenAI keys can be stored. Restricting the gateway's outbound network is still recommended on top of per-call address pinning.
- `agents/*.yaml` on the gateway and the mortgage default agent serve dev sessions only (`RELAY_DEV_SESSIONS=1`).
- `?token=` in URLs is still accepted for SDK 0.1.x (newer SDKs use a header / WebSocket subprotocol); drop it once old SDKs are gone. Operator endpoints use static tokens (`RELAY_ADMIN_TOKEN`, `RELAY_METRICS_TOKEN`) and show every project.
- With no `RELAY_DATABASE_URL`, accounts and keys are kept in memory and lost on restart.
- End users are identified only when the business's server starts the session with `user`; browser-started (publishable key) sessions have no user.
- `EventStore.list_sessions` on Postgres aggregates the whole table (fine with retention set; needs a sessions table at scale).
- CRM writes work (SQLite via `CRM_DB_PATH`, Docker volume `crm-data`; `down -v` resets to the seed). Approval auth is a proof-of-concept token (`RELAY_DEV_APPROVER_TOKEN`).
- npm: the CLI is published as `@sumukhj1219-wkt-org/relay-cli`; the SDK is `@sumukhj1219-wkt-org/relay-web-sdk` (built to `dist/` by `prepare`; check `npm view` before assuming a version is live). Bump `version` before every publish. The gateway image is built locally, not published.
- The voice reply path has not received the text-turn failure handling.
