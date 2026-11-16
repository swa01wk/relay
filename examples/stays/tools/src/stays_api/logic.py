"""Roostly's business logic — the one implementation behind both the site's API and the Relay
tools. Every rule lives here once: availability, minimum stays, guest limits and pets, nightly
pricing (weekends, peak season), fees, length-of-stay discounts, GST, instant book vs. requests,
cancellation policies, date changes, host messages, reviews and wishlists.

Dates are check-in / check-out days (check-out exclusive); times are IST; money is whole rupees.
Functions for the signed-in guest read the user from ``current_user()``; search and listing reads
work without one.
"""

from __future__ import annotations

import random
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from stays_api import db
from stays_api.seeds import (
    AMENITIES,
    DEFAULT_GUEST,
    DESTINATIONS,
    HOST_REPLIES,
    PROPERTY_TYPES,
    SAMPLE_TRIPS,
    SAMPLE_WISHLISTS,
    SUB_RATINGS,
)

IST = timezone(timedelta(hours=5, minutes=30))
SERVICE_FEE_RATE = 0.12
GST_LOW, GST_HIGH, GST_THRESHOLD = 0.12, 0.18, 7500  # GST on the stay: 18% when the average night is above ₹7,500
PEAK = ((12, 20), (1, 4))  # 20 Dec – 4 Jan: nights cost 30% more
PEAK_MARKUP = 0.30
MAX_NIGHTS = 30
BOOKING_WINDOW_DAYS = 365
MAX_PETS = 2
MAX_INFANTS = 5
HOST_RESPONSE_SECONDS = 120  # the demo host answers a booking request after two minutes
REVIEW_WINDOW_DAYS = 14
MAX_WISHLISTS = 10
# policy -> ((at least this many hours before check-in, refund %), ...); below the last line: the fallback
POLICIES: dict[str, dict[str, Any]] = {
    "flexible": {"label": "Flexible", "tiers": ((24, 100),), "after": 50,
                 "text": "Full refund until 24 hours before check-in; 50% after that."},
    "moderate": {"label": "Moderate", "tiers": ((120, 100),), "after": 50,
                 "text": "Full refund until 5 days before check-in; 50% after that."},
    "strict": {"label": "Strict", "tiers": ((336, 100), (168, 50)), "after": 0,
               "text": "Full refund until 14 days before check-in; 50% until 7 days before; no refund after that."},
}
PAYMENT_METHODS = {"upi": "UPI", "card_on_file": "Card on file (Visa •••• 4242)"}
CANCEL_REASONS = ("change_of_plans", "found_another_place", "travel_restrictions", "booked_by_mistake", "other")
TRIP_STATUSES = ("requested", "upcoming", "in_stay", "completed", "cancelled", "declined")
ROOM_TYPES = {"entire_place": "Entire place", "private_room": "Private room"}
SORTS = ("recommended", "price", "rating", "reviews", "newest")
DESTINATION_KINDS = ("beach", "mountains", "countryside", "lakes", "city")
_ID = re.compile(r"LST-\d+")

_user: ContextVar[str | None] = ContextVar("stays_user", default=None)


class NoUser(Exception):
    """A per-guest call without a guest (the tools service answers 401)."""


@contextmanager
def as_user(user_id: str | None) -> Iterator[None]:
    token = _user.set(user_id or None)
    try:
        yield
    finally:
        _user.reset(token)


def current_user() -> str:
    user_id = _user.get()
    if not user_id:
        raise NoUser()
    _ensure_guest(user_id)
    return user_id


def _optional_user() -> str | None:
    return current_user() if _user.get() else None


# ---------------------------------------------------------------- helpers


def _now() -> datetime:
    return datetime.now(IST)


def _today() -> date:
    return _now().date()


def _error(message: str, **fields: str) -> dict[str, Any]:
    return {"error": message, **({"fields": fields} if fields else {})}


def _parse_date(value: Any, field: str) -> date | dict[str, Any]:
    text = str(value or "").strip().lower()
    if text == "today":
        return _today()
    if text == "tomorrow":
        return _today() + timedelta(days=1)
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return _error(f"{field} must be a date like 2026-12-20", **{field: "not a date"})


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value) if value is not None and str(value).strip() != "" else default
    except (TypeError, ValueError):
        return default


def _listing(listing_id: str | None) -> dict[str, Any] | None:
    key = (listing_id or "").strip().upper()
    return db.get("listings", key) if _ID.fullmatch(key) else None


def _host(host_id: str) -> dict[str, Any]:
    host = db.get("hosts", host_id)
    assert host is not None
    return host


def _destinations(value: str | None) -> list[str] | None:
    """Destination keys for a name, key, state or kind ("Kerala", "beach"); None for no filter."""
    if not value:
        return None
    q = value.strip().lower()
    hits = [k for k, d in DESTINATIONS.items() if q in (k, d["name"].lower(), d["state"].lower(), d["kind"])
            or d["name"].lower().startswith(q) or any(q == a.lower() for a in d["areas"])]
    if not hits and q in ("beaches", "hills", "hill station", "hill stations", "backwaters"):
        kind = {"beaches": "beach", "hills": "mountains", "hill station": "mountains", "hill stations": "mountains", "backwaters": "lakes"}[q]
        hits = [k for k, d in DESTINATIONS.items() if d["kind"] == kind]
    return hits


def _list_arg(value: Any) -> list[str]:
    items = value if isinstance(value, list) else re.split(r"[,\s]+", str(value or ""))
    return [str(v).strip() for v in items if str(v).strip()]


# ---------------------------------------------------------------- calendars and prices


def _seeded_taken(listing_id: str, day: date) -> bool:
    """Nights other guests already booked (deterministic: same for every visitor)."""
    block = day.toordinal() // 3
    rng = random.Random(f"busy:{listing_id}:{block}")
    ahead = (day - _today()).days
    share = 0.42 if ahead < 30 else 0.3 if ahead < 90 else 0.15
    if day.weekday() in (4, 5):
        share += 0.1
    return rng.random() < share


def _reserved(listing_id: str, ignore: str | None = None) -> set[date]:
    nights: set[date] = set()
    for r in db.rows("reservations"):
        if r["listing_id"] != listing_id or r["id"] == ignore or r["status"] in ("cancelled", "declined"):
            continue
        day, end = date.fromisoformat(r["check_in"]), date.fromisoformat(r["check_out"])
        while day < end:
            nights.add(day)
            day += timedelta(days=1)
    return nights


def _nights(check_in: date, check_out: date) -> list[date]:
    return [check_in + timedelta(days=i) for i in range((check_out - check_in).days)]


def _unavailable(listing: dict[str, Any], nights: list[date], ignore: str | None = None, own: set[date] | None = None) -> list[date]:
    reserved = _reserved(listing["id"], ignore)
    own = own or set()
    return [d for d in nights if d in reserved or (d not in own and _seeded_taken(listing["id"], d))]


def _is_peak(day: date) -> bool:
    (m1, d1), (m2, d2) = PEAK
    return (day.month, day.day) >= (m1, d1) or (day.month, day.day) <= (m2, d2)


def _night_price(listing: dict[str, Any], day: date) -> int:
    price = listing["weekend_price"] if day.weekday() in (4, 5) else listing["price"]
    if _is_peak(day):
        price = int(round(price * (1 + PEAK_MARKUP) / 100) * 100)
    return price


def _check_guests(listing: dict[str, Any], adults: int, children: int, infants: int, pets: int) -> dict[str, str]:
    fields: dict[str, str] = {}
    if adults < 1:
        fields["adults"] = "at least one adult"
    if adults + children > listing["max_guests"]:
        fields["adults"] = f"this place sleeps {listing['max_guests']} (adults + children)"
    if infants > MAX_INFANTS:
        fields["infants"] = f"at most {MAX_INFANTS} infants"
    if pets and not listing["pets_allowed"]:
        fields["pets"] = "pets aren't allowed here"
    elif pets > MAX_PETS:
        fields["pets"] = f"at most {MAX_PETS} pets"
    return fields


