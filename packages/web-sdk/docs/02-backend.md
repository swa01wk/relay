# Backend: give the assistant a new domain (tools service + agent manifest)

Goal: an `agent_id` (e.g. `orders`) that the frontend connects to, whose LLM answers from your data and renders tables/charts/forms. Each project has its own agents, tools service and model API key; nothing is shared between projects. A new domain needs **no Python and no gateway code changes**:

1. **Tools service** — an HTTP API over your data, in any language.
2. **Agent manifest** — one YAML file (+ a prompt file), uploaded with `relay agents push`.
3. **Run it** — store your model API key (`relay secrets set openai`), push the agent, verify Relay's signature in the tools service.

The examples below use an `orders` domain; replace it with yours.

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
- One tool = one clear question about the data (`list_orders`, `get_customer`, `get_revenue_by_month`). Prefer filters (`status`, `customer_id`, `limit`) over near-duplicate tools. Include a "list everything" tool so "show all X" works.
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
- **Verify Relay's signature** so nobody else can call your tools. Every request from Relay carries `X-Relay-Timestamp`, `X-Relay-Signature: sha256=<hex>` and `X-Relay-Session`. The signature is `HMAC-SHA256(signing_secret, "<timestamp>." + raw_body)`; reject a wrong signature or a timestamp older than 5 minutes:

```python
import hashlib, hmac, time

def relay_signature_is_valid(secret: str, timestamp: str, signature: str, body: bytes) -> bool:
    if not timestamp.isdigit() or abs(time.time() - int(timestamp)) > 300:
        return False
    expected = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, f"sha256={expected}")
```

  With FastAPI, read the raw body (`await request.body()`) in a dependency on both routes and return `401` when the check fails. `GET /tools` is signed too, with an empty body. Keep the secret in an environment variable; `relay tools secret --rotate` replaces it.

## 4. Verify (do all of these)

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
| A write tool runs without asking | Impossible by design — check it is published as `side_effecting`, not `read_only` |
| A write tool never saves | The app must handle approvals (`onApprovalRequested` → `grantApproval`) — see the frontend guide §5 |
| `400` from the tools API | Argument names in the schema don't match the function's parameters |
| Every message: "The assistant couldn't complete that request" | The model rejected the call — usually an invalid or exhausted OpenAI key (`SESSION_ERROR` code `turn_failed`). Set it again with `relay secrets set openai` |
| Tools changed but the assistant doesn't see them | Run `relay agents push` again; running conversations keep the old version |
