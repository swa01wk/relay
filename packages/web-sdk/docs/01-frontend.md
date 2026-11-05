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
- **The user can always hide the generated UI** (required, see "Hide and show the canvas" below): a **Hide** button on the canvas collapses it to a one-line bar, each surface can be **minimized** to its title row or **closed**, and **Clear** removes them all. Hidden or empty, the canvas takes no space beyond that bar.
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
│ Results (3)  [Hide] [Clear]  │  panel   │  │ Results (3)   [Hide] │
│  table / chart / form …      │  (text   │  ├──────────────────────┤
├──────────────────────────────┤  only)   │  │ Existing page        │
│ Existing page content        │          │  │                      │
│ (still visible and usable)   │          │  │       [Chat ▸ drawer]│
└──────────────────────────────┴──────────┘  └──────────────────────┘
```
- Prefer changing a component the app already shows (§4) over drawing a new surface.

### Hide and show the canvas (required)

Generated UI must never get in the way of the app. Give the user these controls, all kept in the same app-level state as the surfaces:

| Control | Where | Does |
|---|---|---|
| **Hide** / **Show results (n)** | Canvas header; when hidden, a slim bar in the page flow (not a floating overlay) | Collapses the whole canvas to that bar and back. Surfaces are kept, not discarded |
| **Minimize** (`–`) / expand | Each surface's title row | Collapses one surface to its title row |
| **Close** (`×`) | Each surface's title row | Removes that surface |
| **Clear** | Canvas header | Removes every surface; the canvas disappears entirely |
| **Show results** | Assistant panel header (optional) | Same as the bar's button, for when the canvas is scrolled out of view |

Rules:
- **New surfaces show the canvas again** (the user just asked for them) and scroll it into view. Hiding is for the results the user has already seen.
- Hidden and empty states take no space: no empty "Results" box, no reserved height.
- The buttons are real `<button>`s with labels (`aria-label="Hide results"`), and the hide toggle sets `aria-expanded` and `aria-controls` on the canvas.
- Remember `hidden` across page navigation within the app (keep it in the provider or `sessionStorage`), so moving between pages doesn't reopen results the user hid.
- A form surface the user is filling in is never removed by **Hide** — hiding only collapses it; values survive.

```tsx
"use client"
import { useState } from "react"
import type { UiSurface } from "@sumukhj1219-wkt-org/relay-web-sdk"

