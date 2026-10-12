# Frontend: add the Relay assistant to a web app

Goal: a chat + voice assistant panel, and an area where AI-generated surfaces (tables, charts, forms, …) render with the app's own components. Works with any framework; examples use React. Do the steps in order and finish with the checklist.

## 1. Install and configure

```bash
pnpm add @relay/web-sdk        # inside the Relay monorepo: "@relay/web-sdk": "workspace:*"
```

The package ships TypeScript source. In Next.js add it to `transpilePackages`:

```ts
// next.config.ts
const nextConfig = { transpilePackages: ["@relay/web-sdk"] }
export default nextConfig
```

Environment (public, browser-visible — no secrets):

```bash
NEXT_PUBLIC_GATEWAY_URL=http://localhost:8080   # Relay gateway
NEXT_PUBLIC_PROJECT_ID=proj-<app>
NEXT_PUBLIC_AGENT_ID=<agent_id>                  # must match the backend registration (02-backend.md)
```

## 2. Create the session (client-side) — the whole lifecycle

```ts
import {
  createRelaySession,
  registerPlaygroundSurfaces,
  submitForm,
  type RelayEventEnvelope,
  type UiSurface,
} from "@relay/web-sdk"

const session = createRelaySession({
  gatewayUrl: process.env.NEXT_PUBLIC_GATEWAY_URL!,
  projectId: process.env.NEXT_PUBLIC_PROJECT_ID!,
  agentId: process.env.NEXT_PUBLIC_AGENT_ID!,
  transport: "small-webrtc",            // "text-only" if the app never uses voice
})

// 1) Handlers BEFORE connect().
const offSurfaces = registerPlaygroundSurfaces(session, ({ surfaces, replace }) => {
  // replace=true: show only these; replace=false: append (same surface.id updates in place)
  render(surfaces, replace)
})
session.on("TURN_STARTED", () => setBusy(true))
session.on("TURN_COMPLETED", () => setBusy(false))
session.on("TRANSCRIPT_DELTA", (e: RelayEventEnvelope) => showLiveTranscript(String(e.payload.text ?? "")))
session.on("TRANSCRIPT_FINAL", (e) => addUserMessage(String(e.payload.text ?? "")))   // typed AND spoken input
session.on("RESPONSE_STARTED", () => startAssistantMessage())
session.on("RESPONSE_DELTA", (e) => appendAssistantText(String(e.payload.text ?? "")))
session.on("RESPONSE_COMPLETED", (e) => finishAssistantMessage(String(e.payload.text ?? "")))
session.on("SESSION_ERROR", (e) => { setBusy(false); showError(String(e.payload.message ?? "Something went wrong")) })
session.onConnectionState((state) => setConnection(state))   // "disconnected" | "connecting" | "ready" | "error"
session.onVoiceState((state) => setVoice(state))             // "disconnected" | "connecting" | "connected" | "failed"

// 2) Connect.
await session.connect()

// 3) Use.
session.sendText("Chart our pipeline by stage")
await session.connectVoice()        // from a click handler; asks for the microphone
session.setMicMuted(true)           // mute without ending voice
await session.disconnectVoice()

// 4) Tear down (component unmount / page leave).
offSurfaces()
session.disconnect()
```

Notes:
- Anything that **sends** (`sendText`, `sendState`, `sendEvent`, `submitForm`) needs an open connection and throws `not connected` before `connect()` resolves. Do it after `await session.connect()` (or in response to user input). Do **not** send from a `SESSION_READY` handler: `SESSION_READY` is delivered from the session-creation response, before the WebSocket opens.
- An exception thrown inside your `on(...)` handlers is caught and logged (`relay: handler for … threw`); it no longer breaks the session, but check the browser console when something silently doesn't update.
- `TRANSCRIPT_FINAL` arrives for typed text too, so add user chat bubbles there (not on send) to avoid duplicates.
- A form submission arrives as a `TRANSCRIPT_FINAL` whose text starts with `[Form submitted]`; show it as "Submitted form: <title>".
- With voice connected, prefer `SPEECH_PROGRESS.payload.heard_text` (and `RESPONSE_INTERRUPTED.payload.heard_text`) for the assistant bubble so the text matches what was actually spoken.
- `session.on("agent_activity", e => e.payload.speaking)` tells you when the agent is speaking.
- In React, create the session inside `useEffect` and disconnect in its cleanup. Strict Mode mounts twice; that is fine (the server ends the abandoned session automatically).

