"""Wayline's backend: the booking API the site calls (``/api/…``) and the Relay tools the
assistant calls (``GET /tools``, ``POST /tools/{name}``). Both run the same ``logic`` functions.

Who the traveller is:
- Relay tools: the signed ``X-Relay-User`` header (the site's server started the session for that
  traveller). Per-traveller tools without one get ``401``.
- Booking API: ``X-Bus-User``, set by the site's server after its own sign-in. The API is for that
  server only (private network); set ``BUS_API_TOKEN`` to require it as a bearer token too.
"""

from __future__ import annotations

import hmac
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from bus_api import logic, sandbox
from bus_api.relay_signature import relay_user, require_relay_signature
from bus_api.tools import TOOL_SPECS, call_tool, tool_manifest

app = FastAPI(title="Wayline booking API + Relay tools", version="0.1.0")


@contextmanager
def _as_traveller(user_id: str | None) -> Iterator[None]:
    """Run on this traveller's data: their sandbox file (Experience Center) and their rows."""
    with sandbox.use(user_id), logic.as_user(user_id):
        yield


@app.exception_handler(logic.NoUser)
async def _no_user(_request: Request, _exc: logic.NoUser) -> JSONResponse:
    return JSONResponse({"detail": "this needs a signed-in traveller"}, status_code=401)


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
        raise HTTPException(status_code=401, detail="this tool needs the session's traveller (X-Relay-User)")
    try:
        with _as_traveller(user["id"] if user else None):
            result = call_tool(name, arguments)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if str(result.get("error", "")).startswith("missing_arguments"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ---------------------------------------------------------------- booking API (for the site's server)


def traveller(
    x_bus_user: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> str | None:
    token = os.environ.get("BUS_API_TOKEN", "").strip()
    if token and not hmac.compare_digest(authorization or "", f"Bearer {token}"):
        raise HTTPException(status_code=401, detail="booking API token required")
    return (x_bus_user or "").strip() or None


def _run(user_id: str | None, fn: Any, **kwargs: Any) -> Any:
    with _as_traveller(user_id):
        result = fn(**{k: v for k, v in kwargs.items() if v is not None and v != ""})
    if isinstance(result, dict) and result.get("error"):
        status = 404 if str(result["error"]).startswith("not_found") else 400
        return JSONResponse(result, status_code=status)
    return result


def _int(value: Any) -> Any:
    return int(value) if isinstance(value, str) and value.strip().isdigit() else value


def _form(body: dict[str, Any], tool: str, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    """The body's fields that the tool accepts, with integer fields converted."""
    props = TOOL_SPECS[tool].properties
    out = {}
    for key, value in body.items():
        if key in props and key not in exclude and value is not None and value != "":
            out[key] = _int(value) if props[key].get("type") == "integer" else value
    return out


@app.get("/api/cities")
def api_cities(user: str | None = Depends(traveller)) -> Any:
    return _run(user, logic.list_cities)


@app.get("/api/routes")
def api_routes(user: str | None = Depends(traveller), from_city: str | None = None) -> Any:
    return _run(user, logic.list_routes, from_city=from_city)


@app.get("/api/offers")
def api_offers(user: str | None = Depends(traveller)) -> Any:
    return _run(user, logic.list_offers)


@app.get("/api/operators")
def api_operators(user: str | None = Depends(traveller)) -> Any:
    return _run(user, logic.list_operators)


@app.get("/api/operators/{operator_id}")
def api_operator(operator_id: str, user: str | None = Depends(traveller)) -> Any:
    return _run(user, logic.get_operator, operator_id=operator_id)


@app.get("/api/search")
def api_search(
    from_city: str,
    to_city: str,
    user: str | None = Depends(traveller),
    date: str | None = None,
    ac: bool | None = None,
    sleeper: bool | None = None,
    bus_type: str | None = None,
    departure_window: str | None = None,
    operator_id: str | None = None,
    max_fare: int | None = None,
    min_rating: float | None = None,
    amenity: str | None = None,
    sort_by: str = "departure",
    sort_order: str | None = None,
) -> Any:
    return _run(
        user, logic.search_trips, from_city=from_city, to_city=to_city, date=date, ac=ac, sleeper=sleeper, bus_type=bus_type,
        departure_window=departure_window, operator_id=operator_id, max_fare=max_fare, min_rating=min_rating, amenity=amenity,
        sort_by=sort_by, sort_order=sort_order, limit=60,
    )


@app.get("/api/fare-calendar")
def api_fare_calendar(from_city: str, to_city: str, user: str | None = Depends(traveller), start_date: str | None = None, days: int = 7) -> Any:
    return _run(user, logic.get_fare_calendar, from_city=from_city, to_city=to_city, start_date=start_date, days=days)


@app.get("/api/trips/{trip_id}")
def api_trip(trip_id: str, user: str | None = Depends(traveller)) -> Any:
    return _run(user, logic.get_trip, trip_id=trip_id)


@app.get("/api/trips/{trip_id}/quote")
def api_quote(trip_id: str, seats: str, user: str | None = Depends(traveller), coupon_code: str | None = None) -> Any:
    return _run(user, logic.get_fare_quote, trip_id=trip_id, seats=seats, coupon_code=coupon_code)


@app.get("/api/me")
def api_me(user: str | None = Depends(traveller)) -> Any:
    return _run(user, logic.get_my_context)


@app.get("/api/travellers")
def api_travellers(user: str | None = Depends(traveller)) -> Any:
    return _run(user, logic.list_travellers)


@app.post("/api/travellers")
def api_add_traveller(body: dict[str, Any] = Body(...), user: str | None = Depends(traveller)) -> Any:
    return _run(user, logic.add_traveller, **_form(body, "add_traveller"))


@app.delete("/api/travellers/{traveller_id}")
def api_remove_traveller(traveller_id: str, user: str | None = Depends(traveller)) -> Any:
    return _run(user, logic.remove_traveller, traveller_id=traveller_id)


@app.get("/api/bookings")
def api_bookings(user: str | None = Depends(traveller), status: str | None = None) -> Any:
    sort_order = "asc" if status == "upcoming" else "desc"
    return _run(user, logic.list_bookings, status=status, sort_order=sort_order, limit=50)


@app.post("/api/bookings")
def api_book(body: dict[str, Any] = Body(...), user: str | None = Depends(traveller)) -> Any:
    fields = _form(body, "book_tickets")
    missing = [k for k in TOOL_SPECS["book_tickets"].required if k not in fields]
    if missing:
        return JSONResponse({"error": "check the booking details", "fields": {k: "required" for k in missing}}, status_code=400)
    return _run(user, logic.book_tickets, **fields)


@app.get("/api/bookings/{booking_id}")
def api_booking(booking_id: str, user: str | None = Depends(traveller)) -> Any:
    return _run(user, logic.get_booking, booking_id=booking_id)


@app.get("/api/bookings/{booking_id}/cancellation-quote")
def api_cancel_quote(booking_id: str, user: str | None = Depends(traveller), seats: str | None = None) -> Any:
    return _run(user, logic.get_cancellation_quote, booking_id=booking_id, seats=seats)


@app.post("/api/bookings/{booking_id}/cancel")
def api_cancel(booking_id: str, body: dict[str, Any] = Body(default_factory=dict), user: str | None = Depends(traveller)) -> Any:
    return _run(user, logic.cancel_booking, booking_id=booking_id, **_form(body, "cancel_booking", ("booking_id",)))


@app.patch("/api/bookings/{booking_id}/points")
def api_points(booking_id: str, body: dict[str, Any] = Body(...), user: str | None = Depends(traveller)) -> Any:
    return _run(user, logic.change_boarding_point, booking_id=booking_id, **_form(body, "change_boarding_point", ("booking_id",)))


@app.post("/api/bookings/{booking_id}/reschedule")
def api_reschedule(booking_id: str, body: dict[str, Any] = Body(...), user: str | None = Depends(traveller)) -> Any:
    fields = _form(body, "reschedule_booking", ("booking_id",))
    if "new_date" not in fields:
        return JSONResponse({"error": "pick a new date", "fields": {"new_date": "required"}}, status_code=400)
    return _run(user, logic.reschedule_booking, booking_id=booking_id, **fields)


@app.post("/api/bookings/{booking_id}/rate")
def api_rate(booking_id: str, body: dict[str, Any] = Body(...), user: str | None = Depends(traveller)) -> Any:
    fields = _form(body, "rate_trip", ("booking_id",))
    if "rating" not in fields:
        return JSONResponse({"error": "choose 1 to 5 stars", "fields": {"rating": "required"}}, status_code=400)
    return _run(user, logic.rate_trip, booking_id=booking_id, **fields)


@app.get("/api/attention")
def api_attention(user: str | None = Depends(traveller)) -> Any:
    return _run(user, logic.list_attention_items)


@app.post("/sandbox/reset")
async def reset_sandbox(x_sandbox_id: str | None = Header(default=None)) -> dict[str, Any]:
    """Experience Center: throw away one visitor's booking data (see ``sandbox.py``)."""
    if not sandbox.reset(x_sandbox_id):
        raise HTTPException(status_code=404, detail="no such sandbox")
    return {"reset": True}


def run() -> None:
    import uvicorn

    uvicorn.run("bus_api.main:app", host="0.0.0.0", port=int(os.environ.get("BUS_TOOLS_PORT", "8093")))
