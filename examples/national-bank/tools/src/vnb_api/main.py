"""National Bank's backend: the net banking site's API (``/api/…``) and the Relay tools the
assistant calls (``GET /tools``, ``POST /tools/{name}``). Both run the same ``logic`` functions.

Who the customer is:
- Relay tools: the signed ``X-Relay-User`` header (the site's server started the session for that
  customer). Per-customer tools without one get ``401``.
- Site API: ``X-Vnb-User``, set by the site's server after its own sign-in. The API is for that
  server only (private network); set ``VNB_API_TOKEN`` to require it as a bearer token too.
"""

from __future__ import annotations

import hmac
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from vnb_api import logic, sandbox
from vnb_api.relay_signature import relay_user, require_relay_signature
from vnb_api.tools import TOOL_SPECS, call_tool, tool_manifest

app = FastAPI(title="National Bank API + Relay tools", version="0.1.0")


@contextmanager
def _as_customer(user_id: str | None) -> Iterator[None]:
    """Run on this customer's data: their sandbox file (Experience Center) and their rows."""
    with sandbox.use(user_id), logic.as_user(user_id):
        yield


@app.exception_handler(logic.NoUser)
async def _no_user(_request: Request, _exc: logic.NoUser) -> JSONResponse:
    return JSONResponse({"detail": "this needs a signed-in customer"}, status_code=401)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------- Relay tools


@app.get("/tools", dependencies=[Depends(require_relay_signature)])
async def list_tools() -> dict[str, Any]:
    return {"tools": tool_manifest()}


@app.post("/tools/{name}", dependencies=[Depends(require_relay_signature)])
async def run_tool(name: str, request: Request, arguments: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    spec = TOOL_SPECS.get(name)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"unknown tool {name}")
    user = relay_user(request)
    if spec.per_user and user is None:
        raise HTTPException(status_code=401, detail="this tool needs the session's customer (X-Relay-User)")
    try:
        with _as_customer(user["id"] if user else None):
            result = call_tool(name, arguments)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if str(result.get("error", "")).startswith("missing_arguments"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ---------------------------------------------------------------- site API (for the site's server)
#
# One endpoint per tool, generated from TOOL_SPECS: ``GET /api/{tool}`` runs a read tool with the query
# string, ``POST /api/{tool}`` runs a side-effecting tool with the JSON body. The site's pages and forms
# therefore use exactly the rules (and field names) the assistant's tools use.


def customer(
    x_vnb_user: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> str | None:
    token = os.environ.get("VNB_API_TOKEN", "").strip()
    if token and not hmac.compare_digest(authorization or "", f"Bearer {token}"):
        raise HTTPException(status_code=401, detail="site API token required")
    return (x_vnb_user or "").strip() or None


def _form(body: dict[str, Any], tool: str) -> dict[str, Any]:
    """The fields the tool accepts, with numbers and booleans converted (form posts send strings)."""
    props = TOOL_SPECS[tool].properties
    out: dict[str, Any] = {}
    for key, value in body.items():
        if key not in props or value is None or value == "":
            continue
        kind = props[key].get("type")
        if kind in ("integer", "number") and isinstance(value, str):
            cleaned = value.replace(",", "").replace("₹", "").strip()
            if cleaned.replace(".", "", 1).lstrip("-").isdigit():
                value = int(float(cleaned)) if kind == "integer" else float(cleaned)
        elif kind == "boolean" and isinstance(value, str):
            value = value.strip().lower() in ("1", "true", "on", "yes")
        out[key] = value
    return out


def _run(user_id: str | None, tool: str, values: dict[str, Any]) -> Any:
    spec = TOOL_SPECS[tool]
    args = _form(values, tool)
    missing = [k for k in spec.required if k not in args]
    if missing:
        return JSONResponse({"error": "Please fill in: " + ", ".join(spec.properties[k].get("title", k) for k in missing),
                             "fields": {k: "required" for k in missing}}, status_code=400)
    try:
        with _as_customer(user_id):
            result = spec.fn(**args)
    except TypeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    if isinstance(result, dict) and result.get("error"):
        status = 404 if str(result["error"]).startswith("not_found") else 400
        return JSONResponse(result, status_code=status)
    return result


@app.get("/api/{tool}")
def api_read(tool: str, request: Request, user: str | None = Depends(customer)) -> Any:
    spec = TOOL_SPECS.get(tool)
    if spec is None or spec.classification != "read_only":
        raise HTTPException(status_code=404, detail=f"no read endpoint {tool}")
    return _run(user, tool, dict(request.query_params))


@app.post("/api/{tool}")
def api_write(tool: str, body: dict[str, Any] = Body(default_factory=dict), user: str | None = Depends(customer)) -> Any:
    spec = TOOL_SPECS.get(tool)
    if spec is None or spec.classification != "side_effecting":
        raise HTTPException(status_code=404, detail=f"no write endpoint {tool}")
    return _run(user, tool, body)


@app.post("/sandbox/reset")
async def reset_sandbox(x_sandbox_id: str | None = Header(default=None)) -> dict[str, Any]:
    """Experience Center: throw away one visitor's data (see ``sandbox.py``)."""
    if not sandbox.reset(x_sandbox_id):
        raise HTTPException(status_code=404, detail="no such sandbox")
    return {"reset": True}


def run() -> None:
    import uvicorn

    uvicorn.run("vnb_api.main:app", host="0.0.0.0", port=int(os.environ.get("VNB_TOOLS_PORT", "8096")))