React reference: `examples/sales-crm/frontend/components/relay/relay-provider.tsx` wraps all of this in a `RelayProvider` + `useRelay()` hook (messages, surfaces, busy, voice, errors, `submitForm`). Copy it rather than re-deriving it.

## 3. Render surfaces

`registerPlaygroundSurfaces` gives you `UiSurface[]` — already normalized and typed. Switch on `surface.kind` and render each with the app's components. All eight kinds must be handled:

| `kind` | Fields | Render as (shadcn names; use the app's equivalents) |
|---|---|---|
| `table` | `columns: {key,label}[]`, `rows: Record[]`, `caption?` | `Table`; add a filter `Input`, sortable headers and a CSV button |
| `chart` | `chartType: "bar"\|"line"\|"area"\|"pie"`, `xKey`, `series: {key,label}[]`, `data`, `yLabel?`, `stacked?` | shadcn `ChartContainer` + Recharts (`BarChart`/`LineChart`/`AreaChart`/`PieChart`); pie uses `series[0]` |
| `kv` | `items: {label,value}[]` | Description list inside a `Card` |
| `cards` | `cards: {title, body?, fields?: {label,value}[]}[]` | Grid of `Card` |
| `comparison` | `entities: string[]`, `rows: {label, values[], differs}[]` | `Table` with one column per entity; highlight `differs` rows (e.g. `Badge`) |
| `markdown` | `markdown: string` | `react-markdown` (+ `remark-gfm`); it ignores raw HTML by default — keep it that way |
| `notice` | `title?`, `body` | `Alert` |
| `form` | `id`, `title?`, `description?`, `fields: {name,label,type,required,options?,defaultValue?,placeholder?}[]`, `submitLabel`, `submitTool?` | `Label` + `Input` / `Textarea` / `Select` / `Checkbox` per `type`; on submit call `submitForm(session, form, values)`. With `submitTool` the submission is **saved** (see below); without it, it only goes to the assistant |

Every surface also has optional `id` and `title`. Exact TypeScript types: `src/ui-surfaces.ts`.

Helpers:
- `surfaceToCsv(surface, rows?)` → CSV string for `table`, `chart`, `comparison`, `kv` (pass the filtered/sorted rows for tables). Download it with a `Blob` + `<a download>`.
- Form values: `number` fields → `Number(value)` or `null`; `checkbox` → boolean.
- **Saving forms (`submitTool`).** The agent can bind a form to a backend write tool; Relay builds its fields from the tool's schema and saves the submission through that tool (the binding lives on the server, so the browser cannot change which tool runs). Show progress per form: set "Saving…" on submit, then listen for `COMMIT_VERIFIED` (`payload.form_id` → "Saved") and `ERROR` with `payload.message === "commit_failed"` (`payload.form_id`, `payload.error` → show it and re-enable the form so the user can fix and resubmit). Refresh any on-screen data after `COMMIT_VERIFIED`. The assistant then confirms in chat; the runtime's follow-up message text starts with `[Action approved|rejected|failed]` — show it as a short status note, not a user bubble (see the CRM's `displayUserText`).

Reference renderers built from shadcn components: `examples/sales-crm/frontend/components/relay/surfaces.tsx`.

## 4. Let the assistant change the app's own screen (recommended)

Give the agent actions over components that already exist (filter a table, open a record, switch a tab). With a `spec`, the SDK advertises the action to the agent, which then **prefers changing what is on screen over drawing a new surface** (e.g. "deals over $70K" filters the existing deals table instead of rendering a new table).

```ts
const off = session.registerAction(
  "FILTER_DEALS_TABLE",
  (params) => {                                   // params follow your JSON schema
    applyFilters(params)
    scrollToTable()
    return { rows_shown: 21, total: 80 }          // returned object goes back to the agent
  },
  {
    description: "Filter the deals table on the dashboard (always on screen). Returns rows_shown.",
    parameters: {
      type: "object",
      properties: {
        min_amount: { type: ["number", "null"], description: "Minimum amount in USD; null clears" },
        owner: { type: ["string", "null"] },
        reset: { type: "boolean", description: "Clear all filters first" },
      },
    },
  },
)
// Also tell the agent what is visible, so follow-ups ("only Ava's") build on current filters:
session.sendState({ deals_table: { visible: true, filters, rows_shown: 21, total: 80 } })
```

Rules: register before or after `connect()` (the SDK re-advertises on changes); unregister (`off()`) when the component unmounts; make the handler idempotent and return counts the agent can repeat; describe every parameter. In React, the CRM's `useRelayAction(name, handler, spec)` hook (`components/relay/relay-provider.tsx`) handles registration timing and unmounts.

## 5. Optional: custom UI actions and shared state

Actions registered **without** a spec are not advertised; only custom agents can trigger them (e.g. open a record):

```ts
session.registerAction("OPEN_ENTITY", async (params, { actionId }) => {
  router.push(`/deals/${params.id}`)         // throw to report ACTION_FAILED with the message
})
session.sendState({ screen: "deal", selected_id: "DEAL-2042" })   // tell the agent what the user sees
session.sendState(edited, { optimisticAdvance: true })            // a human edit; beats stale agent updates
session.onStateConflict(({ expectedVersion, actualVersion }) => showBanner())
```

The SDK acknowledges every action automatically (`ACTION_APPLIED`, or `ACTION_FAILED` if the handler throws or no handler is registered).

Approvals (when the backend has side-effecting tools):

```ts
session.onApprovalRequested((e) => openDialog(e.payload))          // payload.approval_id, summary, tool_name
session.grantApproval(approvalId)   // or session.rejectApproval(approvalId)
```

## 6. Verify (do all of these)

- [ ] Page loads with no console errors; connection state reaches `"ready"`.
- [ ] Sending "hello" shows the user bubble once and a streamed assistant reply; the busy indicator stops.
- [ ] A data request ("show … as a table", "chart …") renders a surface with the app's components.
- [ ] Stop the gateway and send a message: an error is shown, nothing spins forever.
- [ ] Voice: click to start, speak, see the live transcript and hear the reply; mute works.
- [ ] For each advertised action: ask for something it covers (e.g. "deals over $70K") — the existing component changes and no new surface appears.
- [ ] Type-check and lint pass; the production build succeeds.

## Common mistakes

| Symptom | Cause / fix |
|---|---|
| Surfaces never appear | `registerPlaygroundSurfaces` called after `connect()`, or wrong `agentId` |
| User message appears twice | Bubble added on send *and* on `TRANSCRIPT_FINAL` — only use `TRANSCRIPT_FINAL` |
| "Thinking…" never stops | `SESSION_ERROR` not handled, or busy not cleared on `TURN_COMPLETED` |
| `window is not defined` / hydration errors | Session created during server rendering — move it to client code |
| Raw `<b>`/JSON shown in chat | Rendering markdown or payload objects as text; use the surface renderers |
| "not connected" / connect fails although the gateway is healthy | Something called `sendState`/`sendText` before the WebSocket opened (e.g. from a `SESSION_READY` handler) — send after `connect()` resolves |
| The agent draws a new table instead of filtering yours | Action not advertised (missing `spec`), registered after unmount, or its `description` doesn't say what it covers |
| `Module parse failed` for `@relay/web-sdk` | Add it to `transpilePackages` (Next.js) or your bundler's TS handling |
