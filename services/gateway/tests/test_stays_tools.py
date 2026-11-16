"""The vacation rental example's tools service: signed calls, per-guest data, sandboxes and the
rental rules (availability, minimum stay, guests and pets, pricing and fees, instant book vs.
requests, cancellation policies, date changes, host messages, reviews, wishlists)."""

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
def stays(tmp_path, monkeypatch):
    monkeypatch.setenv("STAYS_DB_PATH", str(tmp_path / "stays.db"))
    monkeypatch.setenv("STAYS_SANDBOX_DIR", str(tmp_path / "sandboxes"))
    monkeypatch.delenv("RELAY_TOOLS_SIGNING_SECRET", raising=False)
    monkeypatch.delenv("STAYS_API_TOKEN", raising=False)
    from stays_api.main import app

    return TestClient(app)


def call(client: TestClient, tool: str, user: str | None = "alice", **args):
    return client.post(f"/tools/{tool}", headers=_as(user) if user else {}, json=args)


def _day(days: int) -> str:
    from stays_api import logic

    return (logic._today() + timedelta(days=days)).isoformat()


def _free_stay(client: TestClient, listing_id: str, nights: int = 3, start: int = 20) -> tuple[str, str]:
    """The first check-in from `start` days ahead with `nights` free nights."""
    for offset in range(start, start + 120):
        ci, co = _day(offset), _day(offset + nights)
        if call(client, "check_availability", user=None, listing_id=listing_id, check_in=ci, check_out=co).json()["available"]:
            return ci, co
    raise AssertionError("no free nights")


def test_every_write_needs_approval_and_schemas_match_functions():
    from stays_api.tools import TOOL_SPECS

    writes = {"reserve_stay", "cancel_reservation", "change_reservation", "message_host", "write_review",
              "create_wishlist", "save_to_wishlist", "remove_from_wishlist"}
    assert {n for n, s in TOOL_SPECS.items() if s.classification == "side_effecting"} == writes
    for name, spec in TOOL_SPECS.items():
        params = inspect.signature(spec.fn).parameters
        assert set(spec.properties) <= set(params), name
        assert set(spec.required) <= set(spec.properties), name
        required_args = {p for p, v in params.items() if v.default is inspect.Parameter.empty}
        assert required_args <= set(spec.required), name
        assert len(spec.properties) <= 20 or spec.classification == "read_only", name  # forms fit Relay's 20 fields


def test_calls_must_be_signed_when_a_secret_is_set(stays, monkeypatch):
    monkeypatch.setenv("RELAY_TOOLS_SIGNING_SECRET", "s3cret")
    assert stays.get("/tools").status_code == 401
    from relay_adapter_tools_http import signed_headers

    body = json.dumps({"destination": "Goa"}).encode()
    user = json.dumps({"id": "alice"})
    headers = signed_headers("s3cret", body, operation="tools.call:search_listings", session_id="s1", user=user)
    common = {**headers, "X-Relay-Session": "s1", "X-Relay-User": user, "content-type": "application/json"}
    assert stays.post("/tools/search_listings", content=body, headers=common).status_code == 200
    assert stays.post("/tools/cancel_reservation", content=body, headers=common).status_code == 401


def test_search_by_destination_kind_dates_and_filters(stays):
    kerala = call(stays, "search_listings", user=None, destination="Kerala").json()
    assert kerala["total"] == 6 and {l["destination"] for l in kerala["listings"]} == {"alleppey", "munnar"}
    pools = call(stays, "search_listings", user=None, destination="beach", amenities=["pool"]).json()["listings"]
    assert pools and all("pool" in l["amenities"] for l in pools)
    pets = call(stays, "search_listings", user=None, pets=1, sort_by="price").json()["listings"]
    assert pets and all(l["pets_allowed"] for l in pets) and [l["price"] for l in pets] == sorted(l["price"] for l in pets)
    dated = call(stays, "search_listings", user=None, destination="Goa", check_in=_day(30), check_out=_day(33), adults=2).json()
    assert all(l["nights"] == 3 and l["stay_total"] > 0 for l in dated["listings"])
    assert dated["total"] + dated["unavailable_for_dates"] == 3
    assert "error" in call(stays, "search_listings", user=None, destination="Atlantis").json()


