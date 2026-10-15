# Frontend: add the Relay assistant to a web app

Goal: a chat + voice assistant panel for the conversation, and a **separate canvas** in the app's main view where AI-generated surfaces (tables, charts, forms, …) render with the app's own components. Works with any framework; examples use React. Do the steps in order and finish with the checklist.

## 1. Install and configure

```bash
npm install @sumukhj1219-wkt-org/relay-web-sdk
```

It is plain ES modules with TypeScript types and no dependencies; no bundler configuration is needed.

Environment (public, browser-visible — the publishable key is designed to be public; never put a secret key `rsk_…` here):

```bash
NEXT_PUBLIC_GATEWAY_URL=http://localhost:8080   # Relay gateway
NEXT_PUBLIC_RELAY_API_KEY=rpk_…                  # publishable key: `relay keys create --kind publishable`
NEXT_PUBLIC_AGENT_ID=<agent_id>                  # must match the backend registration (02-backend.md)
```

## Layout: chat for words, canvas for everything else

Two regions, never mixed:

| Region | Shows | Fed by |
|---|---|---|
| **Chat** (assistant panel) | Only conversation text: user messages, the assistant's short replies, one-line status notes ("Saved", "Approved") and errors | `TRANSCRIPT_FINAL`, `RESPONSE_DELTA` / `RESPONSE_COMPLETED`, `SESSION_ERROR` |
| **Canvas** (in the app's main view, outside the chat) | Every surface: tables, charts, cards, kv, comparisons, markdown, notices, forms | `registerPlaygroundSurfaces` |

- Do **not** render surfaces inside chat messages or the chat scroll, even small ones. A chat bubble is too narrow for tables and charts, and surfaces must stay on screen while the conversation scrolls on.
- **The canvas is part of the page, not an overlay.** Never put it in a modal, dialog, sheet, popover or full-screen layer: it must not cover or hide the app's existing screen, and the user must be able to keep using the page around it.
- **Surfaces outlive the chat panel.** Closing, collapsing or hiding the assistant panel must not remove them. They stay until new surfaces replace them, the user dismisses one (a small close button on each surface), or the user clears the canvas. Keep the surfaces in app state above the panel (for example in the provider), not inside the panel component.
- Put the canvas where the user's work is: a "Results" section at the top of the main content column, or a wide split pane beside the content. The chat may be a docked side panel or, on small screens, a drawer — the drawer holds only the chat.
- When new surfaces arrive, scroll the canvas into view (`scrollIntoView({ behavior: "smooth", block: "nearest" })`); don't open anything on top of the page.
- `replace: true` (the default) clears the canvas and shows the new surfaces; `replace: false` adds them below what is there.
- When surfaces arrive, the assistant's chat reply is one short sentence ("Your top 10 meetings are on screen."). Don't copy surface content into the chat.
- On narrow screens, keep the canvas in the page flow (full width, above the content) and the chat as a drawer; closing the drawer reveals the canvas instead of discarding it.

```text
Desktop                                      Narrow screen
┌──────────────────────────────┬──────────┐  ┌──────────────────────┐
│ App header                   │          │  │ App header           │
├──────────────────────────────┤  Chat    │  ├──────────────────────┤
│ Results (canvas)        [×]  │  panel   │  │ Results (canvas) [×] │
│  table / chart / form …      │  (text   │  ├──────────────────────┤
├──────────────────────────────┤  only)   │  │ Existing page        │
│ Existing page content        │          │  │                      │
│ (still visible and usable)   │          │  │       [Chat ▸ drawer]│
└──────────────────────────────┴──────────┘  └──────────────────────┘
```
- Prefer changing a component the app already shows (§4) over drawing a new surface.

## 2. Create the session (client-side) — the whole lifecycle

```ts
import {
  createRelaySession,
  registerPlaygroundSurfaces,
  submitForm,
  type RelayEventEnvelope,
  type UiSurface,
} from "@sumukhj1219-wkt-org/relay-web-sdk"

const session = createRelaySession({
  gatewayUrl: process.env.NEXT_PUBLIC_GATEWAY_URL!,
  apiKey: process.env.NEXT_PUBLIC_RELAY_API_KEY!,   // publishable key (rpk_…); never a secret key
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

### Apps where users sign in: start the session on your server

If the assistant reads or changes **per-user data** (my meetings, my orders), start the session from your backend, after your own login check, and say who it is for. Your tools service then receives that user on every call (backend guide §3). Never let the browser say who the user is.

```ts
// Your backend (route handler / API route). The secret key (rsk_…) comes from `relay keys create --kind secret`.
import { createSession } from "@sumukhj1219-wkt-org/relay-web-sdk"

export async function startAssistant(currentUser: { id: string; role: string }) {
  const s = await createSession(process.env.RELAY_GATEWAY_URL!, {
    apiKey: process.env.RELAY_SECRET_KEY!,
    agentId: "orders",
    user: { id: currentUser.id, attributes: { role: currentUser.role } },
  })
  return { sessionId: s.sessionId, token: s.devToken }   // send only these to the browser
}
```

```ts
// Browser: connect to the session your server created (no key in the browser at all).
const { sessionId, token } = await fetch("/api/assistant/session", { method: "POST" }).then((r) => r.json())
const session = createRelaySession({ gatewayUrl, agentId: "orders", sessionId, devToken: token })
```

A publishable key cannot set `user` (`403`): use it only when the assistant needs no per-user data. The session token is sent in a header and the WebSocket protocol list, never in a URL.

In React, put all of this in one provider component (`RelayProvider`) with a `useRelay()` hook exposing messages, surfaces, busy, voice state, errors and `submitForm`, so the rest of the app never touches the session directly.

## 3. Render surfaces

`registerPlaygroundSurfaces(session, ({ surfaces, replace }) => …)` gives you `UiSurface[]` — already normalized and typed — for the **canvas** (see Layout above; never the chat). Switch on `surface.kind` and render each with the app's components. All eight kinds must be handled:

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
- **Saving forms (`submitTool`).** The agent can bind a form to a backend write tool; Relay builds its fields from the tool's schema and saves the submission through that tool (the binding lives on the server, so the browser cannot change which tool runs). Show progress per form: set "Saving…" on submit, then listen for `COMMIT_VERIFIED` (`payload.form_id` → "Saved") and `ERROR` with `payload.message === "commit_failed"` (`payload.form_id`, `payload.error` → show it and re-enable the form so the user can fix and resubmit). Refresh any on-screen data after `COMMIT_VERIFIED`. The assistant then confirms in chat; the runtime's follow-up message text starts with `[Action approved|rejected|failed]` — show it as a short status note, not a user bubble.

Build one renderer component per surface kind from your own design system (e.g. shadcn Table, Card, Alert, a Recharts chart); the surface types in `src/ui-surfaces.ts` list every field.

## 4. Let the assistant change the app's own screen (recommended)

Give the agent actions over components that already exist (filter a table, open a record, switch a tab). With a `spec`, the SDK advertises the action to the agent, which then **prefers changing what is on screen over drawing a new surface** (e.g. "deals over $70K" filters the existing deals table instead of rendering a new table).

```ts
const off = session.registerAction(
  "FILTER_ORDERS_TABLE",
  (params) => {                                   // params follow your JSON schema
    applyFilters(params)
    scrollToTable()
    return { rows_shown: 21, total: 80 }          // returned object goes back to the agent
  },
  {
    description: "Filter the orders table on the dashboard (always on screen). Returns rows_shown.",
    parameters: {
      type: "object",
      properties: {
        min_amount: { type: ["number", "null"], description: "Minimum amount in USD; null clears" },
        customer: { type: ["string", "null"] },
        reset: { type: "boolean", description: "Clear all filters first" },
      },
    },
  },
)
// Also tell the agent what is visible, so follow-ups ("only Acme's") build on current filters:
session.sendState({ orders_table: { visible: true, filters, rows_shown: 21, total: 80 } })
```

Rules: register before or after `connect()` (the SDK re-advertises on changes); unregister (`off()`) when the component unmounts; make the handler idempotent and return counts the agent can repeat; describe every parameter. In React, wrap this in a small `useRelayAction(name, handler, spec)` hook that registers in an effect and calls `off()` in its cleanup.

## 5. Optional: custom UI actions and shared state

Actions registered **without** a spec are not advertised; only custom agents can trigger them (e.g. open a record):

```ts
session.registerAction("OPEN_ENTITY", async (params, { actionId }) => {
  router.push(`/orders/${params.id}`)         // throw to report ACTION_FAILED with the message
})
session.sendState({ screen: "order", selected_id: "ORD-2042" })   // tell the agent what the user sees
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
- [ ] A data request ("show … as a table", "chart …") renders a surface with the app's components **on the canvas, not in the chat**; the chat shows only the assistant's one-line reply.
- [ ] The surface appears in the page without covering the existing screen, and stays after the assistant panel is closed; its close button removes only that surface.
- [ ] Stop the gateway and send a message: an error is shown, nothing spins forever.
- [ ] Voice: click to start, speak, see the live transcript and hear the reply; mute works.
- [ ] For each advertised action: ask for something it covers (e.g. "orders over $500") — the existing component changes and no new surface appears.
- [ ] Type-check and lint pass; the production build succeeds.

## Common mistakes

| Symptom | Cause / fix |
|---|---|
| Surfaces never appear | `registerPlaygroundSurfaces` called after `connect()`, or wrong `agentId` |
| User message appears twice | Bubble added on send *and* on `TRANSCRIPT_FINAL` — only use `TRANSCRIPT_FINAL` |
| "Thinking…" never stops | `SESSION_ERROR` not handled, or busy not cleared on `TURN_COMPLETED` |
| `window is not defined` / hydration errors | Session created during server rendering — move it to client code |
| Raw `<b>`/JSON shown in chat | Rendering markdown or payload objects as text; use the surface renderers |
| Tables, charts or cards appear inside the chat | Surfaces rendered in the message list. Render them on a canvas outside the chat (Layout section); the chat keeps only text |
| Generated UI opens as an overlay over the app, and disappears when it is closed | The canvas was put in a modal or inside the assistant panel. Make it a section of the page (Layout section), keep surfaces in state above the panel, and give each surface its own close button |
| "not connected" / connect fails although the gateway is healthy | Something called `sendState`/`sendText` before the WebSocket opened (e.g. from a `SESSION_READY` handler) — send after `connect()` resolves |
| The agent draws a new table instead of filtering yours | Action not advertised (missing `spec`), registered after unmount, or its `description` doesn't say what it covers |
