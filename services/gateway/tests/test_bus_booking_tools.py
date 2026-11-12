"""The bus booking example's tools service: signed calls, per-traveller data, sandboxes and the
booking rules (seat availability, the women-only seat rule, fares and GST, coupons, cancellation
charges, rescheduling, boarding-point changes, ratings)."""

from __future__ import annotations

import inspect
import json
from datetime import timedelta
from pathlib import Path

import pytest
from starlette.testclient import TestClient

REPO = Path(__file__).resolve().parents[3]


def _as(user: str) -> dict[str, str]:
    return {"X-Relay-User": json.dumps({"id": user})}


@pytest.fixture
def bus(tmp_path, monkeypatch):
    monkeypatch.setenv("BUS_DB_PATH", str(tmp_path / "bus.db"))
    monkeypatch.setenv("BUS_SANDBOX_DIR", str(tmp_path / "sandboxes"))
    monkeypatch.delenv("RELAY_TOOLS_SIGNING_SECRET", raising=False)
    monkeypatch.delenv("BUS_API_TOKEN", raising=False)
    from bus_api.main import app

    return TestClient(app)


def call(client: TestClient, tool: str, user: str | None = "alice", **args):
    return client.post(f"/tools/{tool}", headers=_as(user) if user else {}, json=args)


def _day(days: int) -> str:
    from bus_api import logic

    return (logic._today() + timedelta(days=days)).isoformat()


def _trip_with_free_seats(client: TestClient, days: int = 10, **filters) -> dict:
    trips = call(client, "search_trips", from_city="BLR", to_city="HYD", date=_day(days), **filters).json()["trips"]
    return max(trips, key=lambda t: t["seats_left"])


def _free(client: TestClient, trip_id: str, n: int, women_only: bool = False) -> list[str]:
    seats = call(client, "get_trip", trip_id=trip_id).json()["trip"]["seats"]
    return [s["id"] for s in seats if s["status"] == "available" and s["women_only"] == women_only][:n]


def _book(client: TestClient, trip: dict, seats: list[str], user: str = "alice", genders: list[str] | None = None, **extra):
    detail = call(client, "get_trip", trip_id=trip["trip_id"]).json()["trip"]
    args = {
        "trip_id": trip["trip_id"], "seats": ", ".join(seats),
        "boarding_point": detail["boarding_points"][1]["id"], "dropping_point": detail["dropping_points"][0]["id"],
        "contact_email": "alice@example.com", "contact_phone": "+91 98765 43210", **extra,
    }
    for i, seat in enumerate(seats, start=1):
        args |= {f"passenger_{i}_name": f"Traveller {i}", f"passenger_{i}_age": 30 + i,
                 f"passenger_{i}_gender": (genders or ["male"] * len(seats))[i - 1]}
    return call(client, "book_tickets", user=user, **args)


def test_every_write_needs_approval_and_schemas_match_functions():
    from bus_api.tools import TOOL_SPECS

    writes = {"book_tickets", "cancel_booking", "change_boarding_point", "reschedule_booking", "rate_trip", "add_traveller", "remove_traveller"}
    assert {n for n, s in TOOL_SPECS.items() if s.classification == "side_effecting"} == writes
    for name, spec in TOOL_SPECS.items():
        params = inspect.signature(spec.fn).parameters
        assert set(spec.properties) <= set(params), name
        assert set(spec.required) <= set(spec.properties), name
        required_args = {p for p, v in params.items() if v.default is inspect.Parameter.empty}
        assert required_args <= set(spec.required), name
    # A booking form fits Relay's 20-field limit.
    assert len(TOOL_SPECS["book_tickets"].properties) <= 20


