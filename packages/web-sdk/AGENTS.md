# @relay/web-sdk — instructions for coding agents

You are integrating **Relay**: a voice + text AI assistant that answers from the app's own data and drives the app's UI (tables, charts, forms, comparisons, …). Read this file fully, then the guide for your task. Do not guess APIs — every name you need is in these docs and in `src/index.ts` / `src/ui-surfaces.ts`.

## Pick the guide for the task

| Task | Read |
|---|---|
| Add the Relay assistant (chat, voice, AI-rendered UI) to a web app | [docs/01-frontend.md](docs/01-frontend.md) |
| Give the assistant access to a new domain's data (tools service + agent manifest — no Python) | [docs/02-backend.md](docs/02-backend.md) |
| Look up an event, surface spec, error code or HTTP endpoint | [docs/03-reference.md](docs/03-reference.md) |

A complete new integration needs **both** guides: backend first (so the agent exists), then frontend.

## The model in one picture

```
Browser app ──(@relay/web-sdk)──▶ Relay gateway ──▶ agent (LLM) ──▶ tools service (your data)
   renders UI        WebSocket + WebRTC        runtime      decides tool calls   POST /tools/{name}
```

Who defines what:

- **Tools** (data operations such as `list_deals`) — the developer, on the **backend**: a tools service in any language that also describes its tools (`GET /tools`: name, description, JSON schema, classification).
- **Tool calls** — nobody writes these. The **LLM** decides at runtime which tool to call with which arguments.
- **The agent** — backend: one YAML manifest (`agent_id`, tools URL, system prompt) in the gateway's `agents/` folder. No Python; Relay discovers the tools.
- **UI actions + renderers** — frontend: the app registers handlers (`registerAction`, `registerPlaygroundSurfaces`) and draws surfaces with its own components.
- The **SDK never renders and never holds AI logic or secrets**. It connects, streams events, acknowledges actions, versions shared state, handles voice, and normalizes AI-generated UI into typed data.

## Rules that are easy to get wrong

1. Create the session in **client-side code only** (browser APIs). In Next.js/React this means a `"use client"` component.
2. **Register every handler before `connect()`** (`registerPlaygroundSurfaces`, `registerAction`, `on(...)`), or early events are missed.
3. `connect()` (WebSocket) must succeed before `connectVoice()` (WebRTC audio). Voice needs a user click (browser mic permission).
4. Handle `SESSION_ERROR` (`payload.code`, `payload.message`): show the message and stop any "thinking" indicator. Track busy state with `TURN_STARTED` / `TURN_COMPLETED`.
5. Render **every** surface kind: `table`, `chart`, `kv`, `cards`, `comparison`, `markdown`, `notice`, `form`. Never render model output as raw HTML (`markdown` must go through a markdown renderer that ignores HTML).
6. Expose existing screen components to the agent with `registerAction(name, handler, spec)` and report what is visible with `sendState` — the agent then filters/updates what is on screen instead of drawing duplicates (frontend guide §4).
7. Forms: a form with `submitTool` is bound to a backend write tool — submitting **saves** through that tool (the submit is the user's approval); show Saving → Saved/failed from `COMMIT_VERIFIED` / `ERROR` (`commit_failed`) events carrying `payload.form_id`, allow retry on failure, and refresh your data after `COMMIT_VERIFIED`. A form **without** `submitTool` only sends its values to the assistant — never show "saved" for those.
8. Tools that change data (refunds, updates) must be published with `"classification": "side_effecting"` in `GET /tools`; the model can only *propose* them, and they run only after a human approves (`onApprovalRequested` → `grantApproval`; the assistant then confirms in a follow-up message). Never mark them `read_only`.
9. Keys (OpenAI, Deepgram) stay on the server. The browser only holds the short-lived session token the gateway issues.

## Reference implementation

The Relay repo's Sales CRM is the canonical, working example of everything above: `examples/sales-crm/frontend` (shadcn dashboard + assistant panel), `examples/sales-crm/tools` (tools service) and `agents/sales-crm.yaml` (the agent). Relay is self-hosted: the customer runs the gateway image. When unsure, mirror the example.
