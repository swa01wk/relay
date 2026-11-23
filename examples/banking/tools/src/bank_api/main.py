"""Kestrel Bank's backend: the net banking site's API (``/api/…``) and the Relay tools the assistant
calls (``GET /tools``, ``POST /tools/{name}``). Both run the same ``logic`` functions.

Who the customer is:
- Relay tools: the signed ``X-Relay-User`` header (the site's server started the session for that
  customer). Per-customer tools without one get ``401``.
- Site API: ``X-Bank-User``, set by the site's server after its own sign-in. The API is for that
  server only (private network); set ``BANK_API_TOKEN`` to require it as a bearer token too.
"""

from __future__ import annotations

import hmac
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from bank_api import logic, sandbox
from bank_api.relay_signature import relay_user, require_relay_signature
from bank_api.tools import TOOL_SPECS, call_tool, tool_manifest

app = FastAPI(title="Kestrel Bank API + Relay tools", version="0.1.0")


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


def customer(
    x_bank_user: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> str | None:
    token = os.environ.get("BANK_API_TOKEN", "").strip()
    if token and not hmac.compare_digest(authorization or "", f"Bearer {token}"):
        raise HTTPException(status_code=401, detail="site API token required")
    return (x_bank_user or "").strip() or None


def _run(user_id: str | None, tool: str, **kwargs: Any) -> Any:
    """Call a tool's function for the site, with the site's values converted like the tool's schema."""
    spec = TOOL_SPECS[tool]
    args = _form(kwargs, tool)
    try:
        with _as_customer(user_id):
            result = spec.fn(**args)
    except TypeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    if isinstance(result, dict) and result.get("error"):
        status = 404 if str(result["error"]).startswith("not_found") else 400
        return JSONResponse(result, status_code=status)
    return result


def _form(body: dict[str, Any], tool: str) -> dict[str, Any]:
    """The body's fields that the tool accepts, with integers and booleans converted (form posts send strings)."""
    props = TOOL_SPECS[tool].properties
    out: dict[str, Any] = {}
    for key, value in body.items():
        if key not in props or value is None or value == "":
            continue
        kind = props[key].get("type")
        if kind == "integer" and isinstance(value, str):
            cleaned = value.replace(",", "").replace("₹", "").strip()
            value = int(float(cleaned)) if cleaned.replace(".", "", 1).lstrip("-").isdigit() else value
        elif kind == "boolean" and isinstance(value, str):
            value = value.strip().lower() in ("1", "true", "on", "yes")
        out[key] = value
    return out


@app.get("/api/me")
def api_me(user: str | None = Depends(customer)) -> Any:
    return _run(user, "get_my_context")


@app.get("/api/overview")
def api_overview(user: str | None = Depends(customer)) -> Any:
    return _run(user, "get_overview")


@app.get("/api/attention")
def api_attention(user: str | None = Depends(customer)) -> Any:
    return _run(user, "list_attention_items")


@app.get("/api/accounts")
def api_accounts(user: str | None = Depends(customer)) -> Any:
    return _run(user, "list_accounts")


@app.get("/api/accounts/{account_id}")
def api_account(account_id: str, user: str | None = Depends(customer)) -> Any:
    return _run(user, "get_account", account_id=account_id)


@app.get("/api/transactions")
def api_transactions(request: Request, user: str | None = Depends(customer)) -> Any:
    return _run(user, "list_transactions", **dict(request.query_params))


@app.get("/api/transactions/{transaction_id}")
def api_transaction(transaction_id: str, user: str | None = Depends(customer)) -> Any:
    return _run(user, "get_transaction", transaction_id=transaction_id)


@app.post("/api/transactions/{transaction_id}/dispute")
def api_dispute(transaction_id: str, body: dict[str, Any] = Body(...), user: str | None = Depends(customer)) -> Any:
    if not body.get("reason"):
        return JSONResponse({"error": "choose a reason", "fields": {"reason": "required"}}, status_code=400)
    return _run(user, "raise_dispute", **{**body, "transaction_id": transaction_id})


@app.get("/api/disputes")
def api_disputes(user: str | None = Depends(customer)) -> Any:
    return _run(user, "list_disputes")


@app.get("/api/insights/summary")
def api_summary(request: Request, user: str | None = Depends(customer)) -> Any:
    return _run(user, "get_month_summary", **dict(request.query_params))


@app.get("/api/insights/cash-flow")
def api_cash_flow(request: Request, user: str | None = Depends(customer)) -> Any:
    return _run(user, "get_cash_flow", **dict(request.query_params))


@app.get("/api/insights/aggregate")
def api_aggregate(request: Request, user: str | None = Depends(customer)) -> Any:
    return _run(user, "aggregate_transactions", **dict(request.query_params))


@app.get("/api/payees")
def api_payees(user: str | None = Depends(customer)) -> Any:
    return _run(user, "list_payees")


@app.post("/api/payees")
def api_add_payee(body: dict[str, Any] = Body(...), user: str | None = Depends(customer)) -> Any:
    if not str(body.get("name", "")).strip():
        return JSONResponse({"error": "give the payee's name", "fields": {"name": "required"}}, status_code=400)
    return _run(user, "add_payee", **body)


@app.delete("/api/payees/{payee_id}")
def api_remove_payee(payee_id: str, user: str | None = Depends(customer)) -> Any:
    return _run(user, "remove_payee", payee_id=payee_id)


@app.get("/api/transfers/quote")
def api_quote(request: Request, user: str | None = Depends(customer)) -> Any:
    params = dict(request.query_params)
    if not params.get("to") or not params.get("amount"):
        return JSONResponse({"error": "choose who to pay and how much"}, status_code=400)
    return _run(user, "get_transfer_quote", **params)


@app.get("/api/transfers/limits")
def api_limits(user: str | None = Depends(customer)) -> Any:
    return _run(user, "get_transfer_limits")


@app.post("/api/transfers")
def api_transfer(body: dict[str, Any] = Body(...), user: str | None = Depends(customer)) -> Any:
    missing = [k for k in ("to", "amount") if not str(body.get(k, "")).strip()]
    if missing:
        return JSONResponse({"error": "choose who to pay and how much", "fields": {k: "required" for k in missing}}, status_code=400)
    return _run(user, "transfer_money", **body)


@app.get("/api/scheduled")
def api_scheduled(request: Request, user: str | None = Depends(customer)) -> Any:
    return _run(user, "list_scheduled_transfers", **dict(request.query_params))


@app.post("/api/scheduled/{scheduled_id}/cancel")
def api_cancel_scheduled(scheduled_id: str, user: str | None = Depends(customer)) -> Any:
    return _run(user, "cancel_scheduled_transfer", scheduled_id=scheduled_id)


@app.get("/api/bills")
def api_bills(user: str | None = Depends(customer)) -> Any:
    return _run(user, "list_bills")


@app.post("/api/bills/{biller_id}/pay")
def api_pay_bill(biller_id: str, body: dict[str, Any] = Body(default_factory=dict), user: str | None = Depends(customer)) -> Any:
    return _run(user, "pay_bill", **{**body, "biller_id": biller_id})


@app.post("/api/bills/{biller_id}/autopay")
def api_autopay(biller_id: str, body: dict[str, Any] = Body(...), user: str | None = Depends(customer)) -> Any:
    return _run(user, "set_bill_autopay", **{"enabled": False, **body, "biller_id": biller_id})


@app.get("/api/cards")
def api_cards(user: str | None = Depends(customer)) -> Any:
    return _run(user, "list_cards")


@app.get("/api/cards/{card_id}")
def api_card(card_id: str, user: str | None = Depends(customer)) -> Any:
    return _run(user, "get_card", card_id=card_id)


@app.post("/api/cards/{card_id}/lock")
def api_lock(card_id: str, body: dict[str, Any] = Body(...), user: str | None = Depends(customer)) -> Any:
    return _run(user, "set_card_lock", card_id=card_id, locked=body.get("locked", True))


@app.patch("/api/cards/{card_id}/controls")
def api_controls(card_id: str, body: dict[str, Any] = Body(...), user: str | None = Depends(customer)) -> Any:
    return _run(user, "update_card_controls", **{**body, "card_id": card_id})


@app.post("/api/cards/{card_id}/report")
def api_report(card_id: str, body: dict[str, Any] = Body(...), user: str | None = Depends(customer)) -> Any:
    return _run(user, "report_card_lost", card_id=card_id, reason=body.get("reason", "lost"))


@app.get("/api/cards/{card_id}/statement")
def api_statement(card_id: str, request: Request, user: str | None = Depends(customer)) -> Any:
    return _run(user, "get_credit_card_statement", **{**dict(request.query_params), "card_id": card_id})


@app.post("/api/cards/{card_id}/pay")
def api_pay_card(card_id: str, body: dict[str, Any] = Body(default_factory=dict), user: str | None = Depends(customer)) -> Any:
    return _run(user, "pay_credit_card", **{**body, "card_id": card_id})


@app.get("/api/deposits")
def api_deposits(user: str | None = Depends(customer)) -> Any:
    return _run(user, "list_fixed_deposits")


@app.get("/api/deposits/rates")
def api_rates(user: str | None = Depends(customer)) -> Any:
    return _run(user, "get_fd_rates")


@app.get("/api/deposits/quote")
def api_fd_quote(request: Request, user: str | None = Depends(customer)) -> Any:
    return _run(user, "get_fd_quote", **dict(request.query_params))


@app.post("/api/deposits")
def api_open_fd(body: dict[str, Any] = Body(...), user: str | None = Depends(customer)) -> Any:
    missing = [k for k in ("amount", "tenure_months") if not str(body.get(k, "")).strip()]
    if missing:
        return JSONResponse({"error": "give an amount and a tenure", "fields": {k: "required" for k in missing}}, status_code=400)
    return _run(user, "open_fixed_deposit", **body)


@app.get("/api/deposits/{deposit_id}/closure")
def api_fd_closure(deposit_id: str, user: str | None = Depends(customer)) -> Any:
    return _run(user, "get_fd_closure_quote", deposit_id=deposit_id)


@app.post("/api/deposits/{deposit_id}/close")
def api_fd_close(deposit_id: str, user: str | None = Depends(customer)) -> Any:
    return _run(user, "close_fixed_deposit", deposit_id=deposit_id)


@app.get("/api/search")
def api_search(q: str, user: str | None = Depends(customer)) -> Any:
    return _run(user, "search_all", query=q)


@app.post("/sandbox/reset")
async def reset_sandbox(x_sandbox_id: str | None = Header(default=None)) -> dict[str, Any]:
    """Experience Center: throw away one visitor's data (see ``sandbox.py``)."""
    if not sandbox.reset(x_sandbox_id):
        raise HTTPException(status_code=404, detail="no such sandbox")
    return {"reset": True}


def run() -> None:
    import uvicorn

    uvicorn.run("bank_api.main:app", host="0.0.0.0", port=int(os.environ.get("BANK_TOOLS_PORT", "8095")))
