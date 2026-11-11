# Relay

Domain-agnostic platform for **realtime voice + text AI assistants that drive an app's UI**, delivered as a hosted service with an SDK (`@sumukhj1219-wkt-org/relay-web-sdk`) and a CLI (`relay login`): browser apps use `@sumukhj1219-wkt-org/relay-web-sdk`; a Python gateway runs sessions (speech → LLM + tools → speech), streams typed Relay Protocol events, renders AI-generated tables/charts/forms through the app's own components, changes what is already on screen, and asks for human approval before any data changes.

**Status:** proof of concept. PRD phases 0–7 signed off, 8–11 implemented ([plans/STATUS.md](./plans/STATUS.md), [plans/ACCEPTANCE_TRACKER.md](./plans/ACCEPTANCE_TRACKER.md)).

**Coding agents / IDEs:** read [AGENTS.md](./AGENTS.md) (working on this repo) or [packages/web-sdk/AGENTS.md](./packages/web-sdk/AGENTS.md) (integrating Relay into an app). LLM doc index: [llms.txt](./llms.txt).

- Integration guides: [frontend](./packages/web-sdk/docs/01-frontend.md) · [backend](./packages/web-sdk/docs/02-backend.md) · [reference + configuration](./packages/web-sdk/docs/03-reference.md)
- Product spec: [`Relay_Final_PRD_16_Pages.docx`](./Relay_Final_PRD_16_Pages.docx) · Plans: [`plans/README.md`](./plans/README.md)

## Repository layout

```text
packages/protocol/        Relay Protocol: event catalog, envelope, JSON schema
packages/python-sdk/      Protocol models re-exported for Python agents
packages/web-sdk/         Browser SDK + agent docs (AGENTS.md, docs/)
runtime/                  SessionManager, turns, ToolUsingAgent, tools, approvals, ports
adapters/                 Pipecat WebRTC, OpenAI, Deepgram, Silero, Postgres, Redis, HTTP tools
packages/cli/             `relay` CLI: login, projects, API keys
services/gateway/         FastAPI gateway: controllers / services / repositories (HTTP, WebSocket, WebRTC, agents)
agents/                   Declarative agents (*.yaml + prompts) loaded by the gateway
examples/sales-crm/       Primary example: Next.js 16 + shadcn dashboard (frontend/), tools service (tools/)
examples/mortgage-servicing/  Custom Python agent example (approve → commit → verify)
infra/docker/             Compose stack and Dockerfiles
infra/observability/      Prometheus alert rules, Grafana dashboard
plans/                    PRD phases, status, decisions, UAT scripts
```

## Quick start

**Ports:** gateway `8080` · mortgage tools `8090` · CRM tools `8091` · store API `8092` · mortgage UI `3000` · CRM UI `3002` · website `3003` · storefront `3004`.

```bash
# 1. Server: gateway + Postgres + Redis + example tools services
cp infra/docker/.env.example infra/docker/.env      # set OPENAI_API_KEY (and DEEPGRAM_API_KEY for voice)
docker compose -f infra/docker/docker-compose.yml up -d --build
curl http://localhost:8080/health

# 2. Frontends
pnpm install
pnpm --filter @relay/crm-frontend dev               # http://localhost:3002  (Sales CRM)
pnpm --filter @relay/mortgage-frontend dev          # http://localhost:3000  (mortgage servicing)
```

Try in the CRM assistant panel: "Chart our pipeline by stage", "Show deals of at least $70K" (filters the existing table), "Compare Northwind Logistics and Cobalt Financial".

Operations:
- Rebuild after changing Python code: `docker compose -f infra/docker/docker-compose.yml up -d --build gateway`
- After editing `infra/docker/.env`: `… up -d --force-recreate gateway`
- Add an agent: put `agents/<id>.yaml` + prompt file, restart the gateway, check the log for `agent <id> loaded` ([agents/README.md](./agents/README.md))
- Session timeline (debugging): `GET /dev/sessions/{id}/timeline?token=…`

## Python (tests and gateway development)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e "packages/protocol[dev]" -e packages/python-sdk -e runtime \
  -e adapters/realtime/pipecat -e adapters/models/openai -e adapters/agents/reference -e adapters/tools/http \
  -e adapters/persistence/postgres -e adapters/persistence/redis -e adapters/speech/silero -e adapters/speech/deepgram \
  -e adapters/observability/prometheus -e adapters/observability/otel \
  -e examples/mortgage-servicing/tools -e examples/mortgage-servicing/agent -e examples/sales-crm/tools \
  -e "services/gateway[dev]"
pytest packages/protocol/tests runtime/tests services/gateway/tests \
  adapters/realtime/pipecat/tests adapters/speech/deepgram/tests adapters/observability -q
```

Mortgage end-to-end suites (needs the stack running): `PLAYWRIGHT_E2E=1 pnpm --filter @relay/mortgage-frontend exec playwright test e2e/<spec>.spec.ts`.

## Environment

Server variables go in `infra/docker/.env` (copy from [`.env.example`](./infra/docker/.env.example)); the full list with defaults is in the [operator guide](./docs/operating-the-gateway.md#configuration). The essentials:

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | LLM (text and voice) |
| `RELAY_OPENAI_MODEL` / `OPENAI_MODEL` | Model id (code default `gpt-4o-mini`) |
| `DEEPGRAM_API_KEY` | Speech-to-text and text-to-speech |
| `RELAY_AGENTS_DIR` | Agent manifests folder (Compose mounts `agents/` at `/app/agents`) |

Compose also sets `RELAY_DATABASE_URL`, `RELAY_REDIS_URL`, `RELAY_MORTGAGE_TOOLS_URL`, `RELAY_CRM_TOOLS_URL` and `RELAY_SHOP_TOOLS_URL` for the gateway.

Frontends (`.env.local` in each app): `NEXT_PUBLIC_GATEWAY_URL` (default `http://localhost:8080`), `NEXT_PUBLIC_PROJECT_ID`, `NEXT_PUBLIC_AGENT_ID` (`sales-crm` for the CRM). The CRM app also reads `CRM_TOOLS_URL` (default `http://localhost:8091`) server-side.
