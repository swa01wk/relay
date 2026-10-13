# @sumukhj1219-wkt-org/relay-web-sdk

Browser SDK for Relay: connect an app to a Relay agent over WebSocket (+ WebRTC voice), stream the conversation, run UI actions, sync shared state with versioning, handle approvals, and receive AI-generated UI surfaces (`table`, `chart`, `kv`, `cards`, `comparison`, `markdown`, `notice`, `form`) as typed data the app renders with its own components. Framework-agnostic; plain ES modules with TypeScript types, no dependencies.

## For coding agents (Cursor, Claude Code, Codex, …)

Full integration instructions live in this package: [AGENTS.md](AGENTS.md) → [frontend guide](docs/01-frontend.md), [backend guide](docs/02-backend.md), [reference](docs/03-reference.md).

Point your project's agent at them once:

- **Codex / Cursor / most agents** — add to the project's `AGENTS.md`:
  `Before working on the Relay assistant, read node_modules/@sumukhj1219-wkt-org/relay-web-sdk/AGENTS.md and follow it.`
- **Claude Code** — add to the project's `CLAUDE.md`: `@node_modules/@sumukhj1219-wkt-org/relay-web-sdk/AGENTS.md`
- **Cursor rules** (optional) — `.cursor/rules/relay.mdc` with the same sentence.

## Quick look

```ts
import { createRelaySession, registerPlaygroundSurfaces } from "@sumukhj1219-wkt-org/relay-web-sdk"

const session = createRelaySession({ gatewayUrl, apiKey, agentId: "orders", transport: "small-webrtc" })  // apiKey: publishable key from `relay keys create`
registerPlaygroundSurfaces(session, ({ surfaces }) => render(surfaces))   // before connect()
session.on("RESPONSE_DELTA", (e) => appendToChat(String(e.payload.text ?? "")))
await session.connect()
session.sendText("Chart this month's orders by status")
```

Status: proof of concept. Install with `npm install @sumukhj1219-wkt-org/relay-web-sdk`; sign in and create a publishable key with the CLI (`npm install -g @sumukhj1219-wkt-org/relay-cli`, then `relay login`).
