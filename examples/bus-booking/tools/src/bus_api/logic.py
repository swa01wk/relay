"""Wayline's business logic — the one implementation behind both the booking API (used by the
site) and the Relay tools (used by the assistant). Every rule lives here once: seat availability
and the women-only seat rule, fares, coupons, GST, booking cut-off, cancellation charges,
rescheduling, boarding-point changes and trip ratings.

Times are Indian Standard Time. Money is whole rupees. Functions for the signed-in traveller read
the user from ``current_user()`` (set per request by ``main.py``); search and trip reads work
without one.
"""

from __future__ import annotations

import hashlib
import random
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
from typing import Any

from bus_api import db
from bus_api.seeds import (
    AMENITIES,
    BUS_TYPES,
    CITIES,
    DEFAULT_TRAVELLER,
    OPERATORS,
    ROUTES,
    SAMPLE_BOOKINGS,
    SAMPLE_TRAVELLERS,
)

IST = timezone(timedelta(hours=5, minutes=30))
GST_RATE = 0.05  # AC buses only
MAX_SEATS = 4
BOOKING_WINDOW_DAYS = 60
BOOKING_CLOSES_MIN = 15  # before departure from the first boarding point
UPPER_BERTH_DISCOUNT = 50
WEEKEND_SURCHARGE = 0.10  # Friday and Sunday departures
RESCHEDULE_FEE = 100
RESCHEDULE_UNTIL_HOURS = 12
CHANGE_POINTS_UNTIL_HOURS = 4
MAX_TRAVELLERS = 8
# (at least this many hours before departure, charge %). Under the last line: no cancellation.
CANCELLATION_POLICY: tuple[tuple[int, int], ...] = ((48, 10), (24, 25), (12, 50), (6, 75))
PAYMENT_METHODS = {"upi": "UPI", "card_on_file": "Card on file (Visa •••• 4242)", "wallet": "Wayline Wallet"}
GENDERS = ("female", "male", "other")
CANCEL_REASONS = ("change_of_plans", "found_another_bus", "booked_by_mistake", "trip_postponed", "other")
BOOKING_STATUSES = ("upcoming", "in_transit", "completed", "cancelled")
DEPARTURE_WINDOWS = {
    "early_morning": ("Before 6 am", 0, 6),
    "morning": ("6 am – 12 pm", 6, 12),
    "afternoon": ("12 pm – 6 pm", 12, 18),
    "night": ("After 6 pm", 18, 24),
}
SORTS = ("departure", "fare", "rating", "duration", "seats_left", "arrival")
_ALIASES = {
    "bangalore": "BLR", "bengaluru": "BLR", "madras": "CHE", "chennai": "CHE", "bombay": "MUM", "mumbai": "MUM",
    "cochin": "COK", "ernakulam": "COK", "kochi": "COK", "mangalore": "MNG", "mangaluru": "MNG", "mysore": "MYS",
    "mysuru": "MYS", "panaji": "GOA", "panjim": "GOA", "goa": "GOA", "hyderabad": "HYD", "secunderabad": "HYD",
    "pune": "PUN", "poona": "PUN", "coimbatore": "CBE", "kovai": "CBE", "vijayawada": "VJA", "bezawada": "VJA",
    "madurai": "MDU",
}
_OPERATORS = {o["id"]: o for o in OPERATORS}
_ROUTES = {r["id"]: r for r in ROUTES}
_TRIP_ID = re.compile(r"(SCH-\d+)-(\d{8})")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_PHONE = re.compile(r"\+?[\d\s-]{10,16}")

_user: ContextVar[str | None] = ContextVar("bus_user", default=None)


class NoUser(Exception):
    """A per-traveller call without a traveller (the tools service answers 401)."""


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
    _ensure_traveller(user_id)
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


def _duration(minutes: int) -> str:
    return f"{minutes // 60}h {minutes % 60:02d}m"


def _city(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    if raw.upper() in CITIES:
        return raw.upper()
    key = raw.lower().split("(")[0].strip()
    if key in _ALIASES:
        return _ALIASES[key]
    for code, city in CITIES.items():
        if city["name"].lower().startswith(key):
            return code
    return None


def _city_name(code: str) -> str:
    return CITIES[code]["name"]


def _parse_date(value: str | None, field: str = "date") -> date | dict[str, Any]:
    if not value:
        return _today()
    text = value.strip().lower()
    if text in ("today", "tonight"):
        return _today()
    if text == "tomorrow":
        return _today() + timedelta(days=1)
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return _error(f"{field} must be a date like 2026-11-20", **{field: "not a date"})


def _seat_ids(value: Any) -> list[str]:
    items = value if isinstance(value, list) else re.split(r"[,\s]+", str(value or ""))
    return [str(s).strip().upper() for s in items if str(s).strip()]


# ---------------------------------------------------------------- trips (a schedule on a date)


def _layout(bus_type: str) -> list[dict[str, Any]]:
    """Seats of a bus: sleepers are 2+1 berths on two decks, seaters 2+2 seats on one."""
    seats: list[dict[str, Any]] = []
    if BUS_TYPES[bus_type]["sleeper"]:
        for deck, prefix in (("lower", "L"), ("upper", "U")):
            for row in range(5):
                n = row * 3 + 1
                seats.append({"id": f"{prefix}{n}", "deck": deck, "row": row, "col": 0, "kind": "sleeper", "window": True, "partner": None})
                seats.append({"id": f"{prefix}{n + 1}", "deck": deck, "row": row, "col": 2, "kind": "sleeper", "window": False, "partner": f"{prefix}{n + 2}"})
                seats.append({"id": f"{prefix}{n + 2}", "deck": deck, "row": row, "col": 3, "kind": "sleeper", "window": True, "partner": f"{prefix}{n + 1}"})
    else:
        for row in range(10):
            n = row * 4 + 1
            for offset, col in enumerate((0, 1, 3, 4)):
                partner = n + (1 if offset in (0, 2) else -1) + offset
                seats.append({"id": f"S{n + offset}", "deck": "main", "row": row, "col": col, "kind": "seat",
                              "window": col in (0, 4), "partner": f"S{partner}"})
    return seats


def _fare_for(schedule: dict[str, Any], day: date) -> int:
    fare = schedule["fare"]
    if day.weekday() in (4, 6):
        fare = int(round(fare * (1 + WEEKEND_SURCHARGE) / 10) * 10 - 1)
    return fare


def _seat_price(trip: dict[str, Any], seat: dict[str, Any]) -> int:
    return trip["fare"] - (UPPER_BERTH_DISCOUNT if seat["deck"] == "upper" else 0)


def _trip(trip_id: str) -> dict[str, Any] | None:
    match = _TRIP_ID.fullmatch((trip_id or "").strip().upper())
    if not match:
        return None
    schedule = db.get("schedules", match.group(1))
    if schedule is None:
        return None
    try:
        day = datetime.strptime(match.group(2), "%Y%m%d").date()
    except ValueError:
        return None
    hour, minute = (int(x) for x in schedule["departs"].split(":"))
    departs = datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST)
    arrives = departs + timedelta(minutes=schedule["duration_min"])
    operator = _OPERATORS[schedule["operator_id"]]
    return {
        "id": f"{schedule['id']}-{day:%Y%m%d}",
        "schedule": schedule,
        "date": day,
        "departs": departs,
        "arrives": arrives,
        "operator": operator,
        "type": BUS_TYPES[schedule["bus_type"]],
        "fare": _fare_for(schedule, day),
        "rating": round(min(5.0, max(1.0, _operator_rating(operator["id"]) + schedule["rating_offset"])), 1),
    }


def _operator_rating(operator_id: str) -> float:
    ratings = [r["rating"] for r in db.rows("reviews") if r["operator_id"] == operator_id]
    return round(sum(ratings) / len(ratings), 1) if ratings else _OPERATORS[operator_id]["rating"]