def test_pricing_rules(stays):
    from stays_api import logic

    listing = logic.db.get("listings", "LST-1001")  # pool villa, sleeps 8, pets allowed
    ci, co = logic.date.fromisoformat(_day(40)), logic.date.fromisoformat(_day(47))
    q = logic._quote(listing, ci, co, 8, 0, 1)
    nightly = sum(n["price"] for n in q["nightly"])
    assert q["nights"] == 7 and q["accommodation"] == nightly
    assert q["length_discount_pct"] == listing["weekly_discount"]
    assert q["extra_guest_fee"] == (8 - listing["guests_included"]) * listing["extra_guest_fee"] * 7
    assert q["pet_fee"] == 600 and q["gst_pct"] == (18 if nightly / 7 > 7500 else 12)
    taxable = q["accommodation"] + q["extra_guest_fee"] - q["length_discount"] + q["cleaning_fee"] + q["pet_fee"]
    assert q["total"] == taxable + q["gst"] + q["service_fee"] and q["service_fee"] == round(taxable * 0.12)
    friday = next(d for d in (ci + timedelta(days=i) for i in range(7)) if d.weekday() == 4)
    assert logic._night_price(listing, friday) == listing["weekend_price"] or logic._is_peak(friday)
    assert logic._night_price(listing, logic.date(2026, 12, 29)) > listing["price"]  # peak season


def test_instant_book_request_flow_and_rules(stays, monkeypatch):
    ci, co = _free_stay(stays, "LST-1002")  # instant-book studio, sleeps 2, no pets
    too_many = call(stays, "reserve_stay", listing_id="LST-1002", check_in=ci, check_out=co, adults=3).json()
    assert "adults" in too_many["fields"]
    assert "pets" in call(stays, "reserve_stay", listing_id="LST-1002", check_in=ci, check_out=co, adults=1, pets=1).json()["fields"]
    booked = call(stays, "reserve_stay", listing_id="LST-1002", check_in=ci, check_out=co, adults=2, payment_method="card_on_file").json()
    trip = booked["reservation"]
    assert trip["status"] == "upcoming" and trip["house_manual"]["wifi"].startswith("Roostly-1002")
    # Those nights are now taken, for everyone.
    assert "booked on" in call(stays, "reserve_stay", user="bob", listing_id="LST-1002", check_in=ci, check_out=co, adults=1).json()["error"]

    # Request to book: needs a message; pending until the host answers; nothing charged meanwhile.
    rci, rco = _free_stay(stays, "LST-1005", nights=2)  # treehouse, request-to-book
    assert "message_to_host" in call(stays, "reserve_stay", listing_id="LST-1005", check_in=rci, check_out=rco, adults=2).json()["fields"]
    req = call(stays, "reserve_stay", listing_id="LST-1005", check_in=rci, check_out=rco, adults=2, message_to_host="Anniversary trip for two.").json()["reservation"]
    assert req["status"] == "requested" and req["amount_paid"] == 0
    from stays_api import logic

    later = logic._now() + timedelta(seconds=logic.HOST_RESPONSE_SECONDS + 5)
    monkeypatch.setattr(logic, "_now", lambda: later)
    accepted = call(stays, "get_trip", reservation_id=req["id"]).json()["trip"]
    assert accepted["status"] == "upcoming" and accepted["amount_paid"] == accepted["total"]
    assert accepted["messages"][-1]["from"] == "host"


def test_cancellation_policies_changes_and_messages(stays):
    from stays_api import logic

    listing = logic.db.get("listings", "LST-1001")  # strict
    ci = logic.date.fromisoformat(_day(30))
    at = logic._check_in_at(listing, ci)
    assert [logic._refund_pct(listing, ci, at - timedelta(hours=h)) for h in (400, 200, 100, -1)] == [100, 50, 0, None]
    flexible = logic.db.get("listings", "LST-1002")
    assert [logic._refund_pct(flexible, ci, logic._check_in_at(flexible, ci) - timedelta(hours=h)) for h in (30, 5)] == [100, 50]

    ci_s, co_s = _free_stay(stays, "LST-1002", nights=2, start=40)
    trip = call(stays, "reserve_stay", listing_id="LST-1002", check_in=ci_s, check_out=co_s, adults=1).json()["reservation"]
    # Longer stay: pay the difference.
    longer = call(stays, "change_reservation", reservation_id=trip["id"], check_out=(logic.date.fromisoformat(co_s) + timedelta(days=1)).isoformat()).json()
    if "error" not in longer:  # the extra night may be taken by someone else
        assert longer["charged"] > 0 and longer["trip"]["nights"] == 3
    assert "error" in call(stays, "change_reservation", reservation_id=trip["id"], adults=5).json()
    reply = call(stays, "message_host", reservation_id=trip["code"], message="What's the wifi password?").json()["messages"][-1]
    assert reply["from"] == "host" and "Roostly-1002" in reply["text"]
    quote = call(stays, "get_cancellation_quote", reservation_id=trip["id"]).json()
    assert quote["refund_pct"] == 100 and quote["refund"] == quote["paid"]
    done = call(stays, "cancel_reservation", reservation_id=trip["id"], reason="change_of_plans").json()
    assert done["trip"]["status"] == "cancelled" and done["trip"]["amount_paid"] == 0
    assert "error" in call(stays, "cancel_reservation", reservation_id=trip["id"]).json()


