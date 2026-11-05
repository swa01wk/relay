# Backend: give the assistant a new domain (tools service + agent manifest)

Goal: an `agent_id` (e.g. `orders`) that the frontend connects to, whose LLM answers from your data and renders tables/charts/forms. Each project has its own agents, tools service and model API key; nothing is shared between projects. A new domain needs **no Python and no gateway code changes**:

1. **Tools service** — an HTTP API over your data, in any language.
2. **Agent manifest** — one YAML file (+ a prompt file), uploaded with `relay agents push`.
3. **Run it** — store your model API key (`relay secrets set openai`), push the agent, verify Relay's signature in the tools service.

The examples below use an `orders` domain; replace it with yours.

## 0. Decide the full tool catalog first (before writing code)

The assistant can only answer what some tool answers, and can only *do* what some write tool does. A thin catalog (`list_x`, `get_x`) gives an assistant that says "I can't do that" to most real requests. **You** decide the catalog, from the app's code: do not ask the developer to list the tools, and do not stop at the tools the request happened to mention.

**The rule: everything a user can see or do in the app, the assistant can see or do through a tool.** Every API endpoint, server action, mutation and form becomes a tool unless it is on the exclusion list in Step 2. Writes count as much as reads: a catalog of 15 read tools and 3 write tools for an app with 20 forms is incomplete.

### Step 1: Scan the whole repository and write the API inventory