def _seeded_occupancy(trip: dict[str, Any]) -> dict[str, str]:
    """Seats other travellers already bought (deterministic per trip): seat id -> gender."""
    rng = random.Random(f"occupancy:{trip['id']}")
    days_ahead = (trip["date"] - _today()).days
    share = 0.62 if days_ahead <= 1 else 0.5 if days_ahead <= 3 else 0.36 if days_ahead <= 7 else 0.22
    if trip["date"].weekday() in (4, 6):
        share += 0.15
    share = min(0.9, max(0.08, share + rng.uniform(-0.1, 0.1)))
    seats = [s["id"] for s in _layout(trip["schedule"]["bus_type"])]
    taken = rng.sample(seats, int(len(seats) * share))
    return {seat: ("female" if rng.random() < 0.42 else "male") for seat in taken}


def _occupancy(trip: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every sold seat on the trip: seat id -> {gender, booking_id, user_id}."""
    sold = {seat: {"gender": g, "booking_id": None, "user_id": None} for seat, g in _seeded_occupancy(trip).items()}
    for booking in db.rows("bookings"):
        if booking["trip_id"] != trip["id"]:
            continue
        for p in booking["passengers"]:
            if p["status"] == "confirmed":
                sold[p["seat"]] = {"gender": p["gender"], "booking_id": booking["id"], "user_id": booking["user_id"]}
    return sold


def _seat_map(trip: dict[str, Any], user_id: str | None) -> list[dict[str, Any]]:
    sold = _occupancy(trip)
    seats = []
    for seat in _layout(trip["schedule"]["bus_type"]):
        taken = sold.get(seat["id"])
        partner = sold.get(seat["partner"]) if seat["partner"] else None
        if taken is None:
            status = "available"
        elif user_id and taken["user_id"] == user_id:
            status = "yours"
        else:
            status = "booked_female" if taken["gender"] == "female" else "booked"
        seats.append({
            **{k: seat[k] for k in ("id", "deck", "row", "col", "kind", "window")},
            "price": _seat_price(trip, seat),
            "status": status,
            # The seat next to a woman can only be booked by a woman.
            "women_only": status == "available" and partner is not None and partner["gender"] == "female",
        })
    return seats


def _points(trip: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    src, dst = trip["schedule"]["from"], trip["schedule"]["to"]
    boarding = [
        {"id": f"{src}-{i + 1}", "name": name, "landmark": landmark, "time": (trip["departs"] + timedelta(minutes=offset)).isoformat()}
        for i, ((name, landmark), offset) in enumerate(zip(CITIES[src]["points"], (0, 20, 40, 60)))
    ]
    dropping = [
        {"id": f"{dst}-{i + 1}", "name": name, "landmark": landmark, "time": (trip["arrives"] - timedelta(minutes=offset)).isoformat()}
        for i, ((name, landmark), offset) in enumerate(zip(CITIES[dst]["points"], (45, 30, 15, 0)))
    ]
    return boarding, dropping


def _window(hour: int) -> str:
    return next(k for k, (_, lo, hi) in DEPARTURE_WINDOWS.items() if lo <= hour < hi)


def _card(trip: dict[str, Any], seats: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The compact trip shape used in lists."""
    s = trip["schedule"]
    seats = seats if seats is not None else _seat_map(trip, None)
    free = [x for x in seats if x["status"] == "available"]
    boarding, dropping = _points(trip)
    return {
        "trip_id": trip["id"],
        "schedule_id": s["id"],
        "from": s["from"],
        "from_city": _city_name(s["from"]),
        "to": s["to"],
        "to_city": _city_name(s["to"]),
        "date": trip["date"].isoformat(),
        "operator": trip["operator"]["name"],
        "operator_id": trip["operator"]["id"],
        "hue": trip["operator"]["hue"],
        "bus_type": s["bus_type"],
        "bus_type_label": trip["type"]["label"],
        "ac": trip["type"]["ac"],
        "sleeper": trip["type"]["sleeper"],
        "departs": trip["departs"].isoformat(),
        "arrives": trip["arrives"].isoformat(),
        "arrives_next_day": (trip["arrives"].date() - trip["date"]).days,
        "duration_min": s["duration_min"],
        "duration": _duration(s["duration_min"]),
        "departure_window": _window(trip["departs"].hour),
        "fare": min((x["price"] for x in free), default=trip["fare"]),
        "fare_max": trip["fare"],
        "seats_left": len(free),
        "seats_total": len(seats),
        "women_only_seats": sum(1 for x in free if x["women_only"]),
        "rating": trip["rating"],
        "amenities": s["amenities"],
        "boarding_from": boarding[0]["name"],
        "dropping_at": dropping[-1]["name"],
        "bookable": _bookable(trip),
    }


def _bookable(trip: dict[str, Any]) -> bool:
    return trip["departs"] - timedelta(minutes=BOOKING_CLOSES_MIN) > _now() and (trip["date"] - _today()).days <= BOOKING_WINDOW_DAYS


def _trips_on(src: str, dst: str, day: date) -> list[dict[str, Any]]:
    route_id = f"{src}-{dst}"
    trips = []
    for schedule in db.rows("schedules"):
        if schedule["route"] == route_id:
            trip = _trip(f"{schedule['id']}-{day:%Y%m%d}")
            if trip:
                trips.append(trip)
    return trips


# ---------------------------------------------------------------- search and trip reads


def search_trips(
    *,
    from_city: str,
    to_city: str,
    date: str | None = None,
    ac: bool | None = None,
    sleeper: bool | None = None,
    bus_type: str | None = None,
    departure_window: str | None = None,
    operator_id: str | None = None,
    max_fare: int | None = None,
    min_rating: float | None = None,
    amenity: str | None = None,
    min_seats: int | None = None,
    sort_by: str = "departure",
    sort_order: str | None = None,
    limit: int = 30,
) -> dict[str, Any]:
    src, dst = _city(from_city), _city(to_city)
    if not src or not dst:
        bad = {k: "unknown city" for k, v in (("from_city", src), ("to_city", dst)) if not v}
        return _error(f"unknown city — Wayline serves {', '.join(c['name'] for c in CITIES.values())}", **bad)
    if src == dst:
        return _error("from and to are the same city", to_city="same as from")
    day = _parse_date(date)
    if isinstance(day, dict):
        return day
    if day < _today():
        return _error("that date has passed", date="in the past")
    if (day - _today()).days > BOOKING_WINDOW_DAYS:
        return _error(f"bookings open {BOOKING_WINDOW_DAYS} days ahead", date="too far ahead")
    route = _ROUTES.get(f"{src}-{dst}")
    base = {"from": src, "from_city": _city_name(src), "to": dst, "to_city": _city_name(dst), "date": day.isoformat()}
    if route is None:
        served = sorted({_city_name(r["to"]) for r in ROUTES if r["from"] == src})
        return {**base, "trips": [], "total": 0, "note": f"No Wayline buses from {_city_name(src)} to {_city_name(dst)}. "
                f"From {_city_name(src)} we go to {', '.join(served)}."}
    cards = []
    for trip in _trips_on(src, dst, day):
        if not _bookable(trip):
            continue
        card = _card(trip)
        if ac is not None and card["ac"] != ac:
            continue
        if sleeper is not None and card["sleeper"] != sleeper:
            continue
        if bus_type and card["bus_type"] != bus_type:
            continue
        if departure_window and card["departure_window"] != departure_window:
            continue
        if operator_id and card["operator_id"] != operator_id.upper():
            continue
        if max_fare is not None and card["fare"] > max_fare:
            continue
        if min_rating is not None and card["rating"] < min_rating:
            continue
        if amenity and amenity not in card["amenities"]:
            continue
        if min_seats is not None and card["seats_left"] < min_seats:
            continue
        cards.append(card)
    key = {
        "departure": lambda c: c["departs"], "fare": lambda c: c["fare"], "rating": lambda c: c["rating"],
        "duration": lambda c: c["duration_min"], "seats_left": lambda c: c["seats_left"], "arrival": lambda c: c["arrives"],
    }.get(sort_by, lambda c: c["departs"])
    descending = sort_order == "desc" if sort_order else sort_by in ("rating", "seats_left")
    cards.sort(key=key, reverse=descending)
    return {
        **base,
        "distance_km": route["distance_km"],
        "total": len(cards),
        "cheapest_fare": min((c["fare"] for c in cards), default=None),
        "trips": cards[: max(1, min(limit, 60))],
    }


def get_trip(*, trip_id: str) -> dict[str, Any]:
    trip = _trip(trip_id)
    if trip is None:
        return _error(f"not_found: no trip {trip_id} — trip ids look like SCH-1042-20261120 (find them with search_trips)", trip_id="unknown trip")
    user_id = _optional_user()
    seats = _seat_map(trip, user_id)
    boarding, dropping = _points(trip)
    reviews = sorted((r for r in db.rows("reviews") if r["operator_id"] == trip["operator"]["id"]), key=_review_when, reverse=True)[:3]
    return {
        "trip": {
            **_card(trip, seats),
            "distance_km": trip["schedule"]["distance_km"],
            "amenity_labels": [AMENITIES[a] for a in trip["schedule"]["amenities"]],
            "boarding_points": boarding,
            "dropping_points": dropping,
            "decks": sorted({s["deck"] for s in seats}, key=["lower", "upper", "main"].index),
            "seats": seats,
            "gst_pct": int(GST_RATE * 100) if trip["type"]["ac"] else 0,
            "upper_berth_discount": UPPER_BERTH_DISCOUNT if trip["type"]["sleeper"] else 0,
            "cancellation_policy": _policy_lines(),
            "latest_reviews": [_review_view(r) for r in reviews],
        }
    }


def find_seats(*, trip_id: str, count: int = 1, preference: str = "any", travellers_gender: str | None = None) -> dict[str, Any]:
    trip = _trip(trip_id)
    if trip is None:
        return _error(f"not_found: no trip {trip_id}", trip_id="unknown trip")
    if not 1 <= count <= MAX_SEATS:
        return _error(f"choose 1 to {MAX_SEATS} seats", count="out of range")
    seats = [s for s in _seat_map(trip, None) if s["status"] == "available"]
    if travellers_gender != "female":
        seats = [s for s in seats if not s["women_only"]]
    by_id = {s["id"]: s for s in seats}
    layout = {s["id"]: s for s in _layout(trip["schedule"]["bus_type"])}
    pick = _pick_seats([s["id"] for s in seats], layout, count, preference, by_id)
    note = None
    if len(pick) < count:
        return {"trip_id": trip["id"], "seats": pick, "note": f"only {len(pick)} suitable seat(s) left"}
    if preference == "together" and count >= 2 and not any(layout[a]["partner"] == b for a in pick for b in pick):
        note = "no side-by-side seats left; these are the closest free seats"
    return {"trip_id": trip["id"], "seats": pick, "prices": {sid: by_id[sid]["price"] for sid in pick},
            "fare_total": sum(by_id[sid]["price"] for sid in pick), "preference": preference, "note": note}


def _pick_seats(free: list[str], layout: dict[str, dict[str, Any]], count: int, preference: str, info: dict[str, dict[str, Any]] | None = None) -> list[str]:
    """Free seats for ``count`` travellers: side-by-side pairs first for "together", else by preference."""
    pick: list[str] = []
    if preference == "together" and count >= 2:
        for sid in free:
            partner = layout[sid]["partner"]
            if partner in free and sid not in pick and partner not in pick and len(pick) + 2 <= count:
                pick += [sid, partner]
        # Fill up with the free seats nearest (by row) to those already picked.
        rows = [layout[p]["row"] for p in pick] or [0]
        rest = sorted((s for s in free if s not in pick), key=lambda s: min(abs(layout[s]["row"] - r) for r in rows))
        return (pick + rest)[:count]
    wanted = {
        "window": lambda s: layout[s]["window"],
        "aisle": lambda s: not layout[s]["window"],
        "lower": lambda s: layout[s]["deck"] == "lower",
        "upper": lambda s: layout[s]["deck"] == "upper",
    }.get(preference, lambda s: True)
    return ([s for s in free if wanted(s)] + [s for s in free if not wanted(s)])[:count]


def compare_trips(*, trip_ids: list[str]) -> dict[str, Any]:
    trips = [_trip(t) for t in trip_ids[:4]]
    missing = [t for t, trip in zip(trip_ids, trips) if trip is None]
    if missing:
        return _error(f"not_found: {', '.join(missing)}", trip_ids="unknown trip")
    if len(trips) < 2:
        return _error("compare needs two to four trips", trip_ids="too few")
    return {"trips": [{**_card(t), "amenity_labels": [AMENITIES[a] for a in t["schedule"]["amenities"]]} for t in trips if t]}


def get_fare_calendar(*, from_city: str, to_city: str, start_date: str | None = None, days: int = 14, bus_type: str | None = None) -> dict[str, Any]:
    src, dst = _city(from_city), _city(to_city)
    if not src or not dst or f"{src}-{dst}" not in _ROUTES:
        return _error("no Wayline route between those cities", from_city="no route")
    start = _parse_date(start_date, "start_date")
    if isinstance(start, dict):
        return start
    start = max(start, _today())
    out = []
    for offset in range(max(1, min(days, 31))):
        day = start + timedelta(days=offset)
        if (day - _today()).days > BOOKING_WINDOW_DAYS:
            break
        cards = [_card(t) for t in _trips_on(src, dst, day) if _bookable(t)]
        if bus_type:
            cards = [c for c in cards if c["bus_type"] == bus_type]
        out.append({
            "date": day.isoformat(),
            "weekday": day.strftime("%a"),
            "cheapest_fare": min((c["fare"] for c in cards if c["seats_left"]), default=None),
            "buses": len(cards),
            "seats_left": sum(c["seats_left"] for c in cards),
        })
    return {"from_city": _city_name(src), "to_city": _city_name(dst), "days": out}


def list_cities() -> dict[str, Any]:
    return {"cities": [
        {"code": code, "name": c["name"], "state": c["state"], "points": [p[0] for p in c["points"]],
         "destinations": sorted(_city_name(r["to"]) for r in ROUTES if r["from"] == code)}
        for code, c in CITIES.items()
    ]}


def list_routes(*, from_city: str | None = None) -> dict[str, Any]:
    src = _city(from_city) if from_city else None
    if from_city and not src:
        return _error("unknown city", from_city="unknown city")
    schedules = db.rows("schedules")
    out = []
    for route in ROUTES:
        if src and route["from"] != src:
            continue
        mine = [s for s in schedules if s["route"] == route["id"]]
        out.append({
            "route": route["id"], "from": route["from"], "from_city": _city_name(route["from"]), "to": route["to"],
            "to_city": _city_name(route["to"]), "distance_km": route["distance_km"], "typical_duration": _duration(route["duration_min"]),
            "buses_per_day": len(mine), "fares_from": min(s["fare"] for s in mine) if mine else None,
            "operators": sorted({_OPERATORS[s["operator_id"]]["name"] for s in mine}),
        })
    return {"routes": out, "total": len(out)}


def list_operators() -> dict[str, Any]:
    schedules = db.rows("schedules")
    out = []
    for op in OPERATORS:
        mine = [s for s in schedules if s["operator_id"] == op["id"]]
        out.append({
            "id": op["id"], "name": op["name"], "rating": _operator_rating(op["id"]),
            "review_count": sum(1 for r in db.rows("reviews") if r["operator_id"] == op["id"]),
            "buses_per_day": len(mine), "routes": sorted({s["route"] for s in mine}),
            "bus_types": sorted({BUS_TYPES[s["bus_type"]]["label"] for s in mine}),
        })
    return {"operators": sorted(out, key=lambda o: -o["rating"])}


def get_operator(*, operator_id: str) -> dict[str, Any]:
    op = next((o for o in list_operators()["operators"] if o["id"] == operator_id.upper() or o["name"].lower() == operator_id.lower()), None)
    if op is None:
        return _error(f"not_found: no operator {operator_id}", operator_id="unknown operator")
    reviews = sorted((r for r in db.rows("reviews") if r["operator_id"] == op["id"]), key=_review_when, reverse=True)
    dist = {n: sum(1 for r in reviews if r["rating"] == n) for n in range(5, 0, -1)}
    return {"operator": {**op, "rating_breakdown": dist, "reviews": [_review_view(r) for r in reviews[:8]]}}


def _review_when(r: dict[str, Any]) -> str:
    return r.get("created_at") or (_now() - timedelta(days=r.get("days_ago", 0))).isoformat()


def _review_view(r: dict[str, Any]) -> dict[str, Any]:
    when = _review_when(r)
    return {"id": r["id"], "operator": _OPERATORS[r["operator_id"]]["name"], "operator_id": r["operator_id"], "route": r["route"],
            "author": r["author"], "rating": r["rating"], "comment": r["comment"], "date": when[:10], "mine": bool(r.get("user_id")) and r.get("user_id") == _user.get()}


def list_reviews(*, operator_id: str | None = None, min_rating: int | None = None, max_rating: int | None = None, mine: bool = False, limit: int = 20) -> dict[str, Any]:
    rows_ = db.rows("reviews")
    if mine:
        user_id = current_user()
        rows_ = [r for r in rows_ if r.get("user_id") == user_id]
    if operator_id:
        rows_ = [r for r in rows_ if r["operator_id"] == operator_id.upper()]
    if min_rating:
        rows_ = [r for r in rows_ if r["rating"] >= min_rating]
    if max_rating:
        rows_ = [r for r in rows_ if r["rating"] <= max_rating]
    views = sorted((_review_view(r) for r in rows_), key=lambda r: r["date"], reverse=True)
    return {"reviews": views[:limit], "total": len(views)}


def get_top_operators(*, rank_by: str = "rating", route: str | None = None, limit: int = 5) -> dict[str, Any]:
    ops = list_operators()["operators"]
    if route:
        ops = [o for o in ops if route.upper() in o["routes"]]
    key = {"rating": lambda o: o["rating"], "buses_per_day": lambda o: o["buses_per_day"], "review_count": lambda o: o["review_count"]}.get(rank_by, lambda o: o["rating"])
    return {"rank_by": rank_by, "operators": sorted(ops, key=key, reverse=True)[:limit]}


# ---------------------------------------------------------------- coupons and quotes


def list_offers() -> dict[str, Any]:
    return {"offers": [{k: c[k] for k in ("code", "title", "description")} for c in db.rows("coupons")]}


def _coupon_discount(code: str | None, trip: dict[str, Any], fare_total: int, seat_count: int, user_id: str | None) -> tuple[int, str | None]:
    if not code:
        return 0, None
    coupon = db.get("coupons", code.strip().upper())
    if coupon is None:
        return 0, f"{code.upper()} isn't a Wayline offer code"
    if coupon.get("min_fare") and fare_total < coupon["min_fare"]:
        return 0, f"{coupon['code']} needs a fare of ₹{coupon['min_fare']} or more"
    if coupon.get("min_seats") and seat_count < coupon["min_seats"]:
        return 0, f"{coupon['code']} needs {coupon['min_seats']} or more seats"
    if coupon.get("night_only") and trip["departs"].hour < 21:
        return 0, f"{coupon['code']} is only for buses leaving at 9 pm or later"
    if coupon.get("first_booking") and user_id and any(b["user_id"] == user_id for b in db.rows("bookings")):
        return 0, f"{coupon['code']} is only for your first Wayline booking"
    if coupon["kind"] == "percent":
        discount = int(round(fare_total * coupon["value"] / 100))
        discount = min(discount, coupon.get("max_discount") or discount)
    else:
        discount = coupon["value"]
    return min(discount, fare_total), None


def _quote(trip: dict[str, Any], seat_ids: list[str], coupon_code: str | None, user_id: str | None) -> dict[str, Any]:
    layout = {s["id"]: s for s in _layout(trip["schedule"]["bus_type"])}
    prices = {sid: _seat_price(trip, layout[sid]) for sid in seat_ids}
    fare_total = sum(prices.values())
    discount, coupon_problem = _coupon_discount(coupon_code, trip, fare_total, len(seat_ids), user_id)
    gst = int(round((fare_total - discount) * GST_RATE)) if trip["type"]["ac"] else 0
    return {
        "seats": seat_ids,
        "seat_prices": prices,
        "fare_total": fare_total,
        "coupon": coupon_code.strip().upper() if coupon_code and not coupon_problem else None,
        "coupon_problem": coupon_problem,
        "discount": discount,
        "gst": gst,
        "total": fare_total - discount + gst,
    }


def _check_seats(trip: dict[str, Any], seat_ids: list[str], genders: list[str] | None, user_id: str | None, ignore_booking: str | None = None) -> dict[str, str]:
    """Problems with these seats on this trip (empty when they can be booked)."""
    layout = {s["id"]: s for s in _layout(trip["schedule"]["bus_type"])}
    sold = {k: v for k, v in _occupancy(trip).items() if not ignore_booking or v["booking_id"] != ignore_booking}
    problems: dict[str, str] = {}
    if not seat_ids:
        return {"seats": "choose at least one seat"}
    if len(seat_ids) > MAX_SEATS:
        return {"seats": f"at most {MAX_SEATS} seats per booking"}
    if len(set(seat_ids)) != len(seat_ids):
        return {"seats": "the same seat twice"}
    unknown = [s for s in seat_ids if s not in layout]
    if unknown:
        return {"seats": f"no seat {', '.join(unknown)} on this bus"}
    taken = [s for s in seat_ids if s in sold]
    if taken:
        problems["seats"] = f"{', '.join(taken)} already booked"
    if genders:
        for sid, gender in zip(seat_ids, genders):
            partner = layout[sid]["partner"]
            if partner and partner in sold and sold[partner]["gender"] == "female" and gender != "female":
                problems["seats"] = f"{sid} is next to a woman traveller and can only be booked for a woman"
    return problems


def get_fare_quote(*, trip_id: str, seats: str, coupon_code: str | None = None) -> dict[str, Any]:
    trip = _trip(trip_id)
    if trip is None:
        return _error(f"not_found: no trip {trip_id}", trip_id="unknown trip")
    seat_ids = _seat_ids(seats)
    problems = _check_seats(trip, seat_ids, None, None)
    if problems:
        return _error(problems["seats"], **problems)
    return {"trip": _card(trip), "quote": _quote(trip, seat_ids, coupon_code, _optional_user())}


def check_coupon(*, code: str, trip_id: str | None = None, seats: str | None = None) -> dict[str, Any]:
    coupon = db.get("coupons", code.strip().upper())
    if coupon is None:
        return {"code": code.upper(), "exists": False, "message": f"{code.upper()} isn't a Wayline offer code"}
    out: dict[str, Any] = {"code": coupon["code"], "exists": True, "title": coupon["title"], "description": coupon["description"]}
    if trip_id:
        trip = _trip(trip_id)
        if trip is None:
            return _error(f"not_found: no trip {trip_id}", trip_id="unknown trip")
        seat_ids = _seat_ids(seats) or [next(s["id"] for s in _seat_map(trip, None) if s["status"] == "available")]
        quote = _quote(trip, seat_ids, coupon["code"], _optional_user())
        out.update({"applies": quote["coupon_problem"] is None, "saving": quote["discount"], "reason": quote["coupon_problem"], "quote": quote})
    return out


# ---------------------------------------------------------------- the traveller


def _profile(user_id: str) -> dict[str, Any]:
    profile = db.get("travellers", user_id)
    assert profile is not None
    return profile


def _ensure_traveller(user_id: str) -> None:
    """A new user starts as the demo traveller with two saved travellers and a booking history."""
    if db.get("travellers", user_id) is not None:
        return
    with db.transaction():
        if db.get("travellers", user_id) is not None:
            return
        saved = [{"id": f"TRV-{i + 1}", **t} for i, t in enumerate(SAMPLE_TRAVELLERS)]
        db.put("travellers", {"id": user_id, **DEFAULT_TRAVELLER, "saved": saved, "created_at": _now().isoformat()})
        people = [{"name": DEFAULT_TRAVELLER["name"], "age": DEFAULT_TRAVELLER["age"], "gender": DEFAULT_TRAVELLER["gender"]}, *SAMPLE_TRAVELLERS]
        for sample in SAMPLE_BOOKINGS:
            _seed_booking(user_id, sample, people)


def _seed_booking(user_id: str, sample: dict[str, Any], people: list[dict[str, Any]]) -> None:
    day = _today() + timedelta(days=sample["days"])
    schedules = [s for s in db.rows("schedules") if s["route"] == sample["route"]]
    schedule = next((s for s in schedules if s["bus_type"] == sample["type"]), schedules[0])
    trip = _trip(f"{schedule['id']}-{day:%Y%m%d}")
    assert trip is not None
    if sample["outcome"] == "upcoming" and not _bookable(trip):
        trip = _trip(f"{schedule['id']}-{day + timedelta(days=1):%Y%m%d}")
        assert trip is not None
    sold = _occupancy(trip)
    layout = _layout(trip["schedule"]["bus_type"])
    free = [s["id"] for s in layout if s["id"] not in sold and not (s["partner"] in sold and sold[s["partner"]]["gender"] == "female")]
    seats = _pick_seats(free, {s["id"]: s for s in layout}, len(sample["pax"]), "together")
    boarding, dropping = _points(trip)
    booked_at = (trip["departs"] - timedelta(days=9)) if sample["days"] < 0 else (_now() - timedelta(days=4))
    booking = _new_booking(
        user_id, trip, seats, [people[i] for i in sample["pax"]], boarding[0]["id"], dropping[-1]["id"],
        DEFAULT_TRAVELLER["email"], DEFAULT_TRAVELLER["phone"], "upi", None, booked_at,
    )
    if sample["outcome"] == "cancelled":
        cancelled_at = trip["departs"] - timedelta(days=4)
        for p in booking["passengers"]:
            charge = int(round(p["paid"] * 10 / 100))
            p.update({"status": "cancelled", "cancelled_at": cancelled_at.isoformat(), "charge": charge, "refund": p["paid"] - charge})
        booking["cancel_reason"] = "change_of_plans"
    if sample.get("rating"):
        review_id = _next_id("reviews", "REV", 5000, width=4)
        db.put("reviews", {"id": review_id, "operator_id": trip["operator"]["id"], "route": trip["schedule"]["route"],
                           "author": "Priya N.", "user_id": user_id, "rating": sample["rating"],
                           "comment": "Smooth overnight ride, clean berths and the bus left on time.",
                           "created_at": (trip["arrives"] + timedelta(days=1)).isoformat()})
        booking["rating"] = {"stars": sample["rating"], "review_id": review_id}
    db.put("bookings", booking)


def _next_id(kind: str, prefix: str, start: int, width: int = 0) -> str:
    numbers = [int(m.group(1)) for r in db.rows(kind) if (m := re.fullmatch(rf"{prefix}-(\d+)", r["id"]))]
    number = (max(numbers) + 1) if numbers and max(numbers) >= start else start
    return f"{prefix}-{number:0{width}d}" if width else f"{prefix}-{number}"


def _new_booking(
    user_id: str, trip: dict[str, Any], seats: list[str], passengers: list[dict[str, Any]], boarding: str, dropping: str,
    email: str, phone: str, payment_method: str, coupon_code: str | None, booked_at: datetime,
) -> dict[str, Any]:
    quote = _quote(trip, seats, coupon_code, user_id)
    booking_id = _next_id("bookings", "BKG", 30001)
    # Spread the discount and GST over the seats so a partial cancellation refunds the right share.
    paid_left, lines = quote["total"], []
    for i, (seat, person) in enumerate(zip(seats, passengers)):
        share = paid_left if i == len(seats) - 1 else int(round(quote["total"] * quote["seat_prices"][seat] / quote["fare_total"]))
        paid_left -= share
        lines.append({"seat": seat, "name": person["name"].strip(), "age": int(person["age"]), "gender": person["gender"],
                      "fare": quote["seat_prices"][seat], "paid": share, "status": "confirmed"})
    return {
        "id": booking_id,
        "pnr": "WL" + hashlib.sha256(f"{booking_id}:{user_id}".encode()).hexdigest()[:6].upper(),
        "user_id": user_id,
        "trip_id": trip["id"],
        "boarding_point": boarding,
        "dropping_point": dropping,
        "passengers": lines,
        "contact_email": email,
        "contact_phone": phone,
        "payment_method": payment_method,
        "coupon": quote["coupon"],
        "fare_total": quote["fare_total"],
        "discount": quote["discount"],
        "gst": quote["gst"],
        "total": quote["total"],
        "extra_paid": 0,
        "booked_at": booked_at.isoformat(),
        "history": [{"at": booked_at.isoformat(), "event": "booked", "detail": f"{len(seats)} seat(s), ₹{quote['total']}"}],
    }


def get_my_context() -> dict[str, Any]:
    user_id = current_user()
    profile = _profile(user_id)
    views = [_booking_view(b) for b in _bookings(user_id)]
    upcoming = sorted((b for b in views if b["status"] == "upcoming"), key=lambda b: b["departs"])
    return {
        "traveller": {k: profile[k] for k in ("name", "email", "phone", "gender", "age")} | {"home_city": _city_name(profile["home_city"])},
        "saved_travellers": profile["saved"],
        "wallet_balance": profile["wallet_balance"],
        "payment_methods": [{"id": k, "label": v if k != "upi" else f"UPI ({profile['upi_id']})"} for k, v in PAYMENT_METHODS.items()],
        "upcoming_trips": len(upcoming),
        "next_trip": _brief(upcoming[0]) if upcoming else None,
        "total_bookings": len(views),
        "lifetime_spend": sum(b["amount_paid"] for b in views),
    }


def list_travellers() -> dict[str, Any]:
    profile = _profile(current_user())
    me = {"id": "me", "name": profile["name"], "age": profile["age"], "gender": profile["gender"]}
    return {"travellers": [me, *profile["saved"]]}


def add_traveller(*, name: str, age: int, gender: str) -> dict[str, Any]:
    user_id = current_user()
    fields: dict[str, str] = {}
    if not name or not name.strip() or len(name.strip()) > 60:
        fields["name"] = "required, up to 60 characters"
    if not isinstance(age, int) or not 1 <= age <= 110:
        fields["age"] = "between 1 and 110"
    if gender not in GENDERS:
        fields["gender"] = f"one of {', '.join(GENDERS)}"
    if fields:
        return _error("check the traveller's details", **fields)
    with db.transaction():
        profile = _profile(user_id)
        if len(profile["saved"]) >= MAX_TRAVELLERS:
            return _error(f"at most {MAX_TRAVELLERS} saved travellers")
        if any(t["name"].lower() == name.strip().lower() for t in profile["saved"]):
            return _error(f"{name.strip()} is already saved", name="already saved")
        numbers = [int(t["id"].split("-")[1]) for t in profile["saved"]]
        traveller = {"id": f"TRV-{max(numbers, default=0) + 1}", "name": name.strip(), "age": age, "gender": gender}
        profile["saved"].append(traveller)
        db.put("travellers", profile)
    return {"traveller": traveller, "travellers": profile["saved"]}


def remove_traveller(*, traveller_id: str) -> dict[str, Any]:
    user_id = current_user()
    with db.transaction():
        profile = _profile(user_id)
        keep = [t for t in profile["saved"] if t["id"] != traveller_id.upper()]
        if len(keep) == len(profile["saved"]):
            return _error(f"not_found: no saved traveller {traveller_id}", traveller_id="unknown traveller")
        profile["saved"] = keep
        db.put("travellers", profile)
    return {"removed": traveller_id.upper(), "travellers": keep}


# ---------------------------------------------------------------- booking


def book_tickets(
    *,
    trip_id: str,
    seats: str,
    boarding_point: str,
    dropping_point: str,
    passenger_1_name: str,
    passenger_1_age: int,
    passenger_1_gender: str,
    contact_email: str,
    contact_phone: str,
    passenger_2_name: str | None = None,
    passenger_2_age: int | None = None,
    passenger_2_gender: str | None = None,
    passenger_3_name: str | None = None,
    passenger_3_age: int | None = None,
    passenger_3_gender: str | None = None,
    passenger_4_name: str | None = None,
    passenger_4_age: int | None = None,
    passenger_4_gender: str | None = None,
    payment_method: str = "upi",
    coupon_code: str | None = None,
) -> dict[str, Any]:
    user_id = current_user()
    trip = _trip(trip_id)
    if trip is None:
        return _error(f"not_found: no trip {trip_id}", trip_id="unknown trip")
    if not _bookable(trip):
        return _error("booking for this bus has closed", trip_id="departed or too close to departure")
    seat_ids = _seat_ids(seats)
    raw = [
        (passenger_1_name, passenger_1_age, passenger_1_gender),
        (passenger_2_name, passenger_2_age, passenger_2_gender),
        (passenger_3_name, passenger_3_age, passenger_3_gender),
        (passenger_4_name, passenger_4_age, passenger_4_gender),
    ]
    fields: dict[str, str] = {}
    people = []
    for i, (name, age, gender) in enumerate(raw, start=1):
        if i > len(seat_ids):
            if name and str(name).strip():
                fields[f"passenger_{i}_name"] = f"only {len(seat_ids)} seat(s) chosen"
            continue
        if not name or not str(name).strip():
            fields[f"passenger_{i}_name"] = "required"
        try:
            age_n = int(age) if age is not None and str(age).strip() else None
        except (TypeError, ValueError):
            age_n = None
        if age_n is None or not 1 <= age_n <= 110:
            fields[f"passenger_{i}_age"] = "between 1 and 110"
        if gender not in GENDERS:
            fields[f"passenger_{i}_gender"] = f"one of {', '.join(GENDERS)}"
        people.append({"name": str(name or ""), "age": age_n or 0, "gender": gender})
    boarding, dropping = _points(trip)
    if boarding_point not in {p["id"] for p in boarding}:
        fields["boarding_point"] = f"one of {', '.join(p['id'] for p in boarding)}"
    if dropping_point not in {p["id"] for p in dropping}:
        fields["dropping_point"] = f"one of {', '.join(p['id'] for p in dropping)}"
    if not _EMAIL.fullmatch((contact_email or "").strip()):
        fields["contact_email"] = "not an email address"
    if not _PHONE.fullmatch((contact_phone or "").strip()):
        fields["contact_phone"] = "a 10-digit mobile number"
    if payment_method not in PAYMENT_METHODS:
        fields["payment_method"] = f"one of {', '.join(PAYMENT_METHODS)}"
    with db.transaction():
        fields.update(_check_seats(trip, seat_ids, [p["gender"] for p in people], user_id))
        if fields:
            return _error("check the booking details", **fields)
        quote = _quote(trip, seat_ids, coupon_code, user_id)
        if coupon_code and quote["coupon_problem"]:
            return _error(quote["coupon_problem"], coupon_code=quote["coupon_problem"])
        profile = _profile(user_id)
        if payment_method == "wallet":
            if profile["wallet_balance"] < quote["total"]:
                return _error(f"wallet balance ₹{profile['wallet_balance']} is less than ₹{quote['total']}", payment_method="not enough in wallet")
            profile["wallet_balance"] -= quote["total"]
            db.put("travellers", profile)
        booking = _new_booking(user_id, trip, seat_ids, people, boarding_point, dropping_point, contact_email.strip(),
                               contact_phone.strip(), payment_method, coupon_code, _now())
        db.put("bookings", booking)
    return {"booking": _booking_view(booking), "message": f"Booked {len(seat_ids)} seat(s). PNR {booking['pnr']}."}


def _bookings(user_id: str) -> list[dict[str, Any]]:
    return [b for b in db.rows("bookings") if b["user_id"] == user_id]


def _own_booking(booking_id: str) -> dict[str, Any] | None:
    user_id = current_user()
    key = (booking_id or "").strip().upper()
    found = db.get("bookings", key) or next((b for b in _bookings(user_id) if b["pnr"] == key), None)
    return found if found and found["user_id"] == user_id else None


def _cancel_pct(hours_left: float) -> int | None:
    for hours, pct in CANCELLATION_POLICY:
        if hours_left >= hours:
            return pct
    return None


def _policy_lines() -> list[dict[str, Any]]:
    lines, upper = [], None
    for hours, pct in CANCELLATION_POLICY:
        when = f"{hours}+ hours before departure" if upper is None else f"{hours}–{upper} hours before departure"
        lines.append({"window": when, "charge_pct": pct})
        upper = hours
    lines.append({"window": f"less than {upper} hours before departure", "charge_pct": None, "note": "cannot be cancelled"})
    return lines


def _booking_view(b: dict[str, Any]) -> dict[str, Any]:
    trip = _trip(b["trip_id"])
    assert trip is not None
    boarding, dropping = _points(trip)
    bp = next(p for p in boarding if p["id"] == b["boarding_point"])
    dp = next(p for p in dropping if p["id"] == b["dropping_point"])
    now = _now()
    active = [p for p in b["passengers"] if p["status"] == "confirmed"]
    departs = datetime.fromisoformat(bp["time"])
    hours_left = (departs - now).total_seconds() / 3600
    if not active:
        status = "cancelled"
    elif trip["arrives"] <= now:
        status = "completed"
    elif departs <= now:
        status = "in_transit"
    else:
        status = "upcoming"
    pct = _cancel_pct(hours_left) if status == "upcoming" else None
    refunded = sum(p.get("refund", 0) for p in b["passengers"])
    next_tier = None
    if pct is not None:
        # The current tier is the first whose threshold has not passed; it ends at departure − threshold.
        tier = next(i for i, (hours, _) in enumerate(CANCELLATION_POLICY) if hours_left >= hours)
        after = CANCELLATION_POLICY[tier + 1][1] if tier + 1 < len(CANCELLATION_POLICY) else None
        next_tier = {"from": (departs - timedelta(hours=CANCELLATION_POLICY[tier][0])).isoformat(), "charge_pct": after}
    return {
        "id": b["id"],
        "pnr": b["pnr"],
        "status": status,
        "trip": _card(trip),
        "trip_id": trip["id"],
        "journey_date": trip["date"].isoformat(),
        "route": f"{_city_name(trip['schedule']['from'])} → {_city_name(trip['schedule']['to'])}",
        "departs": bp["time"],
        "arrives": dp["time"],
        "boarding_point": bp,
        "dropping_point": dp,
        "passengers": b["passengers"],
        "seats": [p["seat"] for p in active],
        "contact_email": b["contact_email"],
        "contact_phone": b["contact_phone"],
        "payment_method": b["payment_method"],
        "payment_label": PAYMENT_METHODS[b["payment_method"]],
        "coupon": b["coupon"],
        "fare_total": b["fare_total"],
        "discount": b["discount"],
        "gst": b["gst"],
        "total": b["total"],
        "extra_paid": b.get("extra_paid", 0),
        "refunded": refunded,
        "amount_paid": b["total"] + b.get("extra_paid", 0) - refunded,
        "booked_at": b["booked_at"],
        "rescheduled_from": b.get("rescheduled_from"),
        "rating": b.get("rating"),
        "history": b.get("history", []),
        "can_cancel": pct is not None,
        "cancellation_charge_pct": pct,
        "charges_rise_at": next_tier,
        "can_reschedule": status == "upcoming" and hours_left >= RESCHEDULE_UNTIL_HOURS and not b.get("rescheduled_from"),
        "can_change_points": status == "upcoming" and hours_left >= CHANGE_POINTS_UNTIL_HOURS,
        "can_rate": status == "completed" and not b.get("rating"),
        "boarding_points": boarding,
        "dropping_points": dropping,
    }


def _brief(v: dict[str, Any]) -> dict[str, Any]:
    return {k: v[k] for k in ("id", "pnr", "status", "route", "journey_date", "departs", "seats", "amount_paid")} | {
        "operator": v["trip"]["operator"], "boarding_point": v["boarding_point"]["name"]}


def list_bookings(
    *,
    status: str | None = None,
    journey_from: str | None = None,
    journey_to: str | None = None,
    city: str | None = None,
    operator_id: str | None = None,
    sort_by: str = "journey_date",
    sort_order: str = "desc",
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    views = [_booking_view(b) for b in _bookings(current_user())]
    if status:
        views = [v for v in views if v["status"] == status]
    if journey_from:
        views = [v for v in views if v["journey_date"] >= journey_from[:10]]
    if journey_to:
        views = [v for v in views if v["journey_date"] <= journey_to[:10]]
    if city:
        code = _city(city)
        views = [v for v in views if code in (v["trip"]["from"], v["trip"]["to"])]
    if operator_id:
        views = [v for v in views if v["trip"]["operator_id"] == operator_id.upper()]
    key = {"booked_at": lambda v: v["booked_at"], "amount": lambda v: v["amount_paid"]}.get(sort_by, lambda v: v["departs"])
    views.sort(key=key, reverse=sort_order != "asc")
    page = views[offset: offset + max(1, min(limit, 50))]
    return {"bookings": [{**_brief(v), "can_cancel": v["can_cancel"], "can_rate": v["can_rate"], "passengers": len(v["seats"]) or len(v["passengers"]),
                          "bus_type": v["trip"]["bus_type_label"], "arrives": v["arrives"], "total": v["total"], "refunded": v["refunded"]} for v in page],
            "total": len(views)}


def get_booking(*, booking_id: str) -> dict[str, Any]:
    b = _own_booking(booking_id)
    if b is None:
        return _error(f"not_found: no booking {booking_id} — ids look like BKG-30004 or a PNR (list_bookings)", booking_id="unknown booking")
    return {"booking": _booking_view(b)}


def get_cancellation_quote(*, booking_id: str, seats: str | None = None) -> dict[str, Any]:
    b = _own_booking(booking_id)
    if b is None:
        return _error(f"not_found: no booking {booking_id}", booking_id="unknown booking")
    view = _booking_view(b)
    chosen = _seat_ids(seats) or view["seats"]
    lines = [p for p in b["passengers"] if p["seat"] in chosen and p["status"] == "confirmed"]
    if not lines:
        return _error("none of those seats is active on this booking", seats="not on this booking")
    pct = view["cancellation_charge_pct"]
    if pct is None:
        return {"booking_id": b["id"], "can_cancel": False, "reason": _why_not_cancellable(view), "policy": _policy_lines()}
    charge = sum(int(round(p["paid"] * pct / 100)) for p in lines)
    paid = sum(p["paid"] for p in lines)
    return {"booking_id": b["id"], "can_cancel": True, "seats": [p["seat"] for p in lines], "charge_pct": pct,
            "paid_for_seats": paid, "cancellation_charge": charge, "refund": paid - charge,
            "refund_to": view["payment_label"], "charges_rise_at": view["charges_rise_at"], "policy": _policy_lines()}


def _why_not_cancellable(view: dict[str, Any]) -> str:
    if view["status"] == "cancelled":
        return "already cancelled"
    if view["status"] in ("completed", "in_transit"):
        return "the bus has already left"
    return f"cancellations close {CANCELLATION_POLICY[-1][0]} hours before departure"


def cancel_booking(*, booking_id: str, seats: str | None = None, reason: str = "change_of_plans") -> dict[str, Any]:
    if reason not in CANCEL_REASONS:
        return _error(f"reason must be one of {', '.join(CANCEL_REASONS)}", reason="unknown reason")
    with db.transaction():
        quote = get_cancellation_quote(booking_id=booking_id, seats=seats)
        if "error" in quote:
            return quote
        if not quote["can_cancel"]:
            return _error(f"can't cancel: {quote['reason']}", booking_id=quote["reason"])
        b = _own_booking(booking_id)
        assert b is not None
        now = _now().isoformat()
        for p in b["passengers"]:
            if p["seat"] in quote["seats"] and p["status"] == "confirmed":
                charge = int(round(p["paid"] * quote["charge_pct"] / 100))
                p.update({"status": "cancelled", "cancelled_at": now, "charge": charge, "refund": p["paid"] - charge})
        b["cancel_reason"] = reason
        b.setdefault("history", []).append({"at": now, "event": "cancelled", "detail": f"{', '.join(quote['seats'])} · refund ₹{quote['refund']}"})
        if b["payment_method"] == "wallet":
            profile = _profile(b["user_id"])
            profile["wallet_balance"] += quote["refund"]
            db.put("travellers", profile)
        db.put("bookings", b)
    return {"booking": _booking_view(b), "refund": quote["refund"], "cancellation_charge": quote["cancellation_charge"],
            "message": f"Cancelled {', '.join(quote['seats'])}. ₹{quote['refund']} goes back to {PAYMENT_METHODS[b['payment_method']]} in 3–5 working days."}


def change_boarding_point(*, booking_id: str, boarding_point: str | None = None, dropping_point: str | None = None) -> dict[str, Any]:
    if not boarding_point and not dropping_point:
        return _error("give a new boarding point, dropping point or both", boarding_point="required")
    with db.transaction():
        b = _own_booking(booking_id)
        if b is None:
            return _error(f"not_found: no booking {booking_id}", booking_id="unknown booking")
        view = _booking_view(b)
        if not view["can_change_points"]:
            return _error(f"boarding and dropping points can be changed until {CHANGE_POINTS_UNTIL_HOURS} hours before departure", booking_id="too late")
        fields = {}
        if boarding_point and boarding_point not in {p["id"] for p in view["boarding_points"]}:
            fields["boarding_point"] = f"one of {', '.join(p['id'] for p in view['boarding_points'])}"
        if dropping_point and dropping_point not in {p["id"] for p in view["dropping_points"]}:
            fields["dropping_point"] = f"one of {', '.join(p['id'] for p in view['dropping_points'])}"
        if fields:
            return _error("unknown point for this bus", **fields)
        if boarding_point:
            b["boarding_point"] = boarding_point
        if dropping_point:
            b["dropping_point"] = dropping_point
        b.setdefault("history", []).append({"at": _now().isoformat(), "event": "points_changed", "detail": f"{b['boarding_point']} → {b['dropping_point']}"})
        db.put("bookings", b)
    view = _booking_view(b)
    return {"booking": view, "message": f"Boarding at {view['boarding_point']['name']} ({view['boarding_point']['time'][11:16]}), dropping at {view['dropping_point']['name']}."}


def reschedule_booking(*, booking_id: str, new_date: str, seats: str | None = None) -> dict[str, Any]:
    day = _parse_date(new_date, "new_date")
    if isinstance(day, dict):
        return day
    user_id = current_user()
    with db.transaction():
        b = _own_booking(booking_id)
        if b is None:
            return _error(f"not_found: no booking {booking_id}", booking_id="unknown booking")
        view = _booking_view(b)
        if not view["can_reschedule"]:
            reason = "a booking can be rescheduled once" if b.get("rescheduled_from") else f"rescheduling closes {RESCHEDULE_UNTIL_HOURS} hours before departure"
            return _error(f"can't reschedule: {reason}", booking_id=reason)
        old = _trip(b["trip_id"])
        assert old is not None
        new = _trip(f"{old['schedule']['id']}-{day:%Y%m%d}")
        if new is None or new["id"] == old["id"]:
            return _error("pick a different date", new_date="same date")
        if not _bookable(new):
            return _error("that bus can't be booked for that date", new_date="departed or outside the booking window")
        active = [p for p in b["passengers"] if p["status"] == "confirmed"]
        seat_ids = _seat_ids(seats) or [p["seat"] for p in active]
        if len(seat_ids) != len(active):
            return _error(f"choose {len(active)} seat(s), one per traveller", seats="wrong number of seats")
        problems = _check_seats(new, seat_ids, [p["gender"] for p in active], user_id)
        if problems:
            free = [s["id"] for s in _seat_map(new, None) if s["status"] == "available"][:8]
            return _error(f"{problems['seats']} on {day:%d %b} — free seats include {', '.join(free)}", **problems)
        layout = {s["id"]: s for s in _layout(new["schedule"]["bus_type"])}
        new_fare = sum(_seat_price(new, layout[s]) for s in seat_ids)
        difference = max(0, new_fare - sum(p["fare"] for p in active))
        extra = RESCHEDULE_FEE + difference
        profile = _profile(user_id)
        if b["payment_method"] == "wallet":
            if profile["wallet_balance"] < extra:
                return _error(f"wallet balance ₹{profile['wallet_balance']} is less than ₹{extra}", booking_id="not enough in wallet")
            profile["wallet_balance"] -= extra
            db.put("travellers", profile)
        for p, seat in zip(active, seat_ids):
            p["seat"] = seat
        b["passengers"] = active + [p for p in b["passengers"] if p["status"] != "confirmed"]
        b["rescheduled_from"] = old["id"]
        b["trip_id"] = new["id"]
        b["extra_paid"] = b.get("extra_paid", 0) + extra
        b.setdefault("history", []).append({"at": _now().isoformat(), "event": "rescheduled",
                                            "detail": f"{old['date']:%d %b} → {day:%d %b}, ₹{extra} (fee ₹{RESCHEDULE_FEE} + fare difference ₹{difference})"})
        db.put("bookings", b)
    return {"booking": _booking_view(b), "charged": extra, "fee": RESCHEDULE_FEE, "fare_difference": difference,
            "message": f"Moved to {day:%a %d %b}, seats {', '.join(seat_ids)}. Charged ₹{extra}."}


def rate_trip(*, booking_id: str, rating: int, comment: str | None = None) -> dict[str, Any]:
    if not isinstance(rating, int) or not 1 <= rating <= 5:
        return _error("rating is 1 to 5 stars", rating="1–5")
    if comment and len(comment) > 1000:
        return _error("keep the review under 1000 characters", comment="too long")
    with db.transaction():
        b = _own_booking(booking_id)
        if b is None:
            return _error(f"not_found: no booking {booking_id}", booking_id="unknown booking")
        view = _booking_view(b)
        if not view["can_rate"]:
            reason = "already rated" if b.get("rating") else "you can rate a trip after it is completed"
            return _error(f"can't rate: {reason}", booking_id=reason)
        profile = _profile(b["user_id"])
        first, *rest = profile["name"].split()
        review = {"id": _next_id("reviews", "REV", 5000, width=4), "operator_id": view["trip"]["operator_id"],
                  "route": f"{view['trip']['from']}-{view['trip']['to']}", "author": f"{first} {rest[-1][0]}." if rest else first,
                  "user_id": b["user_id"], "rating": rating, "comment": (comment or "").strip(), "created_at": _now().isoformat()}
        db.put("reviews", review)
        b["rating"] = {"stars": rating, "review_id": review["id"]}
        db.put("bookings", b)
    return {"booking": _booking_view(b), "review": _review_view(review)}


# ---------------------------------------------------------------- statistics and cross-entity


def aggregate_bookings(*, metric: str = "count", group_by: str = "status") -> dict[str, Any]:
    views = [_booking_view(b) for b in _bookings(current_user())]
    keyf = {
        "status": lambda v: v["status"],
        "month": lambda v: v["journey_date"][:7],
        "route": lambda v: v["route"],
        "operator": lambda v: v["trip"]["operator"],
        "bus_type": lambda v: v["trip"]["bus_type_label"],
    }.get(group_by)
    if keyf is None:
        return _error("group_by must be status, month, route, operator or bus_type", group_by="unknown")
    groups: dict[str, list[dict[str, Any]]] = {}
    for v in views:
        groups.setdefault(keyf(v), []).append(v)
    value = {
        "count": len,
        "sum_paid": lambda vs: sum(v["amount_paid"] for v in vs),
        "seats": lambda vs: sum(len(v["passengers"]) for v in vs),
        "avg_paid": lambda vs: int(sum(v["amount_paid"] for v in vs) / len(vs)),
    }.get(metric)
    if value is None:
        return _error("metric must be count, sum_paid, seats or avg_paid", metric="unknown")
    rows_ = [{"group": k, "value": value(vs)} for k, vs in groups.items()]
    rows_.sort(key=lambda r: r["group"] if group_by == "month" else -r["value"])
    return {"metric": metric, "group_by": group_by, "rows": rows_}


def get_travel_spend_over_time(*, months: int = 6) -> dict[str, Any]:
    views = [_booking_view(b) for b in _bookings(current_user())]
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
                    "trips_taken": sum(1 for v in views if v["journey_date"][:7] == key and v["status"] == "completed")})
    return {"months": out, "currency": "INR"}