def test_reviews_wishlists_and_data_apart(stays):
    trips = call(stays, "list_trips").json()["trips"]
    to_review = next(t for t in trips if t["can_review"])
    upcoming = next(t for t in trips if t["status"] == "upcoming")
    assert "error" in call(stays, "write_review", reservation_id=upcoming["id"], rating=5, comment="Can't review before the stay, surely.").json()
    assert "comment" in call(stays, "write_review", reservation_id=to_review["id"], rating=4, comment="Too short").json()["fields"]
    review = call(stays, "write_review", reservation_id=to_review["id"], rating=4, cleanliness=5, comment="Quiet street, fast Wi-Fi, comfy bed. Would stay again.").json()
    assert review["review"]["sub_ratings"]["cleanliness"] == 5 and review["review"]["mine"]

    assert call(stays, "save_to_wishlist", listing_id="LST-1020", wishlist="Rishikesh retreat").json()["wishlist"]["count"] == 1
    assert "Rishikesh retreat" in call(stays, "get_listing", listing_id="LST-1020").json()["listing"]["saved_in_wishlists"]
    assert call(stays, "remove_from_wishlist", listing_id="LST-1020").json()["from"] == ["Rishikesh retreat"]
    assert "error" in call(stays, "create_wishlist", name="Monsoon getaways").json()  # already exists

    assert call(stays, "list_trips", user=None).status_code == 401
    bob = {t["id"] for t in call(stays, "list_trips", user="bob").json()["trips"]}
    assert bob and not bob & {t["id"] for t in trips}
    assert "error" in call(stays, "get_trip", user="bob", reservation_id=to_review["id"]).json()


def test_every_read_tool_answers(stays):
    from stays_api.tools import TOOL_SPECS

    trip_id = call(stays, "list_trips", status="upcoming").json()["trips"][0]["id"]
    ci, co = _free_stay(stays, "LST-1009", nights=2)
    samples = {
        "get_listing": {"listing_id": "LST-1009"},
        "check_availability": {"listing_id": "LST-1009", "month": _day(30)[:7]},
        "get_price_quote": {"listing_id": "LST-1009", "check_in": ci, "check_out": co, "adults": 2},
        "compare_listings": {"listing_ids": ["LST-1009", "LST-1010"]},
        "get_host": {"host_id": "HST-04"},
        "get_wishlist": {"wishlist_id": "Monsoon getaways"},
        "get_trip": {"reservation_id": trip_id},
        "get_cancellation_quote": {"reservation_id": trip_id},
        "search_all": {"query": "goa"},
    }
    for name, spec in TOOL_SPECS.items():
        if spec.classification != "read_only":
            continue
        res = call(stays, name, **samples.get(name, {}))
        assert res.status_code == 200 and "error" not in res.json(), (name, res.text)


def test_sandboxes_and_site_api(stays, monkeypatch):
    a, b = "sandbox_" + "a" * 20, "sandbox_" + "b" * 20
    call(stays, "create_wishlist", user=a, name="Sandbox list")
    assert len(call(stays, "list_wishlists", user=a).json()["wishlists"]) == 3
    assert len(call(stays, "list_wishlists", user=b).json()["wishlists"]) == 2
    assert len(stays.get("/api/wishlists", headers={"X-Stays-User": a}).json()["wishlists"]) == 3
    assert stays.post("/sandbox/reset", headers={"X-Sandbox-Id": a}).json() == {"reset": True}
    assert len(call(stays, "list_wishlists", user=a).json()["wishlists"]) == 2

    res = stays.post("/api/trips", headers={"X-Stays-User": "carol"}, json={"listing_id": "LST-1002"})
    assert res.status_code == 400 and "check_in" in res.json()["fields"]
    assert stays.get("/api/listings/LST-9999").status_code == 404
    assert stays.get("/api/listings", params={"amenities": ["pool", "wifi"]}).json()["total"] >= 1
    monkeypatch.setenv("STAYS_API_TOKEN", "t0ken")
    assert stays.get("/api/me", headers={"X-Stays-User": "carol"}).status_code == 401
    assert stays.get("/api/me", headers={"X-Stays-User": "carol", "Authorization": "Bearer t0ken"}).status_code == 200


def test_stays_manifest_parses(monkeypatch):
    from relay_gateway.services.agent_service import parse_manifest

    monkeypatch.setenv("RELAY_STAYS_TOOLS_URL", "http://stays-tools:8094")
    manifest = parse_manifest(REPO / "agents" / "stays.yaml")
    assert manifest.agent_id == "stays" and manifest.tools_url == "http://stays-tools:8094"
    assert "Roostly" in manifest.system_prompt and "Assagao" in manifest.keyterms
