# Relay

Domain-agnostic realtime agent platform (Relay Protocol + adapter ports + session runtime). **POC:** Phases **0–7 signed off**; **Phases 8–11 implemented** — sign-off tracked in [plans/ACCEPTANCE_TRACKER.md](./plans/ACCEPTANCE_TRACKER.md) and [plans/STATUS.md](./plans/STATUS.md). Timeline: `GET /dev/sessions/{id}/timeline?token=…`. Voice UAT: [plans/UAT_VOICE_SCRIPT.md](./plans/UAT_VOICE_SCRIPT.md).

- Product spec: [`Relay_Final_PRD_16_Pages.docx`](./Relay_Final_PRD_16_Pages.docx)
- Plans index: [`plans/README.md`](./plans/README.md)
- Live progress: [`plans/STATUS.md`](./plans/STATUS.md)
- Testing / sign-off: [`plans/TESTING.md`](./plans/TESTING.md)
- Models & API keys: [`plans/MODELS_AND_KEYS.md`](./plans/MODELS_AND_KEYS.md)

## Repository layout (PRD §13.2)

```text
packages/protocol/       RP schemas and validation
packages/python-sdk/     Shared event models for runtime/agents
packages/web-sdk/        Client SDK (session, transport, events, state)
runtime/                 SessionManager, TurnManager, ports, core
adapters/                Pipecat, models, speech, persistence, tools — implementation only
services/gateway/        FastAPI entrypoint (WebSocket / WebRTC)
examples/mortgage-servicing/
  frontend/              Next.js reference UI (Web SDK only)
  agent/                 MortgageServicingAgent (external to core)
  tools/                 Read-only mortgage API (search / get case)
infra/docker/            Redis, PostgreSQL, gateway, mortgage-tools
```

Mortgage app details: [`examples/mortgage-servicing/README.md`](./examples/mortgage-servicing/README.md).

## Quick start (local demo)

**Ports:** gateway `8080`, mortgage tools `8090`, UI `3000`.

### 1. Docker (gateway + data + tools)

```bash
cp infra/docker/.env.example infra/docker/.env   # add OPENAI_API_KEY, DEEPGRAM_API_KEY for live voice/LLM
docker compose -f infra/docker/docker-compose.yml up --build
curl http://localhost:8080/health
curl http://localhost:8090/health
```

### 2. Mortgage frontend

```bash
cp examples/mortgage-servicing/frontend/.env.example examples/mortgage-servicing/frontend/.env.local
pnpm install
pnpm --filter @relay/mortgage-frontend dev
```

Open [http://localhost:3000](http://localhost:3000): connect, text chat, voice (mic), search customer **Rajesh Sharma**, open case — shared state syncs with the agent.

### Python (tests & gateway dev)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e "packages/protocol[dev]" -e packages/python-sdk -e runtime \
  -e adapters/realtime/pipecat -e adapters/models/openai -e adapters/agents/reference \
  -e adapters/tools/http \
  -e examples/mortgage-servicing/tools -e examples/mortgage-servicing/agent \
  -e adapters/persistence/postgres -e adapters/persistence/redis \
  -e adapters/speech/silero -e adapters/speech/deepgram \
  -e "services/gateway[dev]"
pytest packages/protocol/tests runtime/tests services/gateway/tests \
  adapters/realtime/pipecat/tests adapters/speech/deepgram/tests -q
```

Phase 5 E2E (gateway + UI running): `pnpm --filter @relay/mortgage-frontend exec playwright test e2e/phase-05-actions.spec.ts`

Phase 6 E2E: `PLAYWRIGHT_E2E=1 pnpm --filter @relay/mortgage-frontend exec playwright test e2e/phase-06-tools.spec.ts`

Phase 9 E2E: `PLAYWRIGHT_E2E=1 pnpm --filter @relay/mortgage-frontend exec playwright test e2e/phase-09-hitl.spec.ts`

Phase 11 staged UAT: `PLAYWRIGHT_E2E=1 pnpm --filter @relay/mortgage-frontend exec playwright test e2e/phase-11-uat-demo.spec.ts`

Session timeline export: `python scripts/export_session_timeline.py --session-id <id> --token <dev_token>`

## Environment

### Server (`infra/docker/.env`)

Copy from [`infra/docker/.env.example`](./infra/docker/.env.example). Required for live agent/voice paths:

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | LLM (text + voice agent) |
| `OPENAI_MODEL` / `RELAY_OPENAI_MODEL` | Model id (default `gpt-5.4-mini`) |
| `DEEPGRAM_API_KEY` | STT + streaming TTS (Phase 3+) |
| `DEEPGRAM_STT_MODEL` / `DEEPGRAM_TTS_*` | Deepgram product settings |
| `RELAY_DEV_TOKEN_SECRET` | Dev session token signing |

Compose sets `RELAY_MORTGAGE_TOOLS_URL=http://mortgage-tools:8090` for the gateway. Override for non-Docker gateway: `RELAY_MORTGAGE_TOOLS_URL=http://localhost:8090`.

### Frontend (`examples/mortgage-servicing/frontend/.env.local`)

| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_GATEWAY_URL` | Gateway base URL (default `http://localhost:8080`) |
| `NEXT_PUBLIC_PROJECT_ID` | Relay project id |
| `NEXT_PUBLIC_AGENT_ID` | Agent id for dev session |