def list_attention_items() -> dict[str, Any]:
    views = [_booking_view(b) for b in _bookings(current_user())]
    now = _now()
    items = []
    for v in views:
        departs = datetime.fromisoformat(v["departs"])
        if v["status"] == "upcoming" and departs - now <= timedelta(hours=48):
            items.append({"kind": "trip_soon", "booking_id": v["id"],
                          "text": f"{v['route']} leaves {departs:%a %d %b at %H:%M} from {v['boarding_point']['name']} ({v['boarding_point']['landmark']})."})
        if v["status"] == "upcoming" and v["charges_rise_at"]:
            rise = v["charges_rise_at"]
            items.append({"kind": "cancellation_charge_rises", "booking_id": v["id"],
                          "text": f"Cancelling {v['pnr']} costs {v['cancellation_charge_pct']}% now; from {rise['from'][:16].replace('T', ' ')} it is "
                                  + (f"{rise['charge_pct']}%." if rise["charge_pct"] else "no longer possible.")})
        if v["can_rate"]:
            items.append({"kind": "rate_trip", "booking_id": v["id"], "text": f"How was {v['trip']['operator']} on {v['route']} ({v['journey_date']})? Rate the trip."})
    return {"items": items, "total": len(items)}


def get_overview() -> dict[str, Any]:
    ctx = get_my_context()
    bookings = list_bookings(limit=5)["bookings"]
    return {"traveller": ctx["traveller"]["name"], "next_trip": ctx["next_trip"], "upcoming_trips": ctx["upcoming_trips"],
            "recent_bookings": bookings, "wallet_balance": ctx["wallet_balance"], "attention": list_attention_items()["items"],
            "offers": [o["code"] for o in list_offers()["offers"]]}


