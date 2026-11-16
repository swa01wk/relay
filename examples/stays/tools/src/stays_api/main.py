"""Roostly's backend: the site's API (``/api/…``) and the Relay tools the assistant calls
(``GET /tools``, ``POST /tools/{name}``). Both run the same ``logic`` functions.

Who the guest is:
- Relay tools: the signed ``X-Relay-User`` header (the site's server started the session for that
  guest). Per-guest tools without one get ``401``.
- Site API: ``X-Stays-User``, set by the site's server after its own sign-in. The API is for that
  server only (private network); set ``STAYS_API_TOKEN`` to require it as a bearer token too.
"""

from __future__ import annotations

import hmac
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from stays_api import logic, sandbox
from stays_api.relay_signature import relay_user, require_relay_signature
from stays_api.tools import TOOL_SPECS, call_tool, tool_manifest

app = FastAPI(title="Roostly API + Relay tools", version="0.1.0")


@contextmanager
def _as_guest(user_id: str | None) -> Iterator[None]:
    """Run on this guest's data: their sandbox file (Experience Center) and their rows."""
    with sandbox.use(user_id), logic.as_user(user_id):
        yield


@app.exception_handler(logic.NoUser)
async def _no_user(_request: Request, _exc: logic.NoUser) -> JSONResponse:
    return JSONResponse({"detail": "this needs a signed-in guest"}, status_code=401)


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
        raise HTTPException(status_code=401, detail="this tool needs the session's guest (X-Relay-User)")
    try:
        with _as_guest(user["id"] if user else None):
            result = call_tool(name, arguments)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if str(result.get("error", "")).startswith("missing_arguments"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ---------------------------------------------------------------- site API (for the site's server)


def guest(
    x_stays_user: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> str | None:
    token = os.environ.get("STAYS_API_TOKEN", "").strip()
    if token and not hmac.compare_digest(authorization or "", f"Bearer {token}"):
        raise HTTPException(status_code=401, detail="site API token required")
    return (x_stays_user or "").strip() or None


def _run(user_id: str | None, fn: Any, **kwargs: Any) -> Any:
    with _as_guest(user_id):
        result = fn(**{k: v for k, v in kwargs.items() if v is not None and v != ""})
    if isinstance(result, dict) and result.get("error"):
        status = 404 if str(result["error"]).startswith("not_found") else 400
        return JSONResponse(result, status_code=status)
    return result


def _form(body: dict[str, Any], tool: str, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    """The body's fields that the tool accepts, with integer fields converted."""
    props = TOOL_SPECS[tool].properties
    out = {}
    for key, value in body.items():
        if key in props and key not in exclude and value is not None and value != "":
            if props[key].get("type") == "integer" and isinstance(value, str) and value.strip().lstrip("-").isdigit():
                value = int(value)
            out[key] = value
    return out


@app.get("/api/destinations")
def api_destinations(user: str | None = Depends(guest)) -> Any:
    return _run(user, logic.list_destinations)


@app.get("/api/listings")
def api_listings(
    user: str | None = Depends(guest),
    destination: str | None = None,
    check_in: str | None = None,
    check_out: str | None = None,
    adults: int = 1,
    children: int = 0,
    infants: int = 0,
    pets: int = 0,
    min_price: int | None = None,
    max_price: int | None = None,
    property_type: str | None = None,
    room_type: str | None = None,
    min_bedrooms: int | None = None,
    amenities: list[str] = Query(default=[]),
    instant_book: bool | None = None,
    superhost: bool | None = None,
    min_rating: float | None = None,
    sort_by: str = "recommended",
) -> Any:
    return _run(
        user, logic.search_listings, destination=destination, check_in=check_in, check_out=check_out, adults=adults, children=children,
        infants=infants, pets=pets, min_price=min_price, max_price=max_price, property_type=property_type, room_type=room_type,
        min_bedrooms=min_bedrooms, amenities=amenities or None, instant_book=instant_book, superhost=superhost, min_rating=min_rating,
        sort_by=sort_by, limit=60,
    )


@app.get("/api/listings/{listing_id}")
def api_listing(listing_id: str, user: str | None = Depends(guest)) -> Any:
    return _run(user, logic.get_listing, listing_id=listing_id)


@app.get("/api/listings/{listing_id}/calendar")
def api_calendar(listing_id: str, user: str | None = Depends(guest), month: str | None = None) -> Any:
    return _run(user, logic.check_availability, listing_id=listing_id, month=month)


@app.get("/api/listings/{listing_id}/quote")
def api_quote(
    listing_id: str, check_in: str, check_out: str, user: str | None = Depends(guest), adults: int = 1, children: int = 0, infants: int = 0, pets: int = 0,
) -> Any:
    return _run(user, logic.get_price_quote, listing_id=listing_id, check_in=check_in, check_out=check_out, adults=adults, children=children,
                infants=infants, pets=pets)


@app.get("/api/hosts/{host_id}")
def api_host(host_id: str, user: str | None = Depends(guest)) -> Any:
    return _run(user, logic.get_host, host_id=host_id)


@app.get("/api/me")
def api_me(user: str | None = Depends(guest)) -> Any:
    return _run(user, logic.get_my_context)


@app.get("/api/wishlists")
def api_wishlists(user: str | None = Depends(guest)) -> Any:
    return _run(user, logic.list_wishlists)


@app.get("/api/wishlists/{wishlist_id}")
def api_wishlist(wishlist_id: str, user: str | None = Depends(guest)) -> Any:
    return _run(user, logic.get_wishlist, wishlist_id=wishlist_id)


@app.post("/api/wishlists")
def api_create_wishlist(body: dict[str, Any] = Body(...), user: str | None = Depends(guest)) -> Any:
    fields = _form(body, "create_wishlist")
    if "name" not in fields:
        return JSONResponse({"error": "give the wishlist a name", "fields": {"name": "required"}}, status_code=400)
    return _run(user, logic.create_wishlist, **fields)


@app.post("/api/wishlists/items")
def api_save(body: dict[str, Any] = Body(...), user: str | None = Depends(guest)) -> Any:
    return _run(user, logic.save_to_wishlist, listing_id=str(body.get("listing_id", "")), wishlist=body.get("wishlist"))


@app.delete("/api/wishlists/items/{listing_id}")
def api_unsave(listing_id: str, user: str | None = Depends(guest), wishlist: str | None = None) -> Any:
    return _run(user, logic.remove_from_wishlist, listing_id=listing_id, wishlist=wishlist)


@app.get("/api/trips")
def api_trips(user: str | None = Depends(guest), status: str | None = None) -> Any:
    return _run(user, logic.list_trips, status=status, sort_order="asc" if status in ("upcoming", "requested") else "desc", limit=50)


@app.post("/api/trips")
def api_reserve(body: dict[str, Any] = Body(...), user: str | None = Depends(guest)) -> Any:
    fields = _form(body, "reserve_stay")
    missing = [k for k in ("listing_id", "check_in", "check_out") if k not in fields]
    if missing:
        return JSONResponse({"error": "choose dates", "fields": {k: "required" for k in missing}}, status_code=400)
    return _run(user, logic.reserve_stay, **fields)


@app.get("/api/trips/{reservation_id}")
def api_trip(reservation_id: str, user: str | None = Depends(guest)) -> Any:
    return _run(user, logic.get_trip, reservation_id=reservation_id)


@app.get("/api/trips/{reservation_id}/cancellation-quote")
def api_cancel_quote(reservation_id: str, user: str | None = Depends(guest)) -> Any:
    return _run(user, logic.get_cancellation_quote, reservation_id=reservation_id)


@app.post("/api/trips/{reservation_id}/cancel")
def api_cancel(reservation_id: str, body: dict[str, Any] = Body(default_factory=dict), user: str | None = Depends(guest)) -> Any:
    return _run(user, logic.cancel_reservation, reservation_id=reservation_id, **_form(body, "cancel_reservation", ("reservation_id",)))


@app.patch("/api/trips/{reservation_id}")
def api_change(reservation_id: str, body: dict[str, Any] = Body(...), user: str | None = Depends(guest)) -> Any:
    return _run(user, logic.change_reservation, reservation_id=reservation_id, **_form(body, "change_reservation", ("reservation_id",)))


@app.post("/api/trips/{reservation_id}/messages")
def api_message(reservation_id: str, body: dict[str, Any] = Body(...), user: str | None = Depends(guest)) -> Any:
    return _run(user, logic.message_host, reservation_id=reservation_id, message=str(body.get("message", "")))


@app.post("/api/trips/{reservation_id}/review")
def api_review(reservation_id: str, body: dict[str, Any] = Body(...), user: str | None = Depends(guest)) -> Any:
    fields = _form(body, "write_review", ("reservation_id",))
    if "rating" not in fields or "comment" not in fields:
        return JSONResponse({"error": "give a rating and a review", "fields": {k: "required" for k in ("rating", "comment") if k not in fields}}, status_code=400)
    return _run(user, logic.write_review, reservation_id=reservation_id, **fields)


@app.get("/api/inbox")
def api_inbox(user: str | None = Depends(guest)) -> Any:
    return _run(user, logic.list_messages)


@app.get("/api/attention")
def api_attention(user: str | None = Depends(guest)) -> Any:
    return _run(user, logic.list_attention_items)


@app.post("/sandbox/reset")
async def reset_sandbox(x_sandbox_id: str | None = Header(default=None)) -> dict[str, Any]:
    """Experience Center: throw away one visitor's data (see ``sandbox.py``)."""
    if not sandbox.reset(x_sandbox_id):
        raise HTTPException(status_code=404, detail="no such sandbox")
    return {"reset": True}


def run() -> None:
    import uvicorn

    uvicorn.run("stays_api.main:app", host="0.0.0.0", port=int(os.environ.get("STAYS_TOOLS_PORT", "8094")))