Scan the entire repository once — backend, frontend and any shared packages — not just the files you were pointed at. Search for every way the app reads or changes data (use the patterns for the app's stack; `rg` is ripgrep, use `grep -rn` if it is missing):

```bash
# HTTP routes and handlers
rg -n "app\.(get|post|put|patch|delete)\(|router\.(get|post|put|patch|delete)\(" --glob '!node_modules'   # Express / Fastify / Koa
rg -n "@(Get|Post|Put|Patch|Delete)\(|@(Get|Post|Put|Patch|Delete)Mapping|@RequestMapping"                  # NestJS / Spring
rg -n "export (async )?function (GET|POST|PUT|PATCH|DELETE)" --glob '**/route.{ts,js}'                      # Next.js route handlers
rg -ln "" --glob '**/pages/api/**'                                                                          # Next.js pages API
rg -n "@(app|router)\.(get|post|put|patch|delete)\(|@(api_view|action)\b|path\(|re_path\(" --type py        # FastAPI / Flask / Django
rg -n "^\s*(get|post|put|patch|delete|resources?) " --glob '**/routes.rb'                                   # Rails
rg -n "HandleFunc|\.(GET|POST|PUT|PATCH|DELETE)\(" --type go                                                # Go
# Server actions, RPC and GraphQL
rg -n "[\"']use server[\"']" --glob '!node_modules'                                                         # Next.js server actions
rg -n "\.(query|mutation)\(" --glob '**/*router*'                                                           # tRPC
rg -n "type (Query|Mutation)\b|@(Query|Mutation|Resolver)\(" --glob '!node_modules'                         # GraphQL
rg -ln "openapi|swagger" --glob '*.{json,yaml,yml}' --glob '!node_modules'                                  # an API spec lists everything at once
# Writes in the data layer and forms in the UI
rg -n "\.(create|createMany|update|updateMany|upsert|delete|deleteMany|insert|save|destroy)\(|INSERT INTO|UPDATE .* SET|DELETE FROM" --glob '!node_modules' --glob '!*.test.*'
rg -n "<form|onSubmit|useForm\(|handleSubmit|z\.object\(|yup\.object\(|FormData" --glob '!node_modules'
```

Then read each hit and write the inventory: **one row per endpoint, server action, mutation and form**, with

| Field | Example |
|---|---|
| Where | `POST /api/orders` · `app/orders/new/page.tsx` form · `updateOrderStatus` server action |
| What it does, in the user's words | "Create an order" |
| Read or write | write |
| Input fields | name, type, required, allowed values, limits, defaults — from the validation schema (zod, yup, pydantic, DTO, form `required`/`maxLength`), not guessed |
| Who may call it | the ownership or role check it performs |
| Tool | `create_order` (`side_effecting`) — or **excluded: reason** |

Also note the entities (tables, models, collections) with their status/enum values, dates, amounts and owners, the relationships between them, and every screen's lists, filters, dashboard numbers and buttons — Steps 3 and 4 use them.

Write the inventory to `relay-tools.md` next to the tools service (the developer can delete it later) and keep it updated as you build. It is how you and the developer check that nothing was skipped.

### Step 2: Map every inventory row to a tool — writes first

- **Every write row gets its own `side_effecting` tool**: create, update, delete/archive, every status change and button (`approve_invoice`, `assign_ticket`, `cancel_subscription`), every form, every bulk action. Do not fold several distinct writes into one generic `update_record`, and do not drop a write because "the user can do it in the UI".
- **Every read row gets a `read_only` tool**, or is covered by a wider one (a `list_` with filters can cover several list endpoints).
- **Call the app's existing code** — the same service function, validation and permission check the endpoint uses. Never re-implement business rules in the tools service or write to the database around them.
- **Excluded, and listed with the reason in `relay-tools.md`:** sign-in, sign-up, password and two-factor flows; entering card or bank details; uploading or downloading binary files; webhooks and callbacks from other services; internal, admin-only and health endpoints. Nothing else is excluded without a reason the developer would agree with.

### Write tools in depth: forms, validation and results

Relay builds the assistant's forms from a write tool's `input_schema` (backend contract below), so the schema **is** the form. Make it match the app's own form field for field:

- **Every field the app's form has**, with the app's label as `title` and its help text as `description` (shown as the placeholder). Up to 20 fields per form; split larger forms into steps (below).
- **Field types:** `enum` with the real values for every select, radio group and status (a dropdown); `"type": "boolean"` for checkboxes and toggles; `"type": "number"` / `"integer"` with `minimum` for amounts and quantities; `"format": "date"` for dates; `"format": "email"` for emails; `"maxLength": 300` or more for notes and descriptions (a textarea).
- **Long text fields** (message body, description, notes, reply, summary): `"maxLength"` between 300 and 5000 (a textarea) and a `description` that tells the assistant to write it, e.g. `"The complete message text — write the full draft"`, not just `"Body"`. The assistant reads the description to decide what to put there (users often ask it to "write" or "rewrite" this text), and its first 80 characters become the form field's placeholder. The assistant can fill up to 5,000 characters from the chat.
- **`required` exactly as the app's validation requires** — no more, no less. Defaults go in the `description` ("Defaults to today").
- **Validate again in the tool** with the app's own validation (the same zod/pydantic/DTO schema the endpoint uses). The schema shapes the form and the model's arguments, but Relay does not enforce `enum`, `maxLength` or `format`.
- **References to other records** (customer, assignee, project): a string id field whose `description` names the tool that finds it ("Customer id — find it with `search_customers`"), and make sure that lookup tool exists. For short fixed lists (fewer than ~50 team members, categories) use an `enum` of the values instead.
- **Nested or repeated parts** (line items, attendees, addresses): forms have flat fields only, so add a separate tool per part (`add_order_line`, `remove_order_line`, `add_attendee`) instead of an array inside `create_order`.
- **Multi-step forms and wizards:** one tool per step that saves on its own; otherwise one tool for the final submit with every field.
- **Updates:** `update_<entity>` takes the id plus every editable field, all optional. Add a dedicated tool for each change users make often on its own (`set_order_status`, `assign_ticket`, `reschedule_meeting`) — it gives a small, focused form and a clearer approval message.
- **Results:** return the saved record with its id (`{"order": {...}}`) so the assistant can confirm what changed and the app can refresh. On a validation or business failure return `200 {"error": "<what is wrong, in words the user understands>", "fields": {"<field>": "<problem>"}}` — Relay then reports the save as failed and the user can fix the form and resubmit.
- **Descriptions say what changes**: "Creates an order for a customer and reserves stock. Use `add_order_line` afterwards to add products."

### Step 3: Fill the gaps with the common tools for **every** entity

After the 1:1 mapping, check each entity against this matrix and add what is missing. Leave a row out only when it makes no sense for that entity (say why in `relay-tools.md`).

| Tool | Classification | Must support |
|---|---|---|
| `list_<entities>` | `read_only` | A filter for every status/enum, owner, related id and date field (`<field>_from` / `<field>_to`); amount ranges (`min_<amount>` / `max_<amount>`); `sort_by` (enum of sortable fields) + `sort_order`; `limit` (default ≈ 50) + `offset`. Returns the rows plus `total` (the count before `limit`) |
| `search_<entities>` | `read_only` | Free text `query` over the name/title/notes fields; returns the best matches with ids. Merge into `list_<entities>` as a `query` parameter if you prefer |
| `get_<entity>` | `read_only` | One record by id **with its related records** (an order with its customer and line items), so one call answers "tell me about X" |
| `aggregate_<entities>` | `read_only` | `metric` (enum: `count`, `sum_<amount>`, `avg_<amount>`, …), `group_by` (enum of status/owner/category fields, plus `day`/`week`/`month`/`quarter` for a date field), and the same filters as `list_<entities>`. Answers "how many…", "total…by…", "…per month" and feeds charts |
| `create_<entity>` | `side_effecting` | As in "Write tools in depth" |
| `update_<entity>` + `set_<entity>_<field>` | `side_effecting` | Id + every editable field (all optional); focused tools for frequent single changes |
| `delete_<entity>` / `archive_<entity>` | `side_effecting` | Whenever the app lets users do it |
| `<verb>_<entity>` | `side_effecting` | One per state transition or button the app has, including bulk versions if the app has bulk actions |

### Step 4: Add the abstract, cross-entity tools

These answer the open-ended questions users ask most and that per-entity tools answer badly. Add every one that has data behind it:

| Tool | Answers |
|---|---|
| `search_all` | "Find anything about Acme": one free-text search over all entities, returning `{type, id, title}` hits |
| `get_overview` | "How are things?" / "Give me a summary": the headline numbers from the app's dashboard (counts per status, totals, change vs the previous period) |
| `get_timeseries` | "Trend of X over time": `metric` + `entity` + `interval` + date range, returning one point per interval, ready for a line chart |
| `get_top_<entities>` / rankings | "Biggest customers", "slowest products": `rank_by` (enum) + `limit` + `direction`. Can be `list_<entities>` with `sort_by`; add it if the ranking needs a computed value |
| `compare_<entities>` | "Compare A and B": `ids` (array) → the same fields for each, side by side (feeds the `comparison` surface) |
| `get_<entity>_history` / `list_recent_activity` | "What changed?" / "What happened this week?": recent creates, updates and status changes, filterable by entity, user and date |
| `list_attention_items` | "What needs my attention?": overdue, stale, at-risk, unassigned, failing or out-of-range records, using the rules the app already shows (badges, red rows, alerts) |
| `get_my_context` | "My orders", "my team": who the current user is and what they own (from `X-Relay-User`). Needed whenever the app has signed-in users |
| `describe_data` | "What statuses are there?" / "What can I filter by?": entities, their filterable fields and allowed enum values, so the model can build correct filters instead of guessing |
| Domain calculations | Anything the app computes that is not stored: forecasts, totals with tax, conversion rates, durations, scores. Expose each as a tool rather than letting the model do the arithmetic |

### Step 5: Check coverage, then build

1. **Inventory coverage:** every row in `relay-tools.md` names a tool or an exclusion reason. Count them: if the app has more write endpoints, server actions and forms than you have `side_effecting` tools, find out which ones are missing before writing code.
2. **Form check:** for every form in the app, the matching tool's schema has the same fields, required flags, choices and limits.
3. **Question check:** write down at least 25 requests a real user would make — at least a third of them changes ("create…", "mark … as …", "assign … to …", "reschedule…", "cancel…") and the rest lookups, counts, trends, comparisons and vague ones ("anything unusual?"). For each, name the tool calls that answer it. The model runs at most 4 rounds of (parallel) calls per message; a request that needs more, or that no tool handles, means a tool is missing or too narrow.
4. Merge near-duplicate *read* tools into parameters (one `list_orders` with filters, not `list_open_orders` + `list_shipped_orders`). Never merge distinct writes. Every tool needs a distinct description; if two read alike, merge or rewrite them.
5. In your summary to the developer, give the counts (endpoints/actions/forms found → read tools, write tools, excluded) and point to `relay-tools.md`.

Never add a tool that takes raw SQL, a query language, a file path or a URL from the model, and never one that skips the user filter or the app's own permission checks. Every tool applies the same per-user filtering (§3).

## 1. Tools service (any language)

### Contract

| Endpoint | Behaviour |
|---|---|
| `GET /health` | `200 {"status": "ok"}` |
| `GET /tools` | **Discovery.** `200 {"tools": [{"name", "description", "input_schema", "classification"}]}` — Relay reads this when you run `relay agents push` and when a session starts |
| `POST /tools/{name}` | JSON object body = arguments. `200` with a **JSON object**. Unknown tool → `404`; missing/invalid arguments → `400` |

`GET /tools` entry fields:
- `name` — e.g. `list_orders` (letters, digits, `_`).
- `description` — what the LLM reads to decide when to call the tool. Say what it returns and which filters exist.
- `input_schema` — JSON Schema, `{"type": "object", "properties": {...}, "required": [...]}`. Keywords used: `type` (object/string/integer/number/boolean/array), `properties`, `required`, `items`, `enum`, `minLength`, `minimum`, `description`, and for forms `title`, `format` (`date`, `email`) and `maxLength`. Relay rejects arguments with a wrong type, a missing required field, a too-short string or a number below `minimum` before calling you; everything else (`enum`, `maxLength`, `format`, business rules) your tools service must check itself.
- `classification` — `read_only` (default), `draft`, or `side_effecting`. Write tools also get **forms for free**: the agent can show a form bound to a write tool and Relay builds the fields from its schema — `title` → label, `enum` → dropdown, `format: date` / `email` → date / email input, `type: number|integer` → number, `boolean` → checkbox, `maxLength ≥ 300` → textarea, `required` → required field — and saves the submission through the tool. `read_only` tools run when the model calls them. `side_effecting` tools (create/update/delete) are offered to the model as **proposals**: calling one opens an approval dialog in the app, and Relay runs the tool only after the user approves, then lets the assistant confirm the result. Unknown values are treated as `side_effecting`. `draft` tools are not offered to the model.

Design rules:
- Build the whole catalog from §0, not a sample of it. One tool = one clear question about the data (`list_orders`, `get_customer`, `aggregate_orders`). Prefer filters (`status`, `customer_id`, `limit`) over near-duplicate tools. Every `list_` tool with no arguments returns everything (up to `limit`), so "show all X" works.
- Write descriptions for the model: what it returns, every filter, units and currency, and when to use it instead of a similar tool ("for totals use `aggregate_orders`").
- Always return an object (`{"orders": [...], "total": 80}`), never a bare list; include totals.
- Keep results small (default `limit` ≈ 50); the model sees at most ~6,000 characters per result.
- Return business errors as `200 {"error": "not_found"}` so the model can explain them.
- Read-only tools must not change data.
- Define each tool **once** (function + description + schema) and generate both `GET /tools` and `POST /tools/{name}` from that table, so they cannot drift.

### Template (Python / FastAPI) — any language works if it follows the contract

`tools.py` — the single table:

```python
from dataclasses import dataclass, field
from typing import Any, Callable

from orders_tools_api import logic   # plain functions returning dicts


@dataclass(frozen=True)
class ToolSpec:
    fn: Callable[..., dict[str, Any]]
    description: str
    properties: dict[str, Any] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    classification: str = "read_only"

    @property
    def input_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {"type": "object", "properties": self.properties}
        if self.required:
            schema["required"] = list(self.required)
        return schema


TOOL_SPECS: dict[str, ToolSpec] = {
    "list_orders": ToolSpec(
        logic.list_orders,
        "Orders, newest first; filter by status or customer_id. Returns orders and total.",
        {"status": {"type": "string", "enum": ["open", "shipped", "returned"]},
         "customer_id": {"type": "string"},
         "limit": {"type": "integer", "minimum": 1}},
    ),
    "get_order": ToolSpec(logic.get_order, "One order with its line items",
                          {"order_id": {"type": "string", "minLength": 1}}, ("order_id",)),
}


def tool_manifest() -> list[dict[str, Any]]:
    return [{"name": n, "description": s.description, "input_schema": s.input_schema,
             "classification": s.classification} for n, s in TOOL_SPECS.items()]


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    spec = TOOL_SPECS.get(name)
    if spec is None:
        return {"error": f"unknown_tool:{name}"}
    kwargs = {k: v for k, v in arguments.items() if k in spec.properties}
    missing = [k for k in spec.required if k not in kwargs]
    if missing:
        return {"error": f"missing_arguments:{','.join(missing)}"}
    return spec.fn(**kwargs)
```

`main.py`:

```python
from typing import Any

from fastapi import Body, FastAPI, HTTPException

from orders_tools_api.tools import TOOL_SPECS, call_tool, tool_manifest

app = FastAPI(title="Orders tools API")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/tools")
async def list_tools() -> dict[str, Any]:
    return {"tools": tool_manifest()}


@app.post("/tools/{name}")
async def run_tool(name: str, arguments: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    if name not in TOOL_SPECS:
        raise HTTPException(status_code=404, detail=f"unknown tool {name}")
    result = call_tool(name, arguments)
    if str(result.get("error", "")).startswith("missing_arguments"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result
```

Each `logic` function's keyword parameters must match its spec's `properties` exactly. Deploy it like any web service, on a public `https` address.

## 2. Agent manifest

`orders.yaml`, anywhere in your repo:

```yaml
agent_id: orders                                   # what the frontend passes as agentId
tools_url: https://tools.example.com               # public https URL of your tools service
system_prompt_file: orders.prompt.md               # relative to this file (or inline: system_prompt: |)
instructions: >                                    # optional hints for tables/charts/forms
  Orders over time → line chart; one order → kv plus a line-items table.
tool_timeout_seconds: 30                           # optional (1–120)
model: gpt-4o-mini                                 # optional; default is the gateway's model
keyterms:                                          # optional: words voice recognition should listen for
  - Acme Freight                                   #   (product, customer and staff names, jargon; max 100, 50 chars each)
  - ORD number
```

Add `keyterms` when the app has voice: speech recognition mishears names it has never seen. List the product name, the customers, staff and places users will say, and domain words; plain spellings, one phrase per item.

`tools_url` must be a literal `https://` URL that resolves to a public address (no `${VAR}`, no credentials in the URL, no private or loopback hosts).

`orders.prompt.md` — who the assistant is and how it answers. Include the user's role; "use the tools for every fact, never guess"; units/currency and rounding; what it cannot do ("you cannot change records; say what should be changed"); "never mention internal implementation (tools, APIs, JSON)". Do **not** describe the tools or `present_ui`; Relay adds those automatically.

What Relay does for every manifest agent — do not re-implement: discovers the tools, offers the model every `read_only` tool plus the built-in `present_ui` (tables, charts, kv, cards, comparison, markdown, notice, form), runs up to 4 tool rounds with parallel calls, validates arguments against your schemas, sanitizes UI output, handles form submissions, and passes the app's shared screen state to the model.

## 3. Run it

```bash
relay login                          # once; opens the browser
relay secrets set openai             # paste your OpenAI API key (hidden); stored encrypted, never shown again
relay agents push orders.yaml        # uploads the manifest + prompt; fails unless GET <tools_url>/tools answers
relay keys create --kind publishable # rpk_… for createRelaySession({ apiKey, agentId: "orders" })
relay tools secret                   # signing secret for the next step
```

- Model calls for your project use **your** API key and are billed to you by the model provider. Without one, sessions are refused (`409`).
- Re-run `relay agents push` after changing the manifest, the prompt or the tools list. Conversations already running keep the version they started with; new sessions get the new one.
- **Verify Relay's signature** so nobody else can call your tools. Every request from Relay carries:

  | Header | Meaning |
  |---|---|
  | `X-Relay-Timestamp` | Seconds since 1970; reject anything older than 5 minutes |
  | `X-Relay-Session` | The Relay session the call belongs to |
  | `X-Relay-User` | The user your server started the session for, as JSON `{"id", "attributes"?}`; absent when it said none |
  | `X-Relay-Signature-V2` | `sha256=` + HMAC-SHA256 with your signing secret over the lines below |
  | `X-Relay-Signature` | Older signature over timestamp + body only; prefer v2 |

  ```text
  relay-v2
  <X-Relay-Timestamp>
  <operation>            tools.list for GET /tools, tools.call:<name> for POST /tools/<name> (from YOUR route)
  <X-Relay-Session>
  <X-Relay-User>         exactly as received; empty line when absent
  <raw body>             empty for GET /tools
  ```

```python
import hashlib, hmac, json, time

def relay_call_is_valid(secret: str, headers, operation: str, body: bytes) -> bool:
    timestamp = headers.get("X-Relay-Timestamp", "")
    if not timestamp.isdigit() or abs(time.time() - int(timestamp)) > 300:
        return False
    signed = "\n".join(("relay-v2", timestamp, operation,
                        headers.get("X-Relay-Session", ""), headers.get("X-Relay-User", ""))).encode()
    expected = hmac.new(secret.encode(), signed + b"\n" + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(headers.get("X-Relay-Signature-V2", ""), f"sha256={expected}")

def relay_user(headers) -> dict | None:   # only after relay_call_is_valid(...) is True
    raw = headers.get("X-Relay-User", "")
    return json.loads(raw) if raw else None
```

  Return `401` when the check fails. Build `operation` from your own route, never from a header — that is what stops a captured call to `list_orders` from being replayed against `delete_order`. Keep the secret in an environment variable; `relay tools secret --rotate` replaces it.
- **Return only the asking user's data.** For per-user data, filter every query by `relay_user(headers)["id"]` and refuse calls without a user (`401`), so a session your server did not start can never read anyone's records. Your app's own login cookie does **not** reach the tools service — calls come from Relay, not the browser; the user travels in `X-Relay-User` instead.

## 4. Verify (do all of these)

- [ ] `relay-tools.md` maps every endpoint, server action, mutation and form found in the repository to a tool or an exclusion reason; every app form has a write tool with the same fields; every coverage question maps to at most 4 rounds of calls.
- [ ] `curl https://<tools-host>/tools` lists every tool with a schema and classification (send a valid signature once verification is on).
- [ ] `curl -X POST https://<tools-host>/tools/<name> -H 'content-type: application/json' -d '{}'` returns the expected object; a missing required argument returns `400`.
- [ ] `relay agents push <agent>.yaml` prints `Agent <agent_id> is live (<n> tools …)` with the right count, and `relay agents list` shows it.
- [ ] `relay secrets list` shows `openai   set (…)`.
- [ ] Ask a real question from the frontend with `agentId: "<agent_id>"`: tools are called and a surface arrives.
- [ ] A request to the tools service with no signature, or a wrong one, is rejected with `401`.
- [ ] `relay logs` lists the test conversation; `relay logs <session-id>` shows the question, the tools called and no errors.

## 5. Watch it in production

```bash
relay logs                      # recent conversations: agent, start time, turns, errors, live or ended
relay logs <session-id>         # one conversation: each question and answer, tools called, errors, approvals, tokens
relay usage --days 30           # sessions, turns, errors, tokens and cost per day and per agent; calls, failures and timing per tool
relay usage --json              # the same as JSON, for your own dashboards or alerts
```

- A tool with many `failed` calls or a high `max ms` in `relay usage` is the first thing to fix: the assistant cannot answer what that tool answers. `relay logs <session-id>` shows the error your tools service returned.
- Questions in `relay logs` answered without the tool you expected mean the tool's `description` doesn't match how users ask (§0, Step 4).
- Cost appears when the gateway knows the model's price; token counts are always there. They come from your model API key, so your model provider's bill is the source of truth.
- The same data is available over HTTP with your account token (reference: `GET /v1/projects/{id}/sessions`, `…/usage`). Only your account sees your project's conversations.

## Common mistakes

| Symptom | Cause / fix |
|---|---|
| Session refused: `this project has no agent '<id>'` (404) | The agent was not pushed to this project, or `agentId` is misspelt — `relay agents list` |
| Session refused: `this project has no model API key` (409) | Run `relay secrets set openai` |
| `relay agents push`: `tool discovery failed` / `must answer GET <url>/tools` | The tools service is down, not public, or rejecting Relay's signed request (check the signing secret) |
| `relay agents push`: `tools_url must use https` / `resolves to a private address` | Deploy the tools service on a public `https` address; `localhost` and private networks are refused |
| Model never calls a tool / asks the user for data | Vague `description`, or no tool answers that question |
| "I can't do that" for counts, trends, "what needs attention" or comparisons | Catalog too thin: add the `aggregate_`, `get_timeseries`, `list_attention_items` and `compare_` tools from §0 |
| The assistant can look things up but cannot create, change or cancel anything | Write tools missing: redo the §0 repository scan and give every endpoint, server action and form its own `side_effecting` tool |
| The assistant's form is missing fields, has free text where the app has a dropdown, or saves invalid data | The write tool's schema doesn't mirror the app's form: add every field with `title`, `enum`, `format`, `maxLength` and the app's `required` rules (§0, "Write tools in depth") |
| A write tool runs without asking | Impossible by design — check it is published as `side_effecting`, not `read_only` |
| A write tool never saves | The app must handle approvals (`onApprovalRequested` → an Approve / Reject card in the assistant panel → `grantApproval`) — see the frontend guide §5 |
| Forms come back with empty text the user asked the assistant to write | The long-text field's `description` is vague ("Body"). Describe it as the complete text to write ("The complete email text — write the full draft") and give it a `maxLength` of 300–5000 |
| `400` from the tools API | Argument names in the schema don't match the function's parameters |
| Every message: "The assistant couldn't complete that request" | The model rejected the call — usually an invalid or exhausted OpenAI key (`SESSION_ERROR` code `turn_failed`). Set it again with `relay secrets set openai` |
| A user reports a wrong or failed answer | `relay logs` → find their session → `relay logs <session-id>` shows what was asked, which tools ran and the error |
| Tools changed but the assistant doesn't see them | Run `relay agents push` again; running conversations keep the old version |