def test_calls_must_be_signed_when_a_secret_is_set(bus, monkeypatch):
    monkeypatch.setenv("RELAY_TOOLS_SIGNING_SECRET", "s3cret")
    assert bus.get("/tools").status_code == 401
    from relay_adapter_tools_http import signed_headers

    body = json.dumps({"from_city": "BLR", "to_city": "CHE"}).encode()
    user = json.dumps({"id": "alice"})
    headers = signed_headers("s3cret", body, operation="tools.call:search_trips", session_id="s1", user=user)
    common = {**headers, "X-Relay-Session": "s1", "X-Relay-User": user, "content-type": "application/json"}
    assert bus.post("/tools/search_trips", content=body, headers=common).status_code == 200
    assert bus.post("/tools/cancel_booking", content=body, headers=common).status_code == 401


def test_search_filters_and_unknown_routes(bus):
    res = call(bus, "search_trips", user=None, from_city="Bangalore", to_city="hyderabad", date=_day(5)).json()
    assert res["total"] >= 3 and res["from_city"] == "Bengaluru"
    sleepers = call(bus, "search_trips", user=None, from_city="BLR", to_city="HYD", date=_day(5), sleeper=True, sort_by="fare").json()["trips"]
    assert sleepers and all(t["sleeper"] for t in sleepers)
    assert [t["fare"] for t in sleepers] == sorted(t["fare"] for t in sleepers)
    none = call(bus, "search_trips", user=None, from_city="Mysuru", to_city="Madurai").json()
    assert none["total"] == 0 and "From Mysuru" in none["note"]
    assert "error" in call(bus, "search_trips", user=None, from_city="BLR", to_city="HYD", date=_day(-1)).json()
    calendar = call(bus, "get_fare_calendar", user=None, from_city="BLR", to_city="HYD", days=7).json()["days"]
    assert len(calendar) == 7 and all(d["buses"] >= 1 for d in calendar[1:])


def test_per_traveller_tools_need_a_user_and_keep_data_apart(bus):
    assert call(bus, "list_bookings", user=None).status_code == 401
    alice = {b["id"] for b in call(bus, "list_bookings").json()["bookings"]}
    bob = {b["id"] for b in call(bus, "list_bookings", user="bob").json()["bookings"]}
    assert alice and bob and not alice & bob
    one_of_alices = next(iter(alice))
    assert "error" in call(bus, "get_booking", user="bob", booking_id=one_of_alices).json()
    assert "error" in call(bus, "cancel_booking", user="bob", booking_id=one_of_alices).json()


def test_booking_prices_gst_coupon_and_seat_rules(bus):
    trip = _trip_with_free_seats(bus, ac=True)
    seats = _free(bus, trip["trip_id"], 2)
    quote = call(bus, "get_fare_quote", trip_id=trip["trip_id"], seats=",".join(seats), coupon_code="WAYLINE10").json()["quote"]
    fare = quote["fare_total"]
    assert quote["discount"] == min(200, round(fare * 0.1)) and quote["gst"] == round((fare - quote["discount"]) * 0.05)
    assert quote["total"] == fare - quote["discount"] + quote["gst"]

    first = call(bus, "check_coupon", user="newbie", code="FIRSTRIDE", trip_id=trip["trip_id"], seats=seats[0]).json()
    assert first["applies"] is False and "first" in first["reason"]  # every demo traveller starts with bookings

    booked = _book(bus, trip, seats, coupon_code="WAYLINE10").json()["booking"]
    assert booked["total"] == quote["total"] and booked["seats"] == seats and booked["pnr"].startswith("WL")
    # The seats are now taken — for everyone.
    again = _book(bus, trip, seats, user="bob").json()
    assert "already booked" in again["fields"]["seats"]
    mine = {s["id"]: s["status"] for s in call(bus, "get_trip", trip_id=trip["trip_id"]).json()["trip"]["seats"]}
    assert mine[seats[0]] == "yours"

    # Women-only seats (next to a woman) are refused for a man and allowed for a woman.
    trip_ids = [t["trip_id"] for t in call(bus, "search_trips", user=None, from_city="BLR", to_city="HYD", date=_day(1)).json()["trips"]]
    women_seat, women_trip = next((s, t) for t in trip_ids for s in _free(bus, t, 1, women_only=True))
    women_trip = {"trip_id": women_trip}
    assert "woman" in _book(bus, women_trip, [women_seat], genders=["male"]).json()["fields"]["seats"]
    assert _book(bus, women_trip, [women_seat], genders=["female"]).json()["booking"]["seats"] == [women_seat]

    bad = _book(bus, trip, _free(bus, trip["trip_id"], 1), contact_email="nope", payment_method="wallet").json()
    assert "contact_email" in bad["fields"]