def _check_dates(listing: dict[str, Any], check_in: date, check_out: date) -> dict[str, str]:
    nights = (check_out - check_in).days
    if check_in < _today() or (check_in == _today() and _now().hour >= 20):
        return {"check_in": "in the past"}
    if (check_in - _today()).days > BOOKING_WINDOW_DAYS:
        return {"check_in": f"bookings open {BOOKING_WINDOW_DAYS} days ahead"}
    if nights < 1:
        return {"check_out": "must be after check-in"}
    if nights < listing["min_nights"]:
        return {"check_out": f"minimum stay is {listing['min_nights']} nights"}
    if nights > MAX_NIGHTS:
        return {"check_out": f"at most {MAX_NIGHTS} nights"}
    return {}


def _quote(listing: dict[str, Any], check_in: date, check_out: date, adults: int, children: int, pets: int) -> dict[str, Any]:
    nights = _nights(check_in, check_out)
    nightly = [{"date": d.isoformat(), "price": _night_price(listing, d), "weekend": d.weekday() in (4, 5), "peak": _is_peak(d)} for d in nights]
    stay = sum(n["price"] for n in nightly)
    extra_guests = max(0, adults + children - listing["guests_included"])
    extra = extra_guests * listing["extra_guest_fee"] * len(nights)
    pct = listing["monthly_discount"] if len(nights) >= 28 else listing["weekly_discount"] if len(nights) >= 7 else 0
    discount = int(round((stay + extra) * pct / 100))
    cleaning = listing["cleaning_fee"]
    pet_fee = listing["pet_fee"] if pets else 0
    taxable = stay + extra - discount + cleaning + pet_fee
    gst_rate = GST_HIGH if (stay / len(nights)) > GST_THRESHOLD else GST_LOW
    gst = int(round(taxable * gst_rate))
    service = int(round(taxable * SERVICE_FEE_RATE))
    return {
        "nights": len(nights),
        "nightly": nightly,
        "average_night": int(round(stay / len(nights))),
        "accommodation": stay,
        "extra_guests": extra_guests,
        "extra_guest_fee": extra,
        "length_discount_pct": pct,
        "length_discount": discount,
        "cleaning_fee": cleaning,
        "pet_fee": pet_fee,
        "service_fee": service,
        "gst_pct": int(gst_rate * 100),
        "gst": gst,
        "total": taxable + gst + service,
    }


# ---------------------------------------------------------------- listings (reads)


def _rating(listing_id: str) -> tuple[float, int, dict[str, float]]:
    mine = [r for r in db.rows("reviews") if r["listing_id"] == listing_id]
    if not mine:
        return 0.0, 0, {}
    avg = round(sum(r["rating"] for r in mine) / len(mine), 2)
    subs = {k: round(sum(r["sub_ratings"].get(k, r["rating"]) for r in mine) / len(mine), 1) for k in SUB_RATINGS}
    return avg, len(mine), subs


def _card(listing: dict[str, Any], quote: dict[str, Any] | None = None) -> dict[str, Any]:
    rating, count, _ = _rating(listing["id"])
    host = _host(listing["host_id"])
    d = DESTINATIONS[listing["destination"]]
    card = {
        "id": listing["id"],
        "title": listing["title"],
        "destination": listing["destination"],
        "destination_name": d["name"],
        "area": listing["area"],
        "state": d["state"],
        "property_type": listing["property_type"],
        "property_type_label": PROPERTY_TYPES[listing["property_type"]],
        "room_type": listing["room_type"],
        "max_guests": listing["max_guests"],
        "bedrooms": listing["bedrooms"],
        "beds": listing["beds"],
        "baths": listing["baths"],
        "price": listing["price"],
        "weekend_price": listing["weekend_price"],
        "rating": rating,
        "review_count": count,
        "superhost": host["superhost"],
        "host_name": host["name"],
        "instant_book": listing["instant_book"],
        "cancellation_policy": listing["cancellation_policy"],
        "pets_allowed": listing["pets_allowed"],
        "amenities": listing["amenities"],
        "hue": listing["hue"],
        "icon": listing["icon"],
        "summary": listing["summary"],
        "is_new": listing["created_days_ago"] < 60,
    }
    if quote:
        card["stay_total"] = quote["total"]
        card["nights"] = quote["nights"]
        card["average_night"] = quote["average_night"]
    return card


def _stay_args(check_in: Any, check_out: Any) -> tuple[date, date] | dict[str, Any] | None:
    if not check_in and not check_out:
        return None
    if not check_in or not check_out:
        return _error("give both check_in and check_out", **{("check_out" if check_in else "check_in"): "required"})
    ci, co = _parse_date(check_in, "check_in"), _parse_date(check_out, "check_out")
    if isinstance(ci, dict):
        return ci
    if isinstance(co, dict):
        return co
    return ci, co


def search_listings(
    *,
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
    min_beds: int | None = None,
    min_baths: int | None = None,
    amenities: str | list[str] | None = None,
    instant_book: bool | None = None,
    superhost: bool | None = None,
    min_rating: float | None = None,
    sort_by: str = "recommended",
    sort_order: str | None = None,
    limit: int = 24,
) -> dict[str, Any]:
    dests = _destinations(destination)
    if dests == []:
        return _error(f"no destination matches {destination} — Roostly has homes in {', '.join(d['name'] for d in DESTINATIONS.values())}",
                      destination="unknown destination")
    stay = _stay_args(check_in, check_out)
    if isinstance(stay, dict):
        return stay
    wanted = [a for a in _list_arg(amenities) if a]
    unknown = [a for a in wanted if a not in AMENITIES]
    if unknown:
        return _error(f"unknown amenity {', '.join(unknown)}", amenities=f"one of {', '.join(AMENITIES)}")
    adults, children, pets = max(1, _int(adults, 1)), _int(children), _int(pets)
    cards = []
    unavailable = 0
    for listing in db.rows("listings"):
        if dests and listing["destination"] not in dests:
            continue
        if property_type and listing["property_type"] != property_type:
            continue
        if room_type and listing["room_type"] != room_type:
            continue
        if adults + children > listing["max_guests"] or (pets and not listing["pets_allowed"]):
            continue
        if min_bedrooms and listing["bedrooms"] < min_bedrooms or min_beds and listing["beds"] < min_beds or min_baths and listing["baths"] < min_baths:
            continue
        if wanted and not all(a in listing["amenities"] for a in wanted):
            continue
        if instant_book is not None and listing["instant_book"] != instant_book:
            continue
        quote = None
        if stay:
            ci, co = stay
            if _check_dates(listing, ci, co) or _unavailable(listing, _nights(ci, co)):
                unavailable += 1
                continue
            quote = _quote(listing, ci, co, adults, children, pets)
        card = _card(listing, quote)
        nightly = card.get("average_night", card["price"])
        if min_price is not None and nightly < min_price or max_price is not None and nightly > max_price:
            continue
        if superhost is not None and card["superhost"] != superhost:
            continue
        if min_rating is not None and card["rating"] < min_rating:
            continue
        cards.append(card)
    key = {
        "price": lambda c: c.get("average_night", c["price"]),
        "rating": lambda c: (c["rating"], c["review_count"]),
        "reviews": lambda c: c["review_count"],
        "newest": lambda c: -db.get("listings", c["id"])["created_days_ago"],  # type: ignore[index]
        "recommended": lambda c: c["rating"] * 2 + (0.6 if c["superhost"] else 0) + (0.3 if c["instant_book"] else 0),
    }.get(sort_by, lambda c: c["rating"])
    descending = sort_order == "desc" if sort_order else sort_by != "price"
    cards.sort(key=key, reverse=descending)
    prices = [c.get("average_night", c["price"]) for c in cards]
    return {
        "destination": destination,
        "check_in": stay[0].isoformat() if stay else None,
        "check_out": stay[1].isoformat() if stay else None,
        "guests": {"adults": adults, "children": children, "infants": _int(infants), "pets": pets},
        "total": len(cards),
        "unavailable_for_dates": unavailable,
        "price_range": [min(prices), max(prices)] if prices else None,
        "listings": cards[: max(1, min(limit, 60))],
    }


