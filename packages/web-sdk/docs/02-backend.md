# Backend: give the assistant a new domain (tools service + agent manifest)

Goal: an `agent_id` (e.g. `orders`) that the frontend connects to, whose LLM answers from your data and renders tables/charts/forms. Each project has its own agents, tools service and model API key; nothing is shared between projects. A new domain needs **no Python and no gateway code changes**:

1. **Tools service** — an HTTP API over your data, in any language.
2. **Agent manifest** — one YAML file (+ a prompt file), uploaded with `relay agents push`.
3. **Run it** — store your model API key (`relay secrets set openai`), push the agent, verify Relay's signature in the tools service.

The examples below use an `orders` domain; replace it with yours.

## 0. Decide the full tool catalog first (before writing code)

The assistant can only answer what some tool answers. A thin catalog (`list_x`, `get_x`) gives an assistant that says "I can't do that" to most real questions. **You** decide the catalog: derive it from the app's code. Do not ask the developer to list the tools, and do not stop at the two or three tools the request happened to mention. Cover every entity and every question a user of this app could reasonably ask.

### Step 1: Inventory the app

Read the data layer and the screens, not just the file you were pointed at:

- **Entities:** every table, ORM model, collection or API resource the app's users see. Skip internal ones such as sessions, migrations and job queues.
- **Fields per entity:** identifiers, status/enum fields (with their values), dates, amounts, owners/assignees, free-text fields.
- **Relationships:** which entity belongs to which (an order has a customer and line items).
- **What users do today:** every list page, filter, sort, search box, dashboard number, chart, export, detail page, form and button in the app. Each is a question or an action the assistant must be able to do too.
- **Who may see what:** per-user, per-team or per-account data (it decides the `X-Relay-User` filter in §3).

### Step 2: Generate the common tools for **every** entity

Apply this matrix to each entity in the inventory. Leave a row out only when it makes no sense for that entity (say why in your summary).

| Tool | Classification | Must support |
|---|---|---|
| `list_<entities>` | `read_only` | A filter for every status/enum, owner, related id and date field (`<field>_from` / `<field>_to`); amount ranges (`min_<amount>` / `max_<amount>`); `sort_by` (enum of sortable fields) + `sort_order`; `limit` (default ≈ 50) + `offset`. Returns the rows plus `total` (the count before `limit`) |
| `search_<entities>` | `read_only` | Free text `query` over the name/title/notes fields; returns the best matches with ids. Merge into `list_<entities>` as a `query` parameter if you prefer |
| `get_<entity>` | `read_only` | One record by id **with its related records** (an order with its customer and line items), so one call answers "tell me about X" |
| `aggregate_<entities>` | `read_only` | `metric` (enum: `count`, `sum_<amount>`, `avg_<amount>`, …), `group_by` (enum of status/owner/category fields, plus `day`/`week`/`month`/`quarter` for a date field), and the same filters as `list_<entities>`. Answers "how many…", "total…by…", "…per month" and feeds charts |
| `create_<entity>` | `side_effecting` | Every field a user can set in the app's own create form, with `title`, `enum`, `format` and `required`, because the assistant's form is built from this schema |
| `update_<entity>` | `side_effecting` | Id + every editable field (all optional except the id) |
| `delete_<entity>` / `archive_<entity>` | `side_effecting` | Only if the app lets users do it |
| `<verb>_<entity>` | `side_effecting` | One per state transition or button the app has (`ship_order`, `assign_ticket`, `approve_invoice`, `add_note_to_order`), including bulk versions if the app has bulk actions |

### Step 3: Add the abstract, cross-entity tools

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

### Step 4: Check coverage, then build

1. Write down at least 25 questions and requests a real user of this app would make. Mix lookups, counts, trends, comparisons, "what should I do", vague ones ("anything unusual?") and changes ("mark it as shipped"). Read them off the app's screens.
2. For each one, name the tool calls that answer it. The model runs at most 4 rounds of (parallel) calls per message. A question that needs more rounds, or that no tool answers, means a tool is missing or too narrow: add or widen one.
3. Merge near-duplicates into parameters (one `list_orders` with filters, not `list_open_orders` + `list_shipped_orders`). Complete coverage matters more than a short list, but every tool needs a distinct description; if two descriptions read alike, merge the tools.
4. List the final catalog in your summary to the developer (tool, classification, the question it answers), plus the coverage questions it was checked against.

Never add a tool that takes raw SQL, a query language, a file path or a URL from the model, and never one that skips the user filter. Every abstract tool applies the same per-user filtering as the per-entity ones (§3).

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
- `input_schema` — JSON Schema, `{"type": "object", "properties": {...}, "required": [...]}`. Supported keywords: `type` (object/string/integer/number/boolean/array), `properties`, `required`, `items`, `enum`, `minLength`, `minimum`, `description`.
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
```

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

- [ ] The catalog covers every entity with the §0 matrix plus the abstract tools, and every coverage question maps to at most 4 rounds of calls.
- [ ] `curl https://<tools-host>/tools` lists every tool with a schema and classification (send a valid signature once verification is on).
- [ ] `curl -X POST https://<tools-host>/tools/<name> -H 'content-type: application/json' -d '{}'` returns the expected object; a missing required argument returns `400`.
- [ ] `relay agents push <agent>.yaml` prints `Agent <agent_id> is live (<n> tools …)` with the right count, and `relay agents list` shows it.
- [ ] `relay secrets list` shows `openai   set (…)`.
- [ ] Ask a real question from the frontend with `agentId: "<agent_id>"`: tools are called and a surface arrives.
- [ ] A request to the tools service with no signature, or a wrong one, is rejected with `401`.

## Common mistakes

| Symptom | Cause / fix |
|---|---|
| Session refused: `this project has no agent '<id>'` (404) | The agent was not pushed to this project, or `agentId` is misspelt — `relay agents list` |
| Session refused: `this project has no model API key` (409) | Run `relay secrets set openai` |
| `relay agents push`: `tool discovery failed` / `must answer GET <url>/tools` | The tools service is down, not public, or rejecting Relay's signed request (check the signing secret) |
| `relay agents push`: `tools_url must use https` / `resolves to a private address` | Deploy the tools service on a public `https` address; `localhost` and private networks are refused |
| Model never calls a tool / asks the user for data | Vague `description`, or no tool answers that question |
| "I can't do that" for counts, trends, "what needs attention" or comparisons | Catalog too thin: add the `aggregate_`, `get_timeseries`, `list_attention_items` and `compare_` tools from §0 |
| A write tool runs without asking | Impossible by design — check it is published as `side_effecting`, not `read_only` |
| A write tool never saves | The app must handle approvals (`onApprovalRequested` → `grantApproval`) — see the frontend guide §5 |
| `400` from the tools API | Argument names in the schema don't match the function's parameters |
| Every message: "The assistant couldn't complete that request" | The model rejected the call — usually an invalid or exhausted OpenAI key (`SESSION_ERROR` code `turn_failed`). Set it again with `relay secrets set openai` |
| Tools changed but the assistant doesn't see them | Run `relay agents push` again; running conversations keep the old version |