// Keep `surfaces` and `hidden` in your provider (above the chat panel); shown here as props.
export function ResultsCanvas({
  surfaces, hidden, setHidden, onClose, onClear, renderSurface,
}: {
  surfaces: UiSurface[]
  hidden: boolean
  setHidden: (hidden: boolean) => void
  onClose: (index: number) => void
  onClear: () => void
  renderSurface: (surface: UiSurface) => React.ReactNode   // your per-kind renderers (§3)
}) {
  const [minimized, setMinimized] = useState<Record<string, boolean>>({})
  if (surfaces.length === 0) return null
  return (
    <section aria-label="Assistant results" className="border-b">
      <div className="flex items-center gap-2 px-4 py-2">
        <h2 className="text-sm font-medium">Results ({surfaces.length})</h2>
        <button
          type="button"
          aria-expanded={!hidden}
          aria-controls="relay-canvas"
          onClick={() => setHidden(!hidden)}
          className="ml-auto text-sm"
        >
          {hidden ? `Show results (${surfaces.length})` : "Hide"}
        </button>
        {!hidden && <button type="button" onClick={onClear} className="text-sm">Clear</button>}
      </div>
      {/* Hidden with CSS, not unmounted, so half-filled forms keep their values. */}
      <div id="relay-canvas" hidden={hidden} className="space-y-4 px-4 pb-4">
        {surfaces.map((surface, i) => {
          const key = surface.id ?? String(i)
          const isMin = minimized[key] ?? false
          return (
            <article key={key} className="rounded-lg border">
              <header className="flex items-center gap-2 px-3 py-2">
                <h3 className="text-sm font-medium">{surface.title ?? surface.kind}</h3>
                <button
                  type="button"
                  aria-label={isMin ? "Expand" : "Minimize"}
                  aria-expanded={!isMin}
                  onClick={() => setMinimized((m) => ({ ...m, [key]: !isMin }))}
                  className="ml-auto"
                >
                  {isMin ? "+" : "–"}
                </button>
                <button type="button" aria-label="Close" onClick={() => onClose(i)}>×</button>
              </header>
              <div hidden={isMin} className="px-3 pb-3">{renderSurface(surface)}</div>
            </article>
          )
        })}
      </div>
    </section>
  )
}
```

In the `registerPlaygroundSurfaces` callback, update the provider's surfaces and call `setHidden(false)` so new results are visible.

## 2. Create the session (client-side) — the whole lifecycle

```ts
import {
  createRelaySession,
  registerAutoNavigation,
  registerPageForms,
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
// "Go to invoices" works for every page the app links to (menus, sidebars, tabs) — no route list.
const offNavigation = registerAutoNavigation(session, { navigate: (path) => router.push(path) })
// "Fill the invoice form" fills the app's own forms on screen — never submits them.
const offPageForms = registerPageForms(session)
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
offNavigation()
offPageForms()
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
- **Filling forms from the chat (required).** While a form is on screen, users often type or say the values instead ("the title is Login broken, severity high, due next Friday"). The assistant then sends a `FILL_FORM` action with only those fields, already checked against the form (choices matched to the options, numbers and yes/no converted, dates as `YYYY-MM-DD`, unknown fields dropped; up to 5,000 characters for a textarea, so a full draft the user asked the assistant to write arrives complete). Handle it with `registerFormFill` and **merge** the values into that form's current values — keep what the user already typed in other fields, never submit, and briefly highlight the fields that changed. The user still reviews and presses the form's button; for a form with `submitTool` that is still the approval that saves it. If the form is no longer open, throw: the assistant is told and shows the form again with the values prefilled.

  ```tsx
  import { registerFormFill } from "@sumukhj1219-wkt-org/relay-web-sdk"

  // Keep every open form's values in app state keyed by form id (also survives hide/show):
  // const [formValues, setFormValues] = useState<Record<string, Record<string, string | number | boolean>>>({})
  const offFill = registerFormFill(session, ({ formId, values }) => {     // before connect()
    if (!openFormIds.current.has(formId)) throw new Error("form is not open")
    setFormValues((all) => ({ ...all, [formId]: { ...all[formId], ...values } }))
    flashFields(formId, Object.keys(values))                              // optional highlight
  })
  // on unmount: offFill()
  ```

  Render form inputs as **controlled** inputs from `formValues[form.id]` (seeded from each field's `defaultValue` when the surface arrives), so a fill shows up immediately; uncontrolled inputs ignore it.

Build one renderer component per surface kind from your own design system (e.g. shadcn Table, Card, Alert, a Recharts chart); the surface types in `src/ui-surfaces.ts` list every field.

## 4. Let the assistant change the app's own screen (required)

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

**Expose every screen interaction, not one example.** First list every page of the app (put them under "Pages" in `relay-tools.md`):

```bash
rg --files --glob '!node_modules' | rg '(^|/)app/.*page\.(tsx|jsx|ts|js)$'                  # Next.js app router: one page per file
rg --files --glob '!node_modules' | rg '(^|/)pages/' | rg -v '(^|/)pages/(api|_app|_document)'   # Next.js pages router
rg -n "<Route\b|path:\s*['\"]/|createBrowserRouter|createFileRoute\(" --glob '!node_modules'    # React Router, TanStack Router, Vue Router, Angular
rg -n "<Tabs\b|TabsTrigger|role=\"tab\"|<Sheet\b|<Drawer\b|<Dialog\b" --glob '!node_modules'      # tabs, drawers and dialogs inside pages
```

Navigation between them is automatic: `registerAutoNavigation` (in the §2 template) registers a `NAVIGATE` action over every in-app link on screen and keeps it current as menus change. It leaves out links to single records (`/orders/1042` — use `OPEN_<ENTITY>`), sign-out, downloads and new-tab links. Add the pages no link points to, and pass your router so navigation stays client-side:

```ts
const offNavigation = registerAutoNavigation(session, {
  navigate: (path) => router.push(path),              // Next.js useRouter(), React Router useNavigate(), …
  pages: [{ path: "/reports/annual", title: "Annual report" }],   // routes found above that no link points to
  exclude: (path) => path.startsWith("/admin"),       // pages the assistant must never open
})
// On every route change, tell the assistant where the user is:
session.sendState({ page: currentPageName, path: pathname })
```

Page forms are automatic too: `registerPageForms` (in the §2 template) offers every form on screen as a `PAGE_FORM_<NAME>` action whose parameters are the form's fields — labels, choices, limits and required flags, never what is typed in them. The assistant fills them the way typing would (React, Vue and form libraries see the change) and **never submits**: the user reviews and clicks the app's own button. "Open a new invoice for Acme, 50,000" opens the page and fills its form in one reply, because `NAVIGATE` reports back only after the new page's forms are advertised.

- It skips forms with a password field (sign-in), forms with fewer than two fillable fields (search boxes, chat inputs), hidden forms, and fields that are hidden, read-only, file uploads or card/password/one-time-code fields.
- Put `data-relay-ignore` on the assistant's own panel and canvas (their chat input and canvas forms are not page forms), and on any form or field the assistant must not fill.
- `data-relay-form="New invoice"` on a `<form>` names it (otherwise its `aria-label`, legend or first heading) and keeps it even with one field.
- Only native `<input>`, `<select>` and `<textarea>` are filled. For custom widgets (comboboxes, date pickers that are not inputs), register a `PREFILL_<FORM>` action for that form (table below).

Without `navigate`, the SDK clicks the page's own link (Next.js `<Link>` and React Router `<Link>` handle that click client-side) or else loads the page, which ends the session. Do not also register your own `NAVIGATE`; the last registration wins.

Then go through each page and component and register an action for every interaction a user does with the mouse that the assistant should be able to do for them:

| Interaction in the app | Action to register |
|---|---|
| Filters, search boxes, date-range pickers on a list | `FILTER_<LIST>` with one parameter per filter, plus `reset` |
| Sortable columns | `SORT_<LIST>` (`sort_by` enum of columns, `sort_order`), or a parameter of `FILTER_<LIST>` |
| Detail pages / drawers | `OPEN_<ENTITY>` (`id`) that navigates or opens the drawer |
| Navigation between pages | Automatic (`registerAutoNavigation`, above) |
| Tabs and sections inside a page | `SWITCH_TAB` per tabbed view (tabs that are links are covered by navigation) |
| Row selection, highlighting | `SELECT_<ENTITY>` / `HIGHLIGHT_<ENTITY>` (`ids`) |
| Chart controls (period, grouping, metric) | `SET_<CHART>_OPTIONS` with the same choices the controls offer |
| Filling an existing form | Automatic (`registerPageForms`, above); `PREFILL_<FORM>` only for forms built from custom widgets |
| Exports, view toggles, pagination | One action each when the app has them |

Report the matching state with `sendState` (current page, filters, sort, selected ids, open record), so follow-ups build on what the user sees. Check coverage before finishing: every page found above is a link on screen or in `pages` (so `NAVIGATE` can open it), every detail view has an `OPEN_<ENTITY>`, every list with filters has a `FILTER_<LIST>` (the table in `AGENTS.md`, Step 5). Data changes do not go here: they are backend `side_effecting` tools (backend guide §0), so they get an approval.

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

Approvals (when the backend has side-effecting tools): show each request as a card **in the assistant panel**, below the assistant's message, with the `summary` and two buttons, **Approve** and **Reject**. The assistant tells users to "approve it in the assistant panel", so don't use a modal, toast or a separate page for it. If the assistant panel is closed when a request arrives, open it. After a click, disable both buttons and show "Approved" / "Rejected" on the card; the assistant then confirms in chat.

```ts
session.onApprovalRequested((e) => addApprovalCard(e.payload))     // payload.approval_id, summary, tool_name, arguments
// Approve button:
session.grantApproval(approvalId)
// Reject button:
session.rejectApproval(approvalId)
```

### Optional: an assistant avatar

Add one only when the developer asks for it. It lives in a separate entry point, so apps that don't import it don't bundle it. `mountAvatar` loops a **talking** video while the assistant speaks (voice), or while a reply streams in (text sessions), and crossfades to an **idle** clip or a still `poster` otherwise. The videos play muted; the voice comes from the session as usual.

```ts
import { mountAvatar } from "@sumukhj1219-wkt-org/relay-web-sdk/avatar"

const avatar = mountAvatar(element, session, {      // element: a sized box, e.g. 144×144 px; the media fills it
  talking: "/avatar/talking.mp4",                     // required
  idle: "/avatar/idle.mp4",                           // optional; without it the poster is shown while idle
  poster: "/avatar/still.jpg",                        // recommended: shown while videos load
  label: "Assistant",                                 // accessible name
  onStateChange: (state) => setLabel(state),          // "idle" | "listening" | "thinking" | "speaking"
})
avatar.destroy()                                      // on unmount, and before mounting on a new session
```

- The element gets `data-relay-avatar-state="idle|listening|thinking|speaking"`, for styling (e.g. a ring while speaking).
- `idleInterval: [minMs, maxMs]` (with a `poster`): instead of looping the idle clip, show the still and play the clip once at a random moment in that range, e.g. `[6000, 14000]` for an occasional blink. Make the clip start and end on the poster's frame so it doesn't jump.
- Optional `listening` and `thinking` clips; each falls back to `idle`. Other options: `fit` (`"cover"`, default, or `"contain"`), `fadeMs` (200), `speakingHoldMs` (350), `textSpeaking` (true), `textHoldMs` (700).
- In React, mount it in an effect keyed on the session and call `destroy()` in the cleanup. Remount after a reconnect, since that creates a new session.
- Drawing your own avatar (sprites, canvas, 3D): use `watchAssistantState(session, (state) => …, options?)`. It returns a function that stops watching.
- Video tips (for `idleInterval`, an idle clip that plays a short blink/glance and returns to the poster frame): a head-and-shoulders crop, about 640×640, H.264 MP4 with no audio track and `+faststart`, a few seconds that loop cleanly (forward then reversed loops without a jump), and a poster taken from the clip's first frame so starting to talk doesn't jump. Use footage you have the rights to.

## 6. Verify (do all of these)

- [ ] Page loads with no console errors; connection state reaches `"ready"`.
- [ ] Sending "hello" shows the user bubble once and a streamed assistant reply; the busy indicator stops.
- [ ] A data request ("show … as a table", "chart …") renders a surface with the app's components **on the canvas, not in the chat**; the chat shows only the assistant's one-line reply.
- [ ] The surface appears in the page without covering the existing screen, and stays after the assistant panel is closed; its close button removes only that surface.
- [ ] **Hide** collapses the canvas to a one-line bar and the page content moves up; **Show results** brings the same surfaces back; minimize collapses one surface; **Clear** removes the canvas entirely; a half-filled form keeps its values after hide/show.
- [ ] With the canvas hidden, asking for new data shows the canvas again with the new surfaces.
- [ ] Ask for a change that needs approval (e.g. "mark order 42 as shipped"): an approval card with **Approve** and **Reject** appears in the assistant panel; approving it shows the assistant's confirmation.
- [ ] With a form on screen, type two of its values in the chat ("set the title to X and priority to high"): those fields change in the form, other fields keep what you typed, nothing is submitted, and the assistant asks you to review and submit.
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
| Results can't be hidden, or keep covering the page | The canvas has no Hide / minimize / Clear controls, or is an overlay. Add the controls from "Hide and show the canvas" and keep the canvas in the page flow |
| The assistant says "approve it in the assistant panel" but users can't find it | Approval requests were shown as a modal, toast or nowhere. Render them as a card with Approve / Reject in the assistant panel (§5, "Approvals") |
| Values given in the chat never appear in the form | No `registerFormFill` handler (the action fails and the assistant redraws the form), or the inputs are uncontrolled. Register it before `connect()` and render inputs from the form's values in state |
| A chat fill wipes what the user already typed | The handler replaced the form's values instead of merging (`{ ...current, ...values }`) |
| Form values are lost after hiding the results | The canvas was unmounted on hide. Hide it with the `hidden` attribute or CSS instead |
| The agent draws a new table instead of filtering yours | Action not advertised (missing `spec`), registered after unmount, or its `description` doesn't say what it covers |