def get_listing(*, listing_id: str) -> dict[str, Any]:
    listing = _listing(listing_id)
    if listing is None:
        return _error(f"not_found: no listing {listing_id} — ids look like LST-1004 (search_listings)", listing_id="unknown listing")
    rating, count, subs = _rating(listing["id"])
    host = _host(listing["host_id"])
    reviews = sorted((r for r in db.rows("reviews") if r["listing_id"] == listing["id"]), key=_review_when, reverse=True)
    user_id = _optional_user()
    saved_in = [w["name"] for w in _wishlists(user_id) if listing["id"] in w["listing_ids"]] if user_id else []
    start = _today()
    blocked = [d.isoformat() for d in _unavailable(listing, [start + timedelta(days=i) for i in range(60)])]
    policy = POLICIES[listing["cancellation_policy"]]
    return {
        "listing": {
            **_card(listing),
            "description": listing["description"],
            "guests_included": listing["guests_included"],
            "extra_guest_fee": listing["extra_guest_fee"],
            "cleaning_fee": listing["cleaning_fee"],
            "pet_fee": listing["pet_fee"],
            "weekly_discount": listing["weekly_discount"],
            "monthly_discount": listing["monthly_discount"],
            "min_nights": listing["min_nights"],
            "amenity_labels": [AMENITIES[a] for a in listing["amenities"]],
            "house_rules": {"check_in_from": listing["check_in_from"], "check_out_by": listing["check_out_by"],
                            "pets_allowed": listing["pets_allowed"], "smoking_allowed": listing["smoking_allowed"],
                            "events_allowed": listing["events_allowed"], "max_guests": listing["max_guests"]},
            "cancellation_policy_text": policy["text"],
            "host": {k: host[k] for k in ("id", "name", "superhost", "since", "response_rate", "response_time", "languages")},
            "rating_breakdown": subs,
            "reviews": [_review_view(r) for r in reviews[:6]],
            "booked_nights_next_60_days": blocked,
            "saved_in_wishlists": saved_in,
        }
    }


def check_availability(*, listing_id: str, month: str | None = None, check_in: str | None = None, check_out: str | None = None) -> dict[str, Any]:
    listing = _listing(listing_id)
    if listing is None:
        return _error(f"not_found: no listing {listing_id}", listing_id="unknown listing")
    if check_in or check_out:
        stay = _stay_args(check_in, check_out)
        if isinstance(stay, dict) or stay is None:
            return stay or _error("give check_in and check_out")
        ci, co = stay
        problems = _check_dates(listing, ci, co)
        taken = [d.isoformat() for d in _unavailable(listing, _nights(ci, co))]
        return {"listing_id": listing["id"], "check_in": ci.isoformat(), "check_out": co.isoformat(), "available": not problems and not taken,
                "booked_nights": taken, "problems": problems, "min_nights": listing["min_nights"]}
    first = _parse_date(f"{month}-01" if month and len(month) == 7 else month or _today().replace(day=1).isoformat(), "month")
    if isinstance(first, dict):
        return _error("month must look like 2026-12", month="not a month")
    first = first.replace(day=1)
    days = []
    day = first
    while day.month == first.month:
        past = day < _today()
        days.append({"date": day.isoformat(), "available": not past and not _unavailable(listing, [day]), "price": _night_price(listing, day), "past": past})
        day += timedelta(days=1)
    return {"listing_id": listing["id"], "month": f"{first:%Y-%m}", "min_nights": listing["min_nights"], "days": days,
            "available_nights": sum(1 for d in days if d["available"])}


def get_price_quote(*, listing_id: str, check_in: str, check_out: str, adults: int = 1, children: int = 0, infants: int = 0, pets: int = 0) -> dict[str, Any]:
    listing = _listing(listing_id)
    if listing is None:
        return _error(f"not_found: no listing {listing_id}", listing_id="unknown listing")
    stay = _stay_args(check_in, check_out)
    if isinstance(stay, dict) or stay is None:
        return stay or _error("give check_in and check_out")
    ci, co = stay
    adults, children, infants, pets = max(1, _int(adults, 1)), _int(children), _int(infants), _int(pets)
    problems = {**_check_dates(listing, ci, co), **_check_guests(listing, adults, children, infants, pets)}
    if problems:
        return _error("; ".join(problems.values()), **problems)
    taken = _unavailable(listing, _nights(ci, co))
    quote = _quote(listing, ci, co, adults, children, pets)
    return {"listing": _card(listing), "check_in": ci.isoformat(), "check_out": co.isoformat(), "available": not taken,
            "booked_nights": [d.isoformat() for d in taken], "instant_book": listing["instant_book"], "quote": quote}


def compare_listings(*, listing_ids: list[str], check_in: str | None = None, check_out: str | None = None) -> dict[str, Any]:
    listings = [_listing(i) for i in listing_ids[:4]]
    missing = [i for i, l in zip(listing_ids, listings) if l is None]
    if missing:
        return _error(f"not_found: {', '.join(missing)}", listing_ids="unknown listing")
    if len(listings) < 2:
        return _error("compare needs two to four listings", listing_ids="too few")
    stay = _stay_args(check_in, check_out)
    out = []
    for listing in listings:
        assert listing is not None
        card = _card(listing)
        if isinstance(stay, tuple):
            ci, co = stay
            ok = not _check_dates(listing, ci, co) and not _unavailable(listing, _nights(ci, co))
            card["available_for_dates"] = ok
            if ok:
                card["stay_total"] = _quote(listing, ci, co, 1, 0, 0)["total"]
        card["amenity_labels"] = [AMENITIES[a] for a in listing["amenities"]]
        out.append(card)
    return {"listings": out}


def list_destinations() -> dict[str, Any]:
    listings = db.rows("listings")
    out = []
    for key, d in DESTINATIONS.items():
        mine = [l for l in listings if l["destination"] == key]
        ratings = [_rating(l["id"])[0] for l in mine]
        out.append({"key": key, "name": d["name"], "state": d["state"], "kind": d["kind"], "areas": d["areas"], "listings": len(mine),
                    "price_from": min(l["price"] for l in mine), "price_to": max(l["price"] for l in mine),
                    "avg_rating": round(sum(ratings) / len(ratings), 2), "property_types": sorted({PROPERTY_TYPES[l["property_type"]] for l in mine})})
    return {"destinations": out}


def aggregate_listings(*, metric: str = "count", group_by: str = "destination", destination: str | None = None) -> dict[str, Any]:
    dests = _destinations(destination)
    listings = [l for l in db.rows("listings") if not dests or l["destination"] in dests]
    keyf = {
        "destination": lambda l: DESTINATIONS[l["destination"]]["name"],
        "property_type": lambda l: PROPERTY_TYPES[l["property_type"]],
        "room_type": lambda l: ROOM_TYPES[l["room_type"]],
        "kind": lambda l: DESTINATIONS[l["destination"]]["kind"],
        "bedrooms": lambda l: f"{l['bedrooms']} bedroom{'s' if l['bedrooms'] > 1 else ''}",
    }.get(group_by)
    if keyf is None:
        return _error("group_by must be destination, property_type, room_type, kind or bedrooms", group_by="unknown")
    groups: dict[str, list[dict[str, Any]]] = {}
    for l in listings:
        groups.setdefault(keyf(l), []).append(l)
    value = {
        "count": len,
        "avg_price": lambda ls: int(sum(l["price"] for l in ls) / len(ls)),
        "min_price": lambda ls: min(l["price"] for l in ls),
        "avg_rating": lambda ls: round(sum(_rating(l["id"])[0] for l in ls) / len(ls), 2),
    }.get(metric)
    if value is None:
        return _error("metric must be count, avg_price, min_price or avg_rating", metric="unknown")
    rows_ = sorted(({"group": k, "value": value(v)} for k, v in groups.items()), key=lambda r: -r["value"])
    return {"metric": metric, "group_by": group_by, "rows": rows_}