def test_cancellation_charges_partial_cancel_and_wallet_refund(bus):
    trip = _trip_with_free_seats(bus, days=10)
    seats = _free(bus, trip["trip_id"], 2)
    wallet_before = call(bus, "get_my_context").json()["wallet_balance"]
    booking = _book(bus, trip, seats, payment_method="wallet").json()
    if "error" in booking:  # fares above the ₹750 demo wallet: pay by UPI instead
        booking = _book(bus, trip, seats).json()
        wallet_before = None
    booking = booking["booking"]
    quote = call(bus, "get_cancellation_quote", booking_id=booking["pnr"], seats=seats[0]).json()
    assert quote["charge_pct"] == 10 and quote["refund"] == quote["paid_for_seats"] - quote["cancellation_charge"]
    done = call(bus, "cancel_booking", booking_id=booking["id"], seats=seats[0], reason="change_of_plans").json()
    assert done["booking"]["status"] == "upcoming" and done["booking"]["seats"] == [seats[1]]
    if wallet_before is not None:
        assert call(bus, "get_my_context").json()["wallet_balance"] == wallet_before - booking["total"] + quote["refund"]
    call(bus, "cancel_booking", booking_id=booking["id"])
    assert call(bus, "get_booking", booking_id=booking["id"]).json()["booking"]["status"] == "cancelled"
    assert "error" in call(bus, "cancel_booking", booking_id=booking["id"]).json()

    from bus_api import logic
    assert [logic._cancel_pct(h) for h in (72, 30, 13, 7, 2)] == [10, 25, 50, 75, None]


def test_reschedule_points_and_rating(bus):
    upcoming = call(bus, "list_bookings", status="upcoming", sort_order="desc").json()["bookings"][0]  # 12 days out
    detail = call(bus, "get_booking", booking_id=upcoming["id"]).json()["booking"]
    new_point = detail["boarding_points"][2]["id"]
    assert call(bus, "change_boarding_point", booking_id=upcoming["id"], boarding_point=new_point).json()["booking"]["boarding_point"]["id"] == new_point
    assert "error" in call(bus, "change_boarding_point", booking_id=upcoming["id"], boarding_point="HYD-1").json()

    moved = call(bus, "reschedule_booking", booking_id=upcoming["id"], new_date=_day(20)).json()
    if "error" in moved:  # the same seats are taken that day: take the free ones it suggests
        trip_id = detail["trip"]["schedule_id"] + "-" + _day(20).replace("-", "")
        moved = call(bus, "reschedule_booking", booking_id=upcoming["id"], new_date=_day(20),
                     seats=",".join(_free(bus, trip_id, len(detail["seats"])))).json()
    assert moved["booking"]["journey_date"] == _day(20) and moved["charged"] >= 100
    assert "error" in call(bus, "reschedule_booking", booking_id=upcoming["id"], new_date=_day(21)).json()  # only once

    to_rate = next(b for b in call(bus, "list_bookings").json()["bookings"] if b["can_rate"])
    assert "error" in call(bus, "rate_trip", booking_id=upcoming["id"], rating=5).json()  # not travelled yet
    rated = call(bus, "rate_trip", booking_id=to_rate["id"], rating=3, comment="Late by an hour but comfortable.").json()
    assert rated["review"]["rating"] == 3 and rated["review"]["mine"]
    assert "error" in call(bus, "rate_trip", booking_id=to_rate["id"], rating=4).json()