def search_all(*, query: str) -> dict[str, Any]:
    q = query.strip().lower()
    hits: list[dict[str, Any]] = []
    for code, city in CITIES.items():
        if q in city["name"].lower() or q == code.lower() or any(q in p[0].lower() for p in city["points"]):
            hits.append({"type": "city", "id": code, "title": city["name"]})
    for route in ROUTES:
        title = f"{_city_name(route['from'])} → {_city_name(route['to'])}"
        if q in title.lower() or q == route["id"].lower():
            hits.append({"type": "route", "id": route["id"], "title": title})
    for op in OPERATORS:
        if q in op["name"].lower():
            hits.append({"type": "operator", "id": op["id"], "title": op["name"]})
    for c in db.rows("coupons"):
        if q in c["code"].lower() or q in c["title"].lower():
            hits.append({"type": "offer", "id": c["code"], "title": c["title"]})
    if _user.get():
        for v in [_booking_view(b) for b in _bookings(current_user())]:
            text = " ".join([v["id"], v["pnr"], v["route"], v["trip"]["operator"], *(p["name"] for p in v["passengers"])]).lower()
            if q in text:
                hits.append({"type": "booking", "id": v["id"], "title": f"{v['route']} · {v['journey_date']} · {v['pnr']}"})
    return {"hits": hits[:25], "total": len(hits)}