def get_top_listings(*, rank_by: str = "rating", destination: str | None = None, limit: int = 5) -> dict[str, Any]:
    dests = _destinations(destination)
    cards = [_card(l) for l in db.rows("listings") if not dests or l["destination"] in dests]
    key = {
        "rating": lambda c: (c["rating"], c["review_count"]),
        "reviews": lambda c: c["review_count"],
        "price_low": lambda c: -c["price"],
        "price_high": lambda c: c["price"],
        "value": lambda c: c["rating"] / max(1, c["price"]) * 10000,
    }.get(rank_by)
    if key is None:
        return _error("rank_by must be rating, reviews, price_low, price_high or value", rank_by="unknown")
    return {"rank_by": rank_by, "listings": sorted(cards, key=key, reverse=True)[:limit]}


def _review_when(r: dict[str, Any]) -> str:
    return r.get("created_at") or (_now() - timedelta(days=r.get("days_ago", 0))).isoformat()


def _review_view(r: dict[str, Any]) -> dict[str, Any]:
    return {"id": r["id"], "listing_id": r["listing_id"], "author": r["author"], "rating": r["rating"], "sub_ratings": r["sub_ratings"],
            "comment": r["comment"], "date": _review_when(r)[:10], "mine": bool(r.get("user_id")) and r.get("user_id") == _user.get()}


def list_reviews(*, listing_id: str | None = None, min_rating: int | None = None, max_rating: int | None = None, mine: bool = False, limit: int = 20) -> dict[str, Any]:
    rows_ = db.rows("reviews")
    if mine:
        user_id = current_user()
        rows_ = [r for r in rows_ if r.get("user_id") == user_id]
    if listing_id:
        rows_ = [r for r in rows_ if r["listing_id"] == listing_id.upper()]
    if min_rating:
        rows_ = [r for r in rows_ if r["rating"] >= min_rating]
    if max_rating:
        rows_ = [r for r in rows_ if r["rating"] <= max_rating]
    views = sorted((_review_view(r) for r in rows_), key=lambda r: r["date"], reverse=True)
    return {"reviews": views[:limit], "total": len(views)}


