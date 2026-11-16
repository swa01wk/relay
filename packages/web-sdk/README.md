# @sumukhj1219-wkt-org/relay-web-sdk

Browser SDK for Relay: connect an app to a Relay agent over WebSocket (+ WebRTC voice), stream the conversation, run UI actions, sync shared state with versioning, handle approvals, and receive AI-generated UI surfaces (`table`, `chart`, `kv`, `cards`, `comparison`, `markdown`, `notice`, `form`) as typed data the app renders with its own components. Framework-agnostic; plain ES modules with TypeScript types, no dependencies.

## For coding agents (Cursor, Claude Code, Codex, …) — start here

Before writing any code, open and read **all** of these files in this package (in a project: `node_modules/@sumukhj1219-wkt-org/relay-web-sdk/`). `AGENTS.md` is only the index; the instructions are in the guides:

1. [AGENTS.md](AGENTS.md) — the required workflow and the rules.
2. [docs/02-backend.md](docs/02-backend.md) — inventory of the whole app, tools service, agent manifest (`<agent>.yaml`).
3. [docs/01-frontend.md](docs/01-frontend.md) — session, surfaces, forms, approvals, navigation and other screen actions.
4. [docs/03-reference.md](docs/03-reference.md) — look-ups (events, surface specs, errors, endpoints).

Then follow the workflow in `AGENTS.md`: inventory every page, endpoint and form into `relay-tools.md` first, build every tool and screen action from it, and finish with its coverage check.

Point your project's agent at them once (agents often skip files in `node_modules` unless told). The quickest way, in the app's folder:

```bash
npx @sumukhj1219-wkt-org/relay-cli init   # or `relay init` if the CLI is installed
```

It adds a Relay block to `AGENTS.md` and `CLAUDE.md` (creating them if needed; re-running replaces the block) and writes `.cursor/rules/relay.mdc`. The pointers reference the installed package, so they follow SDK upgrades. To do it by hand instead:

- **Codex / Cursor / most agents** — add to the project's `AGENTS.md`:
  `Before working on the Relay assistant, read node_modules/@sumukhj1219-wkt-org/relay-web-sdk/AGENTS.md, docs/02-backend.md and docs/01-frontend.md in that package in full, and follow the required workflow in AGENTS.md.`
- **Claude Code** — add to the project's `CLAUDE.md`: `@node_modules/@sumukhj1219-wkt-org/relay-web-sdk/AGENTS.md` and the same sentence.
- **Cursor rules** — `.cursor/rules/relay.mdc` with the same sentence and `alwaysApply: true`.

## Quick look

```ts
import { createRelaySession, registerPlaygroundSurfaces } from "@sumukhj1219-wkt-org/relay-web-sdk"

const session = createRelaySession({ gatewayUrl, apiKey, agentId: "orders", transport: "small-webrtc" })  // apiKey: publishable key from `relay keys create`
registerPlaygroundSurfaces(session, ({ surfaces }) => render(surfaces))   // before connect()
session.on("RESPONSE_DELTA", (e) => appendToChat(String(e.payload.text ?? "")))
await session.connect()
session.sendText("Chart this month's orders by status")
```

Optional video avatar (talks while the assistant speaks): `import { mountAvatar } from "@sumukhj1219-wkt-org/relay-web-sdk/avatar"`; see `docs/01-frontend.md` §5.

Status: proof of concept. Install with `npm install @sumukhj1219-wkt-org/relay-web-sdk`; sign in and create a publishable key with the CLI (`npm install -g @sumukhj1219-wkt-org/relay-cli`, then `relay login`).