def test_travellers_and_every_read_tool_answers(bus):
    added = call(bus, "add_traveller", name="Kiran Rao", age=41, gender="male").json()["traveller"]
    assert "error" in call(bus, "add_traveller", name="Kiran Rao", age=41, gender="male").json()
    assert call(bus, "remove_traveller", traveller_id=added["id"]).json()["removed"] == added["id"]

    from bus_api.tools import TOOL_SPECS

    trip = _trip_with_free_seats(bus)
    other = call(bus, "search_trips", from_city="BLR", to_city="HYD", date=_day(10)).json()["trips"][0]["trip_id"]
    samples = {
        "search_trips": {"from_city": "BLR", "to_city": "CHE"},
        "get_trip": {"trip_id": trip["trip_id"]},
        "find_seats": {"trip_id": trip["trip_id"], "count": 2, "preference": "together"},
        "compare_trips": {"trip_ids": [trip["trip_id"], other]},
        "get_fare_calendar": {"from_city": "BLR", "to_city": "CHE"},
        "get_fare_quote": {"trip_id": trip["trip_id"], "seats": _free(bus, trip["trip_id"], 1)[0]},
        "get_operator": {"operator_id": "OP-NSC"},
        "check_coupon": {"code": "NIGHTOWL"},
        "get_booking": {"booking_id": call(bus, "list_bookings").json()["bookings"][0]["id"]},
        "get_cancellation_quote": {"booking_id": call(bus, "list_bookings", status="upcoming").json()["bookings"][0]["id"]},
        "search_all": {"query": "goa"},
    }
    for name, spec in TOOL_SPECS.items():
        if spec.classification != "read_only":
            continue
        res = call(bus, name, **samples.get(name, {}))
        assert res.status_code == 200 and "error" not in res.json(), (name, res.text)


def test_sandboxes_keep_visitors_apart_and_api_errors(bus, monkeypatch):
    a, b = "sandbox_" + "a" * 20, "sandbox_" + "b" * 20
    added = call(bus, "add_traveller", user=a, name="Sandbox Pal", age=20, gender="female").json()
    assert added["traveller"]["name"] == "Sandbox Pal"
    assert len(call(bus, "list_travellers", user=b).json()["travellers"]) == 3
    assert any(t["name"] == "Sandbox Pal" for t in bus.get("/api/travellers", headers={"X-Bus-User": a}).json()["travellers"])
    assert bus.post("/sandbox/reset", headers={"X-Sandbox-Id": a}).json() == {"reset": True}
    assert len(call(bus, "list_travellers", user=a).json()["travellers"]) == 3

    res = bus.post("/api/bookings", headers={"X-Bus-User": "carol"}, json={"trip_id": "SCH-1001-20200101"})
    assert res.status_code == 400 and "seats" in res.json()["fields"]
    assert bus.get("/api/trips/SCH-9999-20261201").status_code == 404
    monkeypatch.setenv("BUS_API_TOKEN", "t0ken")
    assert bus.get("/api/me", headers={"X-Bus-User": "carol"}).status_code == 401
    assert bus.get("/api/me", headers={"X-Bus-User": "carol", "Authorization": "Bearer t0ken"}).status_code == 200


def test_bus_booking_manifest_parses(monkeypatch):
    from relay_gateway.services.agent_service import parse_manifest

    monkeypatch.setenv("RELAY_BUS_TOOLS_URL", "http://bus-tools:8093")
    manifest = parse_manifest(REPO / "agents" / "bus-booking.yaml")
    assert manifest.agent_id == "bus-booking" and manifest.tools_url == "http://bus-tools:8093"
    assert "Wayline" in manifest.system_prompt and "Northstar Coaches" in manifest.keyterms