def get_host(*, host_id: str) -> dict[str, Any]:
    host = db.get("hosts", host_id.strip().upper())
    if host is None:
        return _error(f"not_found: no host {host_id}", host_id="unknown host")
    mine = [_card(l) for l in db.rows("listings") if l["host_id"] == host["id"]]
    ratings = [c["rating"] for c in mine if c["review_count"]]
    return {"host": {**host, "listings": mine, "listing_count": len(mine), "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None}}


# ---------------------------------------------------------------- the guest, wishlists


def _ensure_guest(user_id: str) -> None:
    """A new user starts as the demo guest with two wishlists and a short trip history."""
    if db.get("guests", user_id) is not None:
        return
    with db.transaction():
        if db.get("guests", user_id) is not None:
            return
        db.put("guests", {"id": user_id, **DEFAULT_GUEST, "joined": (_today() - timedelta(days=700)).isoformat()})
        for i, w in enumerate(SAMPLE_WISHLISTS, start=1):
            db.put("wishlists", {"id": f"WL-{user_id}-{i}", "user_id": user_id, "name": w["name"], "listing_ids": list(w["listings"]),
                                 "created_at": (_now() - timedelta(days=30 * i)).isoformat()})
        for sample in SAMPLE_TRIPS:
            _seed_trip(user_id, sample)


def _seed_trip(user_id: str, sample: dict[str, Any]) -> None:
    listing = _listing(sample["listing"])
    assert listing is not None
    check_in = _today() + timedelta(days=sample["days"])
    # Upcoming sample trips start on the first nights nobody else has.
    if sample["outcome"] == "upcoming":
        for _ in range(60):
            if not _unavailable(listing, _nights(check_in, check_in + timedelta(days=sample["nights"]))):
                break
            check_in += timedelta(days=1)
    check_out = check_in + timedelta(days=sample["nights"])
    quote = _quote(listing, check_in, check_out, sample["adults"], sample.get("children", 0), 0)
    booked_at = datetime.combine(check_in - timedelta(days=21 if sample["days"] < 0 else min(20, sample["days"] + 10)), time(19, 30), IST)
    if booked_at > _now():
        booked_at = _now() - timedelta(days=3)
    res = _new_reservation(user_id, listing, check_in, check_out, sample["adults"], sample.get("children", 0), 0, 0, quote, "upi",
                           "Hi! Looking forward to the stay.", booked_at, confirmed=True)
    if sample["outcome"] == "cancelled":
        res["status"] = "cancelled"
        res["cancelled_at"] = (datetime.combine(check_in, time(9, 0), IST) - timedelta(days=10)).isoformat()
        res["refund"] = quote["total"]
        res["cancel_reason"] = "change_of_plans"
    if sample.get("review"):
        review_id = f"RVW-U-{res['id']}"
        db.put("reviews", {"id": review_id, "listing_id": listing["id"], "author": DEFAULT_GUEST["name"].split()[0], "user_id": user_id,
                           "rating": sample["review"], "sub_ratings": {k: sample["review"] for k in SUB_RATINGS},
                           "comment": "Lovely, calm place and a very helpful host. Would happily stay again.",
                           "created_at": datetime.combine(check_out + timedelta(days=2), time(10, 0), IST).isoformat()})
        res["review_id"] = review_id
    db.put("reservations", res)


def _profile(user_id: str) -> dict[str, Any]:
    guest = db.get("guests", user_id)
    assert guest is not None
    return guest


def _wishlists(user_id: str | None) -> list[dict[str, Any]]:
    return [w for w in db.rows("wishlists") if w["user_id"] == user_id] if user_id else []


def get_my_context() -> dict[str, Any]:
    user_id = current_user()
    guest = _profile(user_id)
    views = [_trip_view(r) for r in _reservations(user_id)]
    upcoming = sorted((v for v in views if v["status"] in ("upcoming", "requested", "in_stay")), key=lambda v: v["check_in"])
    return {
        "guest": {k: guest[k] for k in ("name", "email", "phone", "city", "verified")},
        "payment_methods": [{"id": k, "label": v if k != "upi" else f"UPI ({guest['upi_id']})"} for k, v in PAYMENT_METHODS.items()],
        "wishlists": [{"id": w["id"], "name": w["name"], "count": len(w["listing_ids"])} for w in _wishlists(user_id)],
        "upcoming_trips": len(upcoming),
        "next_trip": _brief(upcoming[0]) if upcoming else None,
        "trips_taken": sum(1 for v in views if v["status"] == "completed"),
        "lifetime_spend": sum(v["amount_paid"] for v in views),
    }


def list_wishlists() -> dict[str, Any]:
    user_id = current_user()
    out = []
    for w in _wishlists(user_id):
        cards = [_card(l) for i in w["listing_ids"] if (l := _listing(i))]
        out.append({"id": w["id"], "name": w["name"], "count": len(cards), "listings": cards})
    return {"wishlists": out}


def _find_wishlist(user_id: str, wishlist: str | None) -> dict[str, Any] | None:
    lists = _wishlists(user_id)
    if not wishlist:
        return lists[0] if lists else None
    key = wishlist.strip().lower()
    return next((w for w in lists if w["id"].lower() == key or w["name"].lower() == key), None)


def get_wishlist(*, wishlist_id: str) -> dict[str, Any]:
    w = _find_wishlist(current_user(), wishlist_id)
    if w is None:
        return _error(f"not_found: no wishlist {wishlist_id}", wishlist_id="unknown wishlist")
    return {"wishlist": {"id": w["id"], "name": w["name"], "listings": [_card(l) for i in w["listing_ids"] if (l := _listing(i))]}}


def create_wishlist(*, name: str, listing_id: str | None = None) -> dict[str, Any]:
    user_id = current_user()
    name = (name or "").strip()
    if not name or len(name) > 50:
        return _error("give the wishlist a name (up to 50 characters)", name="required")
    with db.transaction():
        lists = _wishlists(user_id)
        if any(w["name"].lower() == name.lower() for w in lists):
            return _error(f"you already have a wishlist called {name}", name="already exists")
        if len(lists) >= MAX_WISHLISTS:
            return _error(f"at most {MAX_WISHLISTS} wishlists")
        listing = _listing(listing_id) if listing_id else None
        if listing_id and listing is None:
            return _error(f"no listing {listing_id}", listing_id="unknown listing")
        numbers = [int(w["id"].rsplit("-", 1)[1]) for w in lists]
        w = {"id": f"WL-{user_id}-{max(numbers, default=0) + 1}", "user_id": user_id, "name": name,
             "listing_ids": [listing["id"]] if listing else [], "created_at": _now().isoformat()}
        db.put("wishlists", w)
    return {"wishlist": {"id": w["id"], "name": name, "count": len(w["listing_ids"])}}


def save_to_wishlist(*, listing_id: str, wishlist: str | None = None) -> dict[str, Any]:
    user_id = current_user()
    listing = _listing(listing_id)
    if listing is None:
        return _error(f"no listing {listing_id}", listing_id="unknown listing")
    with db.transaction():
        w = _find_wishlist(user_id, wishlist)
        if w is None:
            if wishlist:
                return create_wishlist(name=wishlist, listing_id=listing["id"])
            return create_wishlist(name="Saved", listing_id=listing["id"])
        if listing["id"] in w["listing_ids"]:
            return {"wishlist": {"id": w["id"], "name": w["name"], "count": len(w["listing_ids"])}, "note": "already saved"}
        w["listing_ids"].append(listing["id"])
        db.put("wishlists", w)
    return {"wishlist": {"id": w["id"], "name": w["name"], "count": len(w["listing_ids"])}, "saved": listing["title"]}


def remove_from_wishlist(*, listing_id: str, wishlist: str | None = None) -> dict[str, Any]:
    user_id = current_user()
    key = listing_id.strip().upper()
    with db.transaction():
        lists = [_find_wishlist(user_id, wishlist)] if wishlist else _wishlists(user_id)
        touched = [w for w in lists if w and key in w["listing_ids"]]
        if not touched:
            return _error(f"{key} isn't in {'that wishlist' if wishlist else 'any wishlist'}", listing_id="not saved")
        for w in touched:
            w["listing_ids"].remove(key)
            db.put("wishlists", w)
    return {"removed": key, "from": [w["name"] for w in touched]}


# ---------------------------------------------------------------- reservations


def _reservations(user_id: str) -> list[dict[str, Any]]:
    out = []
    for r in db.rows("reservations"):
        if r["user_id"] == user_id:
            out.append(_settle(r))
    return out


def _settle(r: dict[str, Any]) -> dict[str, Any]:
    """The demo host answers a booking request two minutes after it was sent."""
    if r["status"] != "requested":
        return r
    asked = datetime.fromisoformat(r["booked_at"])
    if (_now() - asked).total_seconds() < HOST_RESPONSE_SECONDS:
        return r
    with db.transaction():
        listing = _listing(r["listing_id"])
        assert listing is not None
        nights = _nights(date.fromisoformat(r["check_in"]), date.fromisoformat(r["check_out"]))
        host = _host(listing["host_id"])
        when = (asked + timedelta(seconds=HOST_RESPONSE_SECONDS)).isoformat()
        if _unavailable(listing, nights, ignore=r["id"], own=set(nights)):
            r.update({"status": "declined", "responded_at": when, "refund": r["total"]})
            r["messages"].append({"from": "host", "name": host["name"], "at": when, "text": "Sorry — those dates were just taken. Hope to host you another time!"})
        else:
            r.update({"status": "confirmed", "responded_at": when})
            r["messages"].append({"from": "host", "name": host["name"], "at": when,
                                  "text": f"Hi {r['guest_name'].split()[0]}, happy to host you! Check-in is from {listing['check_in_from']}. See you soon."})
        r.setdefault("history", []).append({"at": when, "event": r["status"], "detail": f"{host['name']} responded"})
        db.put("reservations", r)
    return r


def _check_in_at(listing: dict[str, Any], day: date) -> datetime:
    hour, minute = (int(x) for x in listing["check_in_from"].split(":"))
    return datetime.combine(day, time(hour, minute), IST)


def _refund_pct(listing: dict[str, Any], check_in: date, now: datetime | None = None) -> int | None:
    """Refund % if cancelled now; None once the stay has started."""
    hours = (_check_in_at(listing, check_in) - (now or _now())).total_seconds() / 3600
    if hours <= 0:
        return None
    policy = POLICIES[listing["cancellation_policy"]]
    for threshold, pct in policy["tiers"]:
        if hours >= threshold:
            return pct
    return policy["after"]


def _new_reservation(
    user_id: str, listing: dict[str, Any], check_in: date, check_out: date, adults: int, children: int, infants: int, pets: int,
    quote: dict[str, Any], payment_method: str, message: str | None, booked_at: datetime, confirmed: bool,
) -> dict[str, Any]:
    guest = _profile(user_id)
    numbers = [int(r["id"].split("-")[1]) for r in db.rows("reservations")]
    rid = f"RSV-{max(numbers, default=50000) + 1}"
    host = _host(listing["host_id"])
    messages = []
    if message and message.strip():
        messages.append({"from": "guest", "name": guest["name"], "at": booked_at.isoformat(), "text": message.strip()})
    if confirmed:
        messages.append({"from": "host", "name": host["name"], "at": (booked_at + timedelta(seconds=20)).isoformat(),
                         "text": f"Thanks for booking, {guest['name'].split()[0]}! Check-in is from {listing['check_in_from']}; I'll send directions closer to the date."})
    return {
        "id": rid,
        "code": "RST" + rid[4:] + "".join(chr(65 + (ord(c) * 7 + len(user_id)) % 26) for c in rid[-3:]),
        "user_id": user_id,
        "guest_name": guest["name"],
        "listing_id": listing["id"],
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
        "adults": adults,
        "children": children,
        "infants": infants,
        "pets": pets,
        "status": "confirmed" if confirmed else "requested",
        "payment_method": payment_method,
        "price": quote,
        "total": quote["total"],
        "extra_paid": 0,
        "refund": 0,
        "booked_at": booked_at.isoformat(),
        "messages": messages,
        "history": [{"at": booked_at.isoformat(), "event": "booked" if confirmed else "requested", "detail": f"{quote['nights']} nights, ₹{quote['total']:,}"}],
    }


def _trip_view(r: dict[str, Any]) -> dict[str, Any]:
    listing = _listing(r["listing_id"])
    assert listing is not None
    ci, co = date.fromisoformat(r["check_in"]), date.fromisoformat(r["check_out"])
    now = _now()
    check_in_at = _check_in_at(listing, ci)
    hour, minute = (int(x) for x in listing["check_out_by"].split(":"))
    check_out_at = datetime.combine(co, time(hour, minute), IST)
    status = r["status"]
    if status == "confirmed":
        status = "completed" if now >= check_out_at else "in_stay" if now >= check_in_at else "upcoming"
    pct = _refund_pct(listing, ci) if status in ("upcoming", "requested") else None
    if status == "requested":
        pct = 100
    full_until = None
    policy = POLICIES[listing["cancellation_policy"]]
    if status == "upcoming" and policy["tiers"]:
        full_until = (check_in_at - timedelta(hours=policy["tiers"][0][0])).isoformat()
    review_until = (check_out_at + timedelta(days=REVIEW_WINDOW_DAYS)).isoformat()
    confirmed = r["status"] == "confirmed"
    return {
        "id": r["id"],
        "code": r["code"],
        "status": status,
        "listing": _card(listing),
        "listing_id": listing["id"],
        "check_in": r["check_in"],
        "check_out": r["check_out"],
        "check_in_from": listing["check_in_from"],
        "check_out_by": listing["check_out_by"],
        "nights": (co - ci).days,
        "adults": r["adults"],
        "children": r["children"],
        "infants": r["infants"],
        "pets": r["pets"],
        "guests": r["adults"] + r["children"],
        "payment_method": r["payment_method"],
        "payment_label": PAYMENT_METHODS[r["payment_method"]],
        "price": r["price"],
        "total": r["total"],
        "extra_paid": r.get("extra_paid", 0),
        "refund": r.get("refund", 0),
        "amount_paid": 0 if status in ("requested", "declined") else r["total"] + r.get("extra_paid", 0) - r.get("refund", 0),
        "booked_at": r["booked_at"],
        "cancelled_at": r.get("cancelled_at"),
        "cancellation_policy": listing["cancellation_policy"],
        "cancellation_policy_text": policy["text"],
        "refund_pct_now": pct,
        "full_refund_until": full_until,
        "can_cancel": pct is not None,
        "can_change": status in ("upcoming", "requested"),
        "can_message": status not in ("declined",),
        "can_review": status == "completed" and not r.get("review_id") and now < datetime.fromisoformat(review_until),
        "review_until": review_until if status == "completed" else None,
        "reviewed": bool(r.get("review_id")),
        "house_manual": listing["house_manual"] if confirmed and status in ("upcoming", "in_stay") else None,
        "host": {k: _host(listing["host_id"])[k] for k in ("id", "name", "superhost", "response_time")},
        "messages": r["messages"],
        "history": r.get("history", []),
    }


def _brief(v: dict[str, Any]) -> dict[str, Any]:
    return {k: v[k] for k in ("id", "code", "status", "check_in", "check_out", "nights", "guests", "amount_paid")} | {
        "listing_id": v["listing_id"], "title": v["listing"]["title"], "destination": v["listing"]["destination_name"],
        "area": v["listing"]["area"], "hue": v["listing"]["hue"], "icon": v["listing"]["icon"], "host": v["host"]["name"]}


def reserve_stay(
    *,
    listing_id: str,
    check_in: str,
    check_out: str,
    adults: int = 1,
    children: int = 0,
    infants: int = 0,
    pets: int = 0,
    message_to_host: str | None = None,
    payment_method: str = "upi",
) -> dict[str, Any]:
    user_id = current_user()
    listing = _listing(listing_id)
    if listing is None:
        return _error(f"not_found: no listing {listing_id}", listing_id="unknown listing")
    stay = _stay_args(check_in, check_out)
    if isinstance(stay, dict) or stay is None:
        return stay or _error("give check_in and check_out", check_in="required")
    ci, co = stay
    adults, children, infants, pets = max(1, _int(adults, 1)), _int(children), _int(infants), _int(pets)
    fields = {**_check_dates(listing, ci, co), **_check_guests(listing, adults, children, infants, pets)}
    if payment_method not in PAYMENT_METHODS:
        fields["payment_method"] = f"one of {', '.join(PAYMENT_METHODS)}"
    if message_to_host and len(message_to_host) > 1000:
        fields["message_to_host"] = "up to 1000 characters"
    if not listing["instant_book"] and not (message_to_host or "").strip():
        fields["message_to_host"] = "this host reviews requests — say who's coming and why"
    with db.transaction():
        if not fields:
            taken = _unavailable(listing, _nights(ci, co))
            if taken:
                fields["check_in"] = f"booked on {', '.join(d.strftime('%d %b') for d in taken[:5])}"
        if fields:
            return _error("; ".join(fields.values()), **fields)
        quote = _quote(listing, ci, co, adults, children, pets)
        res = _new_reservation(user_id, listing, ci, co, adults, children, infants, pets, quote, payment_method, message_to_host,
                               _now(), confirmed=listing["instant_book"])
        db.put("reservations", res)
    view = _trip_view(res)
    msg = (f"Booked! {quote['nights']} nights at {listing['title']}, ₹{quote['total']:,}. Code {res['code']}."
           if listing["instant_book"] else
           f"Request sent to {view['host']['name']}. You're only charged if they accept (usually {view['host']['response_time']}).")
    return {"reservation": view, "message": msg}


def list_trips(
    *,
    status: str | None = None,
    destination: str | None = None,
    check_in_from: str | None = None,
    check_in_to: str | None = None,
    sort_by: str = "check_in",
    sort_order: str = "desc",
    limit: int = 20,
) -> dict[str, Any]:
    views = [_trip_view(r) for r in _reservations(current_user())]
    if status:
        views = [v for v in views if v["status"] == status]
    dests = _destinations(destination)
    if dests is not None:
        views = [v for v in views if v["listing"]["destination"] in dests]
    if check_in_from:
        views = [v for v in views if v["check_in"] >= check_in_from[:10]]
    if check_in_to:
        views = [v for v in views if v["check_in"] <= check_in_to[:10]]
    key = {"booked_at": lambda v: v["booked_at"], "amount": lambda v: v["amount_paid"]}.get(sort_by, lambda v: v["check_in"])
    views.sort(key=key, reverse=sort_order != "asc")
    return {"trips": [{**_brief(v), "can_cancel": v["can_cancel"], "can_review": v["can_review"], "refund_pct_now": v["refund_pct_now"]}
                      for v in views[: max(1, min(limit, 50))]], "total": len(views)}


def _own(reservation_id: str) -> dict[str, Any] | None:
    user_id = current_user()
    key = (reservation_id or "").strip().upper()
    r = db.get("reservations", key) or next((x for x in db.rows("reservations") if x["code"] == key), None)
    return _settle(r) if r and r["user_id"] == user_id else None


def get_trip(*, reservation_id: str) -> dict[str, Any]:
    r = _own(reservation_id)
    if r is None:
        return _error(f"not_found: no trip {reservation_id} — ids look like RSV-50004 (list_trips)", reservation_id="unknown trip")
    return {"trip": _trip_view(r)}


def get_cancellation_quote(*, reservation_id: str) -> dict[str, Any]:
    r = _own(reservation_id)
    if r is None:
        return _error(f"not_found: no trip {reservation_id}", reservation_id="unknown trip")
    v = _trip_view(r)
    if not v["can_cancel"]:
        reason = {"cancelled": "already cancelled", "declined": "the host declined it", "in_stay": "your stay has started — message the host",
                  "completed": "the stay is over"}.get(v["status"], "can't be cancelled")
        return {"reservation_id": r["id"], "can_cancel": False, "reason": reason, "policy": v["cancellation_policy_text"]}
    paid = r["total"] + r.get("extra_paid", 0) - r.get("refund", 0)
    pct = v["refund_pct_now"] or 0
    if v["status"] == "requested":
        refund = 0  # nothing was charged
    elif pct == 100:
        refund = paid
    else:
        refund = int(round((paid - r["price"]["service_fee"]) * pct / 100))
    return {"reservation_id": r["id"], "can_cancel": True, "status": v["status"], "refund_pct": pct, "paid": 0 if v["status"] == "requested" else paid,
            "refund": refund, "keep": (0 if v["status"] == "requested" else paid) - refund, "refund_to": v["payment_label"],
            "policy": v["cancellation_policy"], "policy_text": v["cancellation_policy_text"], "full_refund_until": v["full_refund_until"]}


def cancel_reservation(*, reservation_id: str, reason: str = "change_of_plans") -> dict[str, Any]:
    if reason not in CANCEL_REASONS:
        return _error(f"reason must be one of {', '.join(CANCEL_REASONS)}", reason="unknown reason")
    with db.transaction():
        quote = get_cancellation_quote(reservation_id=reservation_id)
        if "error" in quote:
            return quote
        if not quote["can_cancel"]:
            return _error(f"can't cancel: {quote['reason']}", reservation_id=quote["reason"])
        r = _own(reservation_id)
        assert r is not None
        now = _now().isoformat()
        r.update({"status": "cancelled", "cancelled_at": now, "refund": r.get("refund", 0) + quote["refund"], "cancel_reason": reason})
        r["history"].append({"at": now, "event": "cancelled", "detail": f"refund ₹{quote['refund']:,} ({quote['refund_pct']}%)"})
        db.put("reservations", r)
    return {"trip": _trip_view(r), "refund": quote["refund"],
            "message": f"Cancelled. ₹{quote['refund']:,} goes back to {quote['refund_to']} in 5–7 working days." if quote["refund"] else "Cancelled."}


def change_reservation(
    *,
    reservation_id: str,
    check_in: str | None = None,
    check_out: str | None = None,
    adults: int | None = None,
    children: int | None = None,
    infants: int | None = None,
    pets: int | None = None,
) -> dict[str, Any]:
    with db.transaction():
        r = _own(reservation_id)
        if r is None:
            return _error(f"not_found: no trip {reservation_id}", reservation_id="unknown trip")
        v = _trip_view(r)
        if not v["can_change"]:
            return _error("only upcoming trips and open requests can be changed", reservation_id=v["status"])
        listing = _listing(r["listing_id"])
        assert listing is not None
        ci_raw, co_raw = check_in or r["check_in"], check_out or r["check_out"]
        ci, co = _parse_date(ci_raw, "check_in"), _parse_date(co_raw, "check_out")
        if isinstance(ci, dict):
            return ci
        if isinstance(co, dict):
            return co
        a = r["adults"] if adults is None else max(1, _int(adults, 1))
        c = r["children"] if children is None else _int(children)
        i = r["infants"] if infants is None else _int(infants)
        p = r["pets"] if pets is None else _int(pets)
        old_nights = set(_nights(date.fromisoformat(r["check_in"]), date.fromisoformat(r["check_out"])))
        fields = {**_check_dates(listing, ci, co), **_check_guests(listing, a, c, i, p)}
        if not fields:
            taken = _unavailable(listing, _nights(ci, co), ignore=r["id"], own=old_nights)
            if taken:
                fields["check_in"] = f"booked on {', '.join(d.strftime('%d %b') for d in taken[:5])}"
        if fields:
            return _error("; ".join(fields.values()), **fields)
        if (ci.isoformat(), co.isoformat(), a, c, i, p) == (r["check_in"], r["check_out"], r["adults"], r["children"], r["infants"], r["pets"]):
            return _error("nothing to change")
        quote = _quote(listing, ci, co, a, c, p)
        difference = quote["total"] - r["total"]
        # More expensive: pay the difference. Cheaper: refunded only while the stay is fully refundable.
        refundable = v["status"] == "requested" or v["refund_pct_now"] == 100
        charge = max(0, difference)
        refund = -difference if difference < 0 and refundable else 0
        before = f"{r['check_in']}→{r['check_out']}, {r['adults'] + r['children']} guests"
        r.update({"check_in": ci.isoformat(), "check_out": co.isoformat(), "adults": a, "children": c, "infants": i, "pets": p, "price": quote})
        if v["status"] == "requested":
            r["total"] = quote["total"]
        else:
            r["extra_paid"] = r.get("extra_paid", 0) + charge
            r["refund"] = r.get("refund", 0) + refund  # what was first paid stays in total; changes go to extra_paid / refund
        r["history"].append({"at": _now().isoformat(), "event": "changed",
                             "detail": f"{before} → {ci}→{co}, {a + c} guests" + (f"; paid ₹{charge:,}" if charge else f"; refunded ₹{refund:,}" if refund else "")})
        db.put("reservations", r)
    return {"trip": _trip_view(r), "new_total": quote["total"], "charged": charge, "refunded": refund,
            "message": f"Updated to {ci:%d %b}–{co:%d %b}, {a + c} guests." + (f" ₹{charge:,} charged." if charge else f" ₹{refund:,} refunded." if refund else "")}


def message_host(*, reservation_id: str, message: str) -> dict[str, Any]:
    text = (message or "").strip()
    if not text or len(text) > 1000:
        return _error("write a message (up to 1000 characters)", message="required")
    with db.transaction():
        r = _own(reservation_id)
        if r is None:
            return _error(f"not_found: no trip {reservation_id}", reservation_id="unknown trip")
        if r["status"] == "declined":
            return _error("this request was declined; message the host from a new booking", reservation_id="declined")
        listing = _listing(r["listing_id"])
        assert listing is not None
        host = _host(listing["host_id"])
        now = _now()
        r["messages"].append({"from": "guest", "name": r["guest_name"], "at": now.isoformat(), "text": text})
        r["messages"].append({"from": "host", "name": host["name"], "at": (now + timedelta(seconds=5)).isoformat(), "text": _host_reply(listing, r, text)})
        db.put("reservations", r)
    return {"trip_id": r["id"], "messages": r["messages"][-2:]}


def _host_reply(listing: dict[str, Any], r: dict[str, Any], text: str) -> str:
    t = text.lower()
    manual = listing["house_manual"]
    confirmed = r["status"] == "confirmed"
    facts = {
        "check_in_from": listing["check_in_from"],
        "check_in": manual["check_in"] if confirmed else "I'll share the details once the booking is confirmed.",
        "parking": manual["parking"],
        "wifi": manual["wifi"] if confirmed else "shared once you're booked",
        "pets": "Pets are welcome — please keep them off the beds." if listing["pets_allowed"] else "Sorry, this home doesn't allow pets.",
    }
    for key, words in (("early", ("early",)), ("late", ("late check", "late checkout", "check out late")), ("check", ("check-in", "check in", "arrive", "key")),
                       ("park", ("park", "car")), ("wifi", ("wifi", "wi-fi", "internet")), ("pet", ("pet", "dog", "cat")),
                       ("airport", ("airport", "station", "taxi", "pick"))):
        if any(w in t for w in words):
            return HOST_REPLIES[key].format(**facts)
    return f"Thanks for the message! I'll get back to you shortly. — {_host(listing['host_id'])['name']}"


def list_messages(*, reservation_id: str | None = None) -> dict[str, Any]:
    if reservation_id:
        r = _own(reservation_id)
        if r is None:
            return _error(f"not_found: no trip {reservation_id}", reservation_id="unknown trip")
        return {"trip_id": r["id"], "messages": r["messages"]}
    threads = []
    for r in _reservations(current_user()):
        if not r["messages"]:
            continue
        v = _trip_view(r)
        last = r["messages"][-1]
        threads.append({"trip_id": r["id"], "title": v["listing"]["title"], "host": v["host"]["name"], "status": v["status"],
                        "check_in": r["check_in"], "last_message": last["text"], "last_from": last["from"], "last_at": last["at"], "count": len(r["messages"])})
    threads.sort(key=lambda t: t["last_at"], reverse=True)
    return {"threads": threads, "total": len(threads)}


def write_review(
    *,
    reservation_id: str,
    rating: int,
    comment: str,
    cleanliness: int | None = None,
    accuracy: int | None = None,
    communication: int | None = None,
    location: int | None = None,
    check_in: int | None = None,
    value: int | None = None,
) -> dict[str, Any]:
    subs_in = {"cleanliness": cleanliness, "accuracy": accuracy, "communication": communication, "location": location, "check_in": check_in, "value": value}
    fields: dict[str, str] = {}
    rating = _int(rating)
    if not 1 <= rating <= 5:
        fields["rating"] = "1–5 stars"
    for k, val in subs_in.items():
        if val is not None and not 1 <= _int(val) <= 5:
            fields[k] = "1–5 stars"
    if not comment or len(comment.strip()) < 20 or len(comment) > 2000:
        fields["comment"] = "20–2000 characters"
    if fields:
        return _error("check the review", **fields)
    with db.transaction():
        r = _own(reservation_id)
        if r is None:
            return _error(f"not_found: no trip {reservation_id}", reservation_id="unknown trip")
        v = _trip_view(r)
        if not v["can_review"]:
            reason = "already reviewed" if v["reviewed"] else f"reviews open after check-out, for {REVIEW_WINDOW_DAYS} days"
            return _error(f"can't review: {reason}", reservation_id=reason)
        review = {"id": f"RVW-U-{r['id']}", "listing_id": r["listing_id"], "author": r["guest_name"].split()[0], "user_id": r["user_id"],
                  "rating": rating, "sub_ratings": {k: _int(val) if val is not None else rating for k, val in subs_in.items()},
                  "comment": comment.strip(), "created_at": _now().isoformat()}
        db.put("reviews", review)
        r["review_id"] = review["id"]
        db.put("reservations", r)
    return {"review": _review_view(review), "trip": _trip_view(r)}


# ---------------------------------------------------------------- statistics and cross-entity


def aggregate_trips(*, metric: str = "count", group_by: str = "status") -> dict[str, Any]:
    views = [_trip_view(r) for r in _reservations(current_user())]
    keyf = {
        "status": lambda v: v["status"],
        "month": lambda v: v["check_in"][:7],
        "destination": lambda v: v["listing"]["destination_name"],
        "property_type": lambda v: v["listing"]["property_type_label"],
        "host": lambda v: v["host"]["name"],
    }.get(group_by)
    if keyf is None:
        return _error("group_by must be status, month, destination, property_type or host", group_by="unknown")
    value = {"count": len, "sum_paid": lambda vs: sum(v["amount_paid"] for v in vs), "nights": lambda vs: sum(v["nights"] for v in vs if v["status"] != "cancelled"),
             "avg_night": lambda vs: int(sum(v["price"]["average_night"] for v in vs) / len(vs))}.get(metric)
    if value is None:
        return _error("metric must be count, sum_paid, nights or avg_night", metric="unknown")
    groups: dict[str, list[dict[str, Any]]] = {}
    for v in views:
        groups.setdefault(keyf(v), []).append(v)
    rows_ = [{"group": k, "value": value(vs)} for k, vs in groups.items()]
    rows_.sort(key=lambda r: r["group"] if group_by == "month" else -r["value"])
    return {"metric": metric, "group_by": group_by, "rows": rows_}


def get_travel_spend_over_time(*, months: int = 12) -> dict[str, Any]:
    views = [_trip_view(r) for r in _reservations(current_user())]
    today = _today()
    out = []
    for back in range(max(1, min(months, 24)) - 1, -1, -1):
        year, month = today.year, today.month - back
        while month <= 0:
            month += 12
            year -= 1
        key = f"{year}-{month:02d}"
        mine = [v for v in views if v["booked_at"][:7] == key]
        out.append({"month": key, "spend": sum(v["amount_paid"] for v in mine), "bookings": len(mine),
                    "nights_stayed": sum(v["nights"] for v in views if v["check_in"][:7] == key and v["status"] == "completed")})
    return {"months": out, "currency": "INR"}


def list_attention_items() -> dict[str, Any]:
    views = [_trip_view(r) for r in _reservations(current_user())]
    now = _now()
    items = []
    for v in views:
        title = v["listing"]["title"]
        if v["status"] == "requested":
            items.append({"kind": "awaiting_host", "trip_id": v["id"], "text": f"Waiting for {v['host']['name']} to accept your request for {title}."})
        if v["status"] == "upcoming":
            days = (date.fromisoformat(v["check_in"]) - now.date()).days
            if days <= 3:
                items.append({"kind": "check_in_soon", "trip_id": v["id"], "text": f"Check-in at {title} {'today' if days == 0 else f'in {days} day(s)'} from {v['check_in_from']}."})
            if v["full_refund_until"]:
                until = datetime.fromisoformat(v["full_refund_until"])
                if now < until <= now + timedelta(days=4):
                    items.append({"kind": "free_cancellation_ends", "trip_id": v["id"], "text": f"Free cancellation for {title} ends {until:%a %d %b, %H:%M}."})
        if v["can_review"]:
            items.append({"kind": "review", "trip_id": v["id"], "text": f"How was {title}? You can review it until {v['review_until'][:10]}."})
    return {"items": items, "total": len(items)}


def get_overview() -> dict[str, Any]:
    ctx = get_my_context()
    return {"guest": ctx["guest"]["name"], "next_trip": ctx["next_trip"], "upcoming_trips": ctx["upcoming_trips"],
            "recent_trips": list_trips(limit=5)["trips"], "wishlists": ctx["wishlists"], "attention": list_attention_items()["items"]}


def search_all(*, query: str) -> dict[str, Any]:
    q = query.strip().lower()
    hits: list[dict[str, Any]] = []
    for key, d in DESTINATIONS.items():
        if q in d["name"].lower() or q in d["state"].lower() or q == d["kind"] or any(q in a.lower() for a in d["areas"]):
            hits.append({"type": "destination", "id": key, "title": f"{d['name']}, {d['state']}"})
    for l in db.rows("listings"):
        if q in l["title"].lower() or q in l["area"].lower() or q in PROPERTY_TYPES[l["property_type"]].lower():
            hits.append({"type": "listing", "id": l["id"], "title": l["title"]})
    for h in db.rows("hosts"):
        if q in h["name"].lower():
            hits.append({"type": "host", "id": h["id"], "title": h["name"]})
    if _user.get():
        user_id = current_user()
        for r in _reservations(user_id):
            l = _listing(r["listing_id"])
            if l and (q in r["code"].lower() or q in r["id"].lower() or q in l["title"].lower()):
                hits.append({"type": "trip", "id": r["id"], "title": f"{l['title']} · {r['check_in']}"})
        for w in _wishlists(user_id):
            if q in w["name"].lower():
                hits.append({"type": "wishlist", "id": w["id"], "title": w["name"]})
    return {"hits": hits[:25], "total": len(hits)}


def describe_data() -> dict[str, Any]:
    return {
        "currency": "INR (whole rupees)",
        "timezone": "IST (UTC+05:30)",
        "destinations": {k: f"{d['name']} ({d['state']}, {d['kind']})" for k, d in DESTINATIONS.items()},
        "destination_kinds": list(DESTINATION_KINDS),
        "property_types": PROPERTY_TYPES,
        "room_types": ROOM_TYPES,
        "amenities": AMENITIES,
        "sorts": list(SORTS),
        "trip_statuses": list(TRIP_STATUSES),
        "pricing": f"Friday and Saturday nights use the weekend price; 20 Dec–4 Jan nights cost {int(PEAK_MARKUP * 100)}% more. Extra-guest fee per "
                   "night above the included guests; cleaning fee per stay; pet fee per stay; weekly (7+ nights) and monthly (28+) discounts; "
                   f"service fee {int(SERVICE_FEE_RATE * 100)}%; GST {int(GST_LOW * 100)}% (18% when the average night is above ₹{GST_THRESHOLD:,}).",
        "stay_rules": f"Each listing has a minimum stay; at most {MAX_NIGHTS} nights; bookable {BOOKING_WINDOW_DAYS} days ahead; infants don't count "
                      f"towards guests; at most {MAX_PETS} pets where allowed.",
        "booking": "Instant-book listings confirm at once; other hosts get a request (with a message) and accept or decline — the guest is "
                   "charged only on acceptance.",
        "cancellation_policies": {k: p["text"] for k, p in POLICIES.items()},
        "changes": "Upcoming trips can change dates or guests if the nights are free: pay any increase; a decrease is refunded while the trip is fully refundable.",
        "reviews": f"After check-out, for {REVIEW_WINDOW_DAYS} days: 1–5 stars overall plus cleanliness, accuracy, communication, location, check-in, value.",
        "payment_methods": PAYMENT_METHODS,
        "cancel_reasons": list(CANCEL_REASONS),
    }
