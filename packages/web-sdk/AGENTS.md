# @sumukhj1219-wkt-org/relay-web-sdk — instructions for coding agents

You are integrating **Relay**: a voice + text AI assistant that answers from the app's own data and drives the app's UI (tables, charts, forms, comparisons, navigation, …). Do not guess APIs — every name you need is in these docs and in `src/index.ts` / `src/ui-surfaces.ts`.

**This file is only the index.** The instructions are in the guides below. You have not read the instructions until you have opened and read both guides in full.

## Required workflow (in this order; do not skip a step)

**Step 1 — Read both guides now, in full**, even if the task sounds frontend-only. They are in this package (in a project: `node_modules/@sumukhj1219-wkt-org/relay-web-sdk/`):

| File | What it covers |
|---|---|
| [docs/02-backend.md](docs/02-backend.md) | §0 the full tool catalog (scan, inventory, coverage), §1 tools service, §2 agent manifest (`<agent>.yaml` + prompt), §3 run and sign |
| [docs/01-frontend.md](docs/01-frontend.md) | session, layout, surfaces, forms, approvals, §4 screen actions (navigation, filters, open record) |
| [docs/03-reference.md](docs/03-reference.md) | look up an event, surface spec, error code or HTTP endpoint when you need one |

The assistant only works with all three parts: a **tools service** (its data), an **agent manifest** (`<agent>.yaml`, registered with `relay agents push`) and the **frontend**. Check which exist; build the missing ones. A frontend without a tools service and manifest cannot start a session.

**Step 2 — Inventory the whole app before writing any code.** Scan the entire repository (frontend, backend, shared packages), not only the files you were pointed at, and write `relay-tools.md` with:

- **Pages:** every route/page/screen (backend guide §0 Step 1 and frontend guide §4 give the search commands), each with its lists, filters, tabs, detail views, forms and buttons.
- **Data operations:** every API endpoint, server action, mutation and form, each mapped to a tool or an exclusion reason (backend guide §0).
- **Entities:** every model/table with its status values, dates, amounts and owners.

Tell the developer the counts (pages, endpoints/actions/forms, entities) and continue — do not wait for them to pick tools.

**Step 3 — Backend:** build every tool from the inventory (backend guide §0 Steps 2–4, §1), then the manifest and prompt (§2).

**Step 4 — Frontend:** session, canvas and surfaces, forms, approvals (frontend guide §1–3, §5), and a screen action for every page and interaction in the inventory (frontend guide §4): `registerAutoNavigation` with the app's router (pages no link points to go in its `pages`), `registerPageForms` (with `data-relay-ignore` on the assistant's own panel and canvas), `OPEN_<ENTITY>` for every detail view, `FILTER_<LIST>` for every list.

**Step 5 — Coverage check before you say you are done.** Fill this in at the end of `relay-tools.md` and in your summary; if a line does not hold, go back and add what is missing:

| Check | Must hold |
|---|---|
| Pages found → reachable by `NAVIGATE` (a link on screen, or listed in `registerAutoNavigation`'s `pages`) | every page |
| Detail views / drawers → `OPEN_<ENTITY>` actions | one each |
| Lists with filters or search → `FILTER_<LIST>` actions | one each |
| Writes, server actions and forms → `side_effecting` tools | one each, or excluded with a reason |
| Entities → `list_` / `get_` / `aggregate_` tools (+ create/update/delete where the app allows them) | one set each |
| Cross-entity tools (`search_all`, `get_overview`, …; backend guide §0 Step 4) | every one that has data behind it |

A handful of tools for an app with many pages means the inventory was skipped: an app with 20 pages usually needs several dozen tools and actions.

## Setup order (run these; do not skip one)

```bash
relay login                           # the developer signs in once, in the browser
relay secrets set openai              # their OpenAI API key — typed hidden or piped on stdin, never as an argument
relay agents push <agent>.yaml        # after the tools service is deployed (02-backend.md)
relay keys create --kind publishable  # rpk_… → the app's NEXT_PUBLIC_RELAY_API_KEY
relay origins set https://<app-domain>   # limit where that key works
relay logs                            # afterwards: recent conversations; relay logs <id> for one; relay usage for tokens, errors, tools
```

Ask the developer to run `relay login`, `relay secrets set openai`, `relay agents push` and `relay keys create` themselves: login needs their browser, and changes ask for their password. If a command answers with a `429`, wait for the time it gives. Never write an API key, a secret key (`rsk_…`) or the tools signing secret into frontend code, a committed file or a command line.

## The model in one picture

```
Browser app ──(@sumukhj1219-wkt-org/relay-web-sdk)──▶ Relay gateway ──▶ agent (LLM) ──▶ tools service (your data)
   renders UI        WebSocket + WebRTC        runtime      decides tool calls   POST /tools/{name}
```

Who defines what:

- **Tools** (data operations such as `list_orders`) — the developer, on the **backend**: a tools service in any language that also describes its tools (`GET /tools`: name, description, JSON schema, classification).
- **Tool calls** — nobody writes these. The **LLM** decides at runtime which tool to call with which arguments.
- **The agent** — backend: one YAML manifest (`agent_id`, tools URL, system prompt) uploaded to the developer's project with `relay agents push`. No Python; Relay discovers the tools. Each project has its own agents, tools service and model API key.
- **UI actions + renderers** — frontend: the app registers handlers (`registerAction`, `registerPlaygroundSurfaces`) and draws surfaces with its own components.
- The **SDK never renders and never holds AI logic or secrets**. It connects, streams events, acknowledges actions, versions shared state, handles voice, and normalizes AI-generated UI into typed data.

## Rules that are easy to get wrong

1. Create the session in **client-side code only** (browser APIs). In Next.js/React this means a `"use client"` component.
2. **Register every handler before `connect()`** (`registerPlaygroundSurfaces`, `registerFormFill`, `registerAction`, `on(...)`), or early events are missed.
3. `connect()` (WebSocket) must succeed before `connectVoice()` (WebRTC audio). Voice needs a user click (browser mic permission).
4. Handle `SESSION_ERROR` (`payload.code`, `payload.message`): show the message and stop any "thinking" indicator. Track busy state with `TURN_STARTED` / `TURN_COMPLETED`.
5. Keep two regions: the **chat** shows only conversation text; every surface goes on a **canvas** that is part of the page (never a modal or overlay, never inside the chat or the assistant panel) and stays there when the panel closes (frontend guide, "Layout"). The user must be able to **hide** it: a Hide / Show results toggle on the canvas, minimize and close on each surface, and Clear — hidden, it shrinks to a one-line bar; new surfaces show it again (frontend guide, "Hide and show the canvas"). Render **every** surface kind: `table`, `chart`, `kv`, `cards`, `comparison`, `markdown`, `notice`, `form`. Never render model output as raw HTML (`markdown` must go through a markdown renderer that ignores HTML).
6. Expose existing screen components to the agent with `registerAction(name, handler, spec)` and report what is visible with `sendState` — the agent then filters/updates what is on screen instead of drawing duplicates (frontend guide §4).
7. Forms: a form with `submitTool` is bound to a backend write tool — submitting **saves** through that tool (the submit is the user's approval); show Saving → Saved/failed from `COMMIT_VERIFIED` / `ERROR` (`commit_failed`) events carrying `payload.form_id`, allow retry on failure, and refresh your data after `COMMIT_VERIFIED`. A form **without** `submitTool` only sends its values to the assistant — never show "saved" for those. Values the user gives **in the chat** for an open form arrive as a `FILL_FORM` action: handle it with `registerFormFill` and merge them into that form's controlled inputs without submitting (frontend guide §3, "Filling forms from the chat").
8. Tools that change data (refunds, updates) must be published with `"classification": "side_effecting"` in `GET /tools`; the model can only *propose* them, and they run only after a human approves (`onApprovalRequested` → `grantApproval`; the assistant then confirms in a follow-up message). Never mark them `read_only`. Show each approval request as a card **in the assistant panel** with **Approve** and **Reject** buttons (not a modal) — the assistant tells users to approve it there.
9. The browser holds only the project's **publishable** key (`rpk_…`) and the short-lived session token the gateway issues. Secret keys (`rsk_…`), the model API key and the tools signing secret never go into browser code.
10. The tools service must verify `X-Relay-Signature-V2` on every request (backend guide §3) — it is reachable from the internet.
11. **Scan the whole repository and build every applicable tool and screen action** (Required workflow above; backend guide §0; frontend guide §4). Find every page, API route, server action, RPC/GraphQL mutation, data-layer write and form; list them in `relay-tools.md`; map **each** to a tool (excluded only: sign-in/password flows, card entry, binary uploads, webhooks, internal/admin endpoints — with the reason). Every write and form gets its own `side_effecting` tool whose schema mirrors the app's form field for field (labels, dropdown values, dates, required rules, limits; long-text fields described as the complete text to write, e.g. "The complete message text — write the full draft") and that calls the app's own validation and permission checks. Then add the per-entity list/search/get/aggregate tools and the cross-entity ones (search everything, overview, trends, rankings, comparisons, recent activity, "what needs attention", current user, data description, domain calculations). Do not ask the developer which tools to build and do not stop at reads. On the frontend, register an action for every filter, sort, navigation, open-record, selection and chart control on screen (frontend guide §4).
12. If the app has signed-in users and the assistant touches per-user data, start sessions **on the server** with the secret key and `user` (frontend guide, "Apps where users sign in"), and filter every tool by the `X-Relay-User` id. The app's login cookie never reaches the tools service.

## Reference implementation

The guides are self-contained: every template in them is complete and verified against this version of the SDK. Follow them rather than inventing structure, and read `src/index.ts` / `src/ui-surfaces.ts` in this package when you need an exact type.