def describe_data() -> dict[str, Any]:
    return {
        "currency": "INR (whole rupees)",
        "timezone": "IST (UTC+05:30)",
        "cities": {code: c["name"] for code, c in CITIES.items()},
        "bus_types": {k: v["label"] for k, v in BUS_TYPES.items()},
        "amenities": AMENITIES,
        "departure_windows": {k: v[0] for k, v in DEPARTURE_WINDOWS.items()},
        "sorts": list(SORTS),
        "booking_statuses": list(BOOKING_STATUSES),
        "max_seats_per_booking": MAX_SEATS,
        "booking_window_days": BOOKING_WINDOW_DAYS,
        "booking_closes_minutes_before": BOOKING_CLOSES_MIN,
        "seat_rules": "Sleepers are 2+1 berths on a lower and an upper deck (upper berths ₹50 cheaper); seaters are 2+2. "
                      "A seat whose neighbour is a woman traveller can only be booked for a woman.",
        "fares": f"Friday and Sunday departures cost {int(WEEKEND_SURCHARGE * 100)}% more. GST {int(GST_RATE * 100)}% on AC buses only.",
        "payment_methods": PAYMENT_METHODS,
        "cancellation_policy": _policy_lines(),
        "cancel_reasons": list(CANCEL_REASONS),
        "reschedule": f"Once per booking, same bus on another date, until {RESCHEDULE_UNTIL_HOURS} h before departure; ₹{RESCHEDULE_FEE} fee plus any fare difference.",
        "change_points": f"Boarding and dropping points can be changed until {CHANGE_POINTS_UNTIL_HOURS} h before departure.",
        "genders": list(GENDERS),
    }
