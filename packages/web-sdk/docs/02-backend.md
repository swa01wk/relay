# Backend: give the assistant a new domain (tools service + agent manifest)

Goal: an `agent_id` (e.g. `sales-crm`) that the frontend connects to, whose LLM answers from your data and renders tables/charts/forms. Relay is **self-hosted**: the customer runs the Relay gateway image. A new domain needs **no Python and no gateway code changes**:

1. **Tools service** — an HTTP API over your data, in any language.
2. **Agent manifest** — one YAML file (+ a prompt file) in the gateway's agents folder.
3. **Run it** — make the tools service reachable from the gateway and restart the gateway.

Reference: `agents/sales-crm.yaml` + `examples/sales-crm/tools/` in the Relay repo.

## 1. Tools service (any language)

### Contract

| Endpoint | Behaviour |
|---|---|
| `GET /health` | `200 {"status": "ok"}` |
| `GET /tools` | **Discovery.** `200 {"tools": [{"name", "description", "input_schema", "classification"}]}` — Relay reads this at startup |
| `POST /tools/{name}` | JSON object body = arguments. `200` with a **JSON object**. Unknown tool → `404`; missing/invalid arguments → `400` |

`GET /tools` entry fields:
- `name` — e.g. `list_deals` (letters, digits, `_`).
- `description` — what the LLM reads to decide when to call the tool. Say what it returns and which filters exist.
- `input_schema` — JSON Schema, `{"type": "object", "properties": {...}, "required": [...]}`. Supported keywords: `type` (object/string/integer/number/boolean/array), `properties`, `required`, `items`, `enum`, `minLength`, `minimum`, `description`.
- `classification` — `read_only` (default), `draft`, or `side_effecting`. Write tools also get **forms for free**: the agent can show a form bound to a write tool and Relay builds the fields from its schema — `title` → label, `enum` → dropdown, `format: date` / `email` → date / email input, `type: number|integer` → number, `boolean` → checkbox, `maxLength ≥ 300` → textarea, `required` → required field — and saves the submission through the tool. `read_only` tools run when the model calls them. `side_effecting` tools (create/update/delete) are offered to the model as **proposals**: calling one opens an approval dialog in the app, and Relay runs the tool only after the user approves, then lets the assistant confirm the result. Unknown values are treated as `side_effecting`. `draft` tools are not offered to the model.

Design rules:
- One tool = one clear question about the data (`list_deals`, `get_account`, `get_revenue_by_month`). Prefer filters (`stage`, `owner`, `limit`) over near-duplicate tools. Include a "list everything" tool so "show all X" works.
- Always return an object (`{"deals": [...], "total": 80}`), never a bare list; include totals.
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

Each `logic` function's keyword parameters must match its spec's `properties` exactly. Packaging (`pyproject.toml`, Dockerfile): copy `examples/sales-crm/tools/` and `infra/docker/Dockerfile.crm-tools`.

## 2. Agent manifest

`agents/<agent_id>.yaml` (the folder the gateway reads, `RELAY_AGENTS_DIR`; mounted at `/app/agents` in Docker):

```yaml
agent_id: orders                                   # what the frontend passes as agentId
tools_url: ${RELAY_ORDERS_TOOLS_URL:-http://localhost:8092}
system_prompt_file: orders.prompt.md               # relative to this file (or inline: system_prompt: |)
instructions: >                                    # optional hints for tables/charts/forms
  Orders over time → line chart; one order → kv plus a line-items table.
tool_timeout_seconds: 30                           # optional
```

`agents/orders.prompt.md` — who the assistant is and how it answers. Include the user's role; "use the tools for every fact, never guess"; units/currency and rounding; what it cannot do ("you cannot change records; say what should be changed"); "never mention internal implementation (tools, APIs, JSON)". Do **not** describe the tools or `present_ui`; Relay adds those automatically.

What Relay does for every manifest agent — do not re-implement: discovers the tools, offers the model every `read_only` tool plus the built-in `present_ui` (tables, charts, kv, cards, comparison, markdown, notice, form), runs up to 4 tool rounds with parallel calls, validates arguments against your schemas, sanitizes UI output, handles form submissions, and passes the app's shared screen state to the model.

## 3. Run it

- The gateway must reach `tools_url`. With Docker Compose, add the tools service to `infra/docker/docker-compose.yml` (copy the `crm-tools` service: build, port, `curl` health check), set `RELAY_<NAME>_TOOLS_URL: "http://<service>:<port>"` on `gateway`, and add a `depends_on` entry with `condition: service_healthy`.
- Restart the gateway: `docker compose -f infra/docker/docker-compose.yml up -d --build`. The gateway retries discovery for ~20 s while tools services start.
- Check the gateway log for `agent <agent_id> loaded from <file> (<n> tools)`. A problem logs `agent manifest skipped: <reason>` and that agent is not served.

## 4. Verify (do all of these)

- [ ] `curl localhost:<port>/tools` lists every tool with a schema and classification.
- [ ] `curl -X POST localhost:<port>/tools/<name> -H 'content-type: application/json' -d '{}'` returns the expected object; a missing required argument returns `400`.
- [ ] Gateway log shows `agent <agent_id> loaded … (<n> tools)` with the right count.
- [ ] Ask a real question with `agentId: "<agent_id>"` (frontend, or a WebSocket script): tools are called and a surface arrives. If you get the mortgage assistant's answers instead, the agent did not load (unknown ids fall back to the default agent).
- [ ] Optional automated test: build the agent with `relay_gateway.manifests.build_manifest_runtime(parse_manifest(path), tool_manifest(), model_router=..., delegate=...)` and a scripted model (see `services/gateway/tests/test_sales_crm_manifest_agent.py`).

## Common mistakes

| Symptom | Cause / fix |
|---|---|
| Frontend gets the mortgage assistant | Manifest not loaded — read the `agent manifest skipped:` log line (bad YAML, missing key, unreachable `tools_url`, duplicate `agent_id`) |
| `tool discovery failed` | Tools service not running or not reachable from the gateway container (use the Compose service name, not `localhost`) |
| Model never calls a tool / asks the user for data | Vague `description`, or no tool answers that question |
| A write tool runs without asking | Impossible by design — check it is published as `side_effecting`, not `read_only` |
| A write tool never saves | The app must handle approvals (`onApprovalRequested` → `grantApproval`) — see the frontend guide §5 |
| `400` from the tools API | Argument names in the schema don't match the function's parameters |
| Every message: "The assistant couldn't complete that request" | Upstream model error (e.g. invalid `OPENAI_API_KEY`; `SESSION_ERROR` code `turn_failed`) — check gateway logs |

## Advanced: agents with custom Python logic

Only when an agent needs behaviour a prompt cannot express (deterministic routes, multi-step approval → commit → verify flows), write a Python `AgentAdapter` (usually wrapping `relay_runtime.ToolUsingAgent`) and register it in `services/gateway/src/relay_gateway/deps.py` with `add_tool_agent(agent_id, build_agent=..., register_tools=..., tools_url_env=..., local_executor=...)`. The mortgage example (`examples/mortgage-servicing/agent/`) is the reference.
