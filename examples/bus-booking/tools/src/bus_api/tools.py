"""Every Relay tool, defined once: function, description, JSON schema, classification.

``GET /tools`` and ``POST /tools/{name}`` are both generated from ``TOOL_SPECS``. Writes are
``side_effecting``: the assistant can only propose them, and they run after the traveller approves
(or submits a form bound to them). The inventory behind this catalog is in ``../relay-tools.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from bus_api import logic
from bus_api.seeds import AMENITIES, BUS_TYPES, CITIES, OPERATORS


@dataclass(frozen=True)
class ToolSpec:
    fn: Callable[..., dict[str, Any]]
    description: str
    properties: dict[str, Any] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    classification: str = "read_only"
    # Needs a signed-in traveller (X-Relay-User); the service answers 401 without one.
    per_user: bool = True

    @property
    def input_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {"type": "object", "properties": self.properties}
        if self.required:
            schema["required"] = list(self.required)
        return schema


SE = "side_effecting"
_CITY_LIST = ", ".join(c + " " + v["name"] for c, v in CITIES.items())
CITY = {"type": "string", "description": f"City name or code: {_CITY_LIST}"}
TRIP_ID = {"type": "string", "minLength": 1, "title": "Bus", "description": "Trip id like SCH-1042-20261120 (a bus on a date) — find it with search_trips"}
BOOKING_ID = {"type": "string", "minLength": 1, "title": "Booking", "description": "Booking id like BKG-30004, or its PNR — find it with list_bookings"}
SEATS = {"type": "string", "minLength": 1, "title": "Seats", "description": "Seat ids separated by commas, e.g. 'L4, L5' (sleeper: L lower / U upper berths; seater: S1–S40)"}
DATE = {"type": "string", "format": "date"}
SORT_ORDER = {"type": "string", "enum": ["asc", "desc"]}
OPERATOR_ID = {"type": "string", "enum": [o["id"] for o in OPERATORS], "description": ", ".join(f"{o['id']} {o['name']}" for o in OPERATORS)}
GENDER = {"type": "string", "enum": list(logic.GENDERS)}


def _passenger(n: int) -> dict[str, Any]:
    note = " (for the second seat, if any)" if n == 2 else f" (seat {n}, if any)" if n > 2 else " (first seat — usually the traveller themselves)"
    return {
        f"passenger_{n}_name": {"type": "string", "title": f"Passenger {n} name", "maxLength": 60, "description": f"Full name as on ID{note}"},
        f"passenger_{n}_age": {"type": "integer", "minimum": 1, "maximum": 110, "title": f"Passenger {n} age"},
        f"passenger_{n}_gender": {**GENDER, "title": f"Passenger {n} gender"},
    }


TOOL_SPECS: dict[str, ToolSpec] = {
    # ------------------------------------------------------------ search and trips (reads)
    "search_trips": ToolSpec(
        logic.search_trips,
        "Buses between two cities on a date (default today; accepts 'tomorrow'). Filters: ac, sleeper, bus_type, "
        "departure_window (early_morning <6am, morning 6–12, afternoon 12–6pm, night after 6pm), operator, max_fare (₹), "
        "min_rating, amenity, min_seats; sort_by departure|fare|rating|duration|seats_left|arrival. Returns compact trips "
        "(trip_id, operator, type, times, duration, lowest fare, seats left, rating) and `total`. To show results on the "
        "site's own search page prefer the SEARCH_BUSES screen action.",
        {
            "from_city": CITY,
            "to_city": CITY,
            "date": {**DATE, "description": "Journey date YYYY-MM-DD, or 'today' / 'tomorrow'"},
            "ac": {"type": "boolean"},
            "sleeper": {"type": "boolean"},
            "bus_type": {"type": "string", "enum": list(BUS_TYPES)},
            "departure_window": {"type": "string", "enum": list(logic.DEPARTURE_WINDOWS)},
            "operator_id": OPERATOR_ID,
            "max_fare": {"type": "integer", "minimum": 0, "description": "Rupees"},
            "min_rating": {"type": "number", "minimum": 0, "description": "0–5 stars"},
            "amenity": {"type": "string", "enum": list(AMENITIES)},
            "min_seats": {"type": "integer", "minimum": 1},
            "sort_by": {"type": "string", "enum": list(logic.SORTS)},
            "sort_order": SORT_ORDER,
            "limit": {"type": "integer", "minimum": 1, "description": "Default 30"},
        },
        ("from_city", "to_city"),
        per_user=False,
    ),
    "get_trip": ToolSpec(
        logic.get_trip,
        "One bus on a date: operator, type, times, amenities, the full seat map (each seat's deck, window, price, "
        "status available|booked|booked_female|yours and women_only), boarding and dropping points with times, "
        "cancellation policy, GST and the latest operator reviews.",
        {"trip_id": TRIP_ID},
        ("trip_id",),
        per_user=False,
    ),
    "find_seats": ToolSpec(
        logic.find_seats,
        "Suggests free seats on a bus: count (1–4) and preference any|window|aisle|lower|upper|together (side-by-side "
        "pairs). Seats next to a woman are suggested only when travellers_gender is female. Returns seat ids and prices.",
        {
            "trip_id": TRIP_ID,
            "count": {"type": "integer", "minimum": 1, "maximum": logic.MAX_SEATS},
            "preference": {"type": "string", "enum": ["any", "window", "aisle", "lower", "upper", "together"]},
            "travellers_gender": {"type": "string", "enum": ["female", "mixed"], "description": "female when every traveller is a woman"},
        },
        ("trip_id",),
        per_user=False,
    ),
    "compare_trips": ToolSpec(
        logic.compare_trips,
        "Two to four buses side by side (operator, type, times, duration, fare, seats left, rating, amenities) — for a comparison surface.",
        {"trip_ids": {"type": "array", "items": {"type": "string"}, "description": "2–4 trip ids"}},
        ("trip_ids",),
        per_user=False,
    ),
    "get_fare_calendar": ToolSpec(
        logic.get_fare_calendar,
        "Cheapest fare, number of buses and seats left per day on a route for `days` days (default 14) from start_date "
        "— for 'which day is cheapest?' and a fare chart. Optional bus_type.",
        {"from_city": CITY, "to_city": CITY, "start_date": DATE, "days": {"type": "integer", "minimum": 1, "maximum": 31},
         "bus_type": {"type": "string", "enum": list(BUS_TYPES)}},
        ("from_city", "to_city"),
        per_user=False,
    ),
    "get_fare_quote": ToolSpec(
        logic.get_fare_quote,
        "Price for chosen seats on a bus: seat prices, fare, coupon discount (or why the coupon doesn't apply), 5% GST "
        "on AC buses, total. Use before proposing a booking.",
        {"trip_id": TRIP_ID, "seats": SEATS, "coupon_code": {"type": "string"}},
        ("trip_id", "seats"),
        per_user=False,
    ),
    "list_cities": ToolSpec(logic.list_cities, "Every city Wayline serves with its boarding points and destinations.", per_user=False),
    "list_routes": ToolSpec(
        logic.list_routes,
        "Routes (optionally from one city) with distance, typical duration, buses per day, lowest fare and operators.",
        {"from_city": CITY},
        per_user=False,
    ),
    "list_operators": ToolSpec(logic.list_operators, "Bus operators with rating, review count, buses per day, routes and bus types.", per_user=False),
    "get_operator": ToolSpec(
        logic.get_operator, "One operator with rating breakdown and recent reviews.", {"operator_id": OPERATOR_ID}, ("operator_id",), per_user=False
    ),
    "get_top_operators": ToolSpec(
        logic.get_top_operators,
        "Operators ranked by rating, buses_per_day or review_count, optionally only on one route (like BLR-HYD).",
        {"rank_by": {"type": "string", "enum": ["rating", "buses_per_day", "review_count"]},
         "route": {"type": "string", "description": "Route id FROM-TO with city codes, e.g. BLR-HYD"},
         "limit": {"type": "integer", "minimum": 1}},
        per_user=False,
    ),
    "list_reviews": ToolSpec(
        logic.list_reviews,
        "Operator reviews, newest first: filter by operator, min_rating / max_rating (1–5), or mine=true for the traveller's own.",
        {"operator_id": OPERATOR_ID, "min_rating": {"type": "integer", "minimum": 1}, "max_rating": {"type": "integer", "minimum": 1},
         "mine": {"type": "boolean"}, "limit": {"type": "integer", "minimum": 1}},
        per_user=False,
    ),
    "list_offers": ToolSpec(logic.list_offers, "Offer codes with what they give and their conditions.", per_user=False),
    "check_coupon": ToolSpec(
        logic.check_coupon,
        "Checks an offer code without booking: whether it exists, and — with a trip (and seats) — whether it applies and how much it saves.",
        {"code": {"type": "string", "minLength": 1}, "trip_id": TRIP_ID, "seats": SEATS},
        ("code",),
        per_user=False,
    ),
    # ------------------------------------------------------------ the traveller
    "get_my_context": ToolSpec(
        logic.get_my_context,
        "Who the traveller is: name, email, phone, gender, age, home city, saved co-travellers, wallet balance, payment "
        "methods, next trip and lifetime spend. Use it to prefill bookings.",
    ),
    "list_travellers": ToolSpec(logic.list_travellers, "The traveller ('me') and their saved co-travellers with age and gender."),
    "add_traveller": ToolSpec(
        logic.add_traveller,
        "Saves a co-traveller (name, age, gender) so bookings can be prefilled. At most 8.",
        {"name": {"type": "string", "minLength": 1, "maxLength": 60, "title": "Full name"},
         "age": {"type": "integer", "minimum": 1, "maximum": 110, "title": "Age"},
         "gender": {**GENDER, "title": "Gender"}},
        ("name", "age", "gender"),
        SE,
    ),
    "remove_traveller": ToolSpec(
        logic.remove_traveller, "Removes a saved co-traveller.", {"traveller_id": {"type": "string", "description": "Like TRV-2 (list_travellers)"}},
        ("traveller_id",), SE,
    ),
    # ------------------------------------------------------------ bookings
    "book_tickets": ToolSpec(
        logic.book_tickets,
        "Books seats on a bus: one passenger per seat in seat order (up to 4), boarding and dropping point ids from "
        "get_trip, contact email and phone, payment method and an optional offer code. Checks the seats are free, the "
        "women-only seat rule, the coupon and the wallet balance. Prefill the traveller and saved co-travellers from "
        "get_my_context. Show it as a form so the traveller reviews names, seats and points before paying.",
        {
            "trip_id": TRIP_ID,
            "seats": SEATS,
            "boarding_point": {"type": "string", "title": "Boarding point", "description": "Point id like BLR-2 from get_trip's boarding_points"},
            "dropping_point": {"type": "string", "title": "Dropping point", "description": "Point id like HYD-4 from get_trip's dropping_points"},
            **_passenger(1), **_passenger(2), **_passenger(3), **_passenger(4),
            "contact_email": {"type": "string", "format": "email", "title": "Email", "description": "For the e-ticket"},
            "contact_phone": {"type": "string", "title": "Mobile number", "description": "For the bus staff and SMS ticket"},
            "payment_method": {"type": "string", "enum": list(logic.PAYMENT_METHODS), "title": "Pay with", "description": "upi, card_on_file (Visa •••• 4242) or wallet"},
            "coupon_code": {"type": "string", "title": "Offer code (optional)"},
        },
        ("trip_id", "seats", "boarding_point", "dropping_point", "passenger_1_name", "passenger_1_age", "passenger_1_gender", "contact_email", "contact_phone"),
        SE,
    ),
    "list_bookings": ToolSpec(
        logic.list_bookings,
        "The traveller's bookings: filter by status (upcoming|in_transit|completed|cancelled), journey_from / journey_to "
        "dates, a city or operator; sort_by journey_date|booked_at|amount. Returns route, date, PNR, seats, amount paid, "
        "can_cancel, can_rate and `total`.",
        {"status": {"type": "string", "enum": list(logic.BOOKING_STATUSES)}, "journey_from": DATE, "journey_to": DATE, "city": CITY,
         "operator_id": OPERATOR_ID, "sort_by": {"type": "string", "enum": ["journey_date", "booked_at", "amount"]},
         "sort_order": SORT_ORDER, "limit": {"type": "integer", "minimum": 1}, "offset": {"type": "integer", "minimum": 0}},
    ),
    "get_booking": ToolSpec(
        logic.get_booking,
        "One booking (by id or PNR): bus, boarding and dropping points with times, passengers and seats, payment, refunds, "
        "history, and whether it can be cancelled (current charge and when it rises), rescheduled, re-pointed or rated.",
        {"booking_id": BOOKING_ID},
        ("booking_id",),
    ),
    "get_cancellation_quote": ToolSpec(
        logic.get_cancellation_quote,
        "What cancelling would cost: charge % (by hours before departure), charge, refund and where it goes — for all "
        "seats or only some. Use before proposing a cancellation.",
        {"booking_id": BOOKING_ID, "seats": {**SEATS, "description": "Only these seats (default: every active seat)"}},
        ("booking_id",),
    ),
    "cancel_booking": ToolSpec(
        logic.cancel_booking,
        "Cancels a booking, or only some of its seats, under the cancellation policy (10% from 48 h before departure, "
        "25% from 24 h, 50% from 12 h, 75% from 6 h; not within 6 h). Refunds to the original payment method.",
        {"booking_id": BOOKING_ID, "seats": {**SEATS, "title": "Seats to cancel (optional)", "description": "Leave empty to cancel every seat"},
         "reason": {"type": "string", "enum": list(logic.CANCEL_REASONS), "title": "Reason"}},
        ("booking_id",),
        SE,
    ),
    "change_boarding_point": ToolSpec(
        logic.change_boarding_point,
        "Changes the boarding and/or dropping point of an upcoming booking (until 4 h before departure). Give only what changes.",
        {"booking_id": BOOKING_ID,
         "boarding_point": {"type": "string", "title": "New boarding point", "description": "Point id like BLR-3 (get_booking's boarding_points)"},
         "dropping_point": {"type": "string", "title": "New dropping point", "description": "Point id like HYD-1"}},
        ("booking_id",),
        SE,
    ),
    "reschedule_booking": ToolSpec(
        logic.reschedule_booking,
        "Moves a booking to the same bus on another date (once per booking, until 12 h before departure): ₹100 fee plus "
        "any fare difference, charged to the original payment method. Keeps the seat numbers unless `seats` is given.",
        {"booking_id": BOOKING_ID, "new_date": {**DATE, "title": "New date"}, "seats": {**SEATS, "title": "Seats on the new date (optional)"}},
        ("booking_id", "new_date"),
        SE,
    ),
    "rate_trip": ToolSpec(
        logic.rate_trip,
        "Rates a completed trip (once): 1–5 stars and an optional review published on the operator's page.",
        {"booking_id": BOOKING_ID,
         "rating": {"type": "integer", "minimum": 1, "maximum": 5, "enum": [1, 2, 3, 4, 5], "title": "Rating"},
         "comment": {"type": "string", "maxLength": 1000, "title": "Review (optional)", "description": "The complete review in the traveller's words — write the full text"}},
        ("booking_id", "rating"),
        SE,
    ),
    "aggregate_bookings": ToolSpec(
        logic.aggregate_bookings,
        "Booking statistics for the traveller: metric count|sum_paid|seats|avg_paid grouped by status|month|route|operator|bus_type.",
        {"metric": {"type": "string", "enum": ["count", "sum_paid", "seats", "avg_paid"]},
         "group_by": {"type": "string", "enum": ["status", "month", "route", "operator", "bus_type"]}},
    ),
    "get_travel_spend_over_time": ToolSpec(
        logic.get_travel_spend_over_time,
        "The traveller's spend (after refunds), bookings made and trips taken per month for the last `months` (default 6) — for a chart.",
        {"months": {"type": "integer", "minimum": 1, "maximum": 24}},
    ),
    # ------------------------------------------------------------ cross-entity
    "get_overview": ToolSpec(logic.get_overview, "A summary for 'what's going on?': next trip, recent bookings, wallet, offers and what needs attention."),
    "list_attention_items": ToolSpec(
        logic.list_attention_items,
        "What needs the traveller's attention: trips leaving within 48 h (with boarding point), cancellation charges about to rise, trips to rate.",
    ),
    "search_all": ToolSpec(
        logic.search_all,
        "One free-text search over cities, boarding points, routes, operators, offers and the traveller's bookings (PNR, passenger names).",
        {"query": {"type": "string", "minLength": 1}},
        ("query",),
        per_user=False,
    ),
    "describe_data": ToolSpec(
        logic.describe_data,
        "The site's vocabulary and rules: cities, bus types, amenities, departure windows, seat rules, fares and GST, payment "
        "methods, cancellation policy, rescheduling and boarding-point rules.",
        per_user=False,
    ),
}


def tool_manifest() -> list[dict[str, Any]]:
    return [
        {"name": n, "description": s.description, "input_schema": s.input_schema, "classification": s.classification}
        for n, s in TOOL_SPECS.items()
    ]


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    spec = TOOL_SPECS.get(name)
    if spec is None:
        return {"error": f"unknown_tool:{name}"}
    kwargs = {k: v for k, v in arguments.items() if k in spec.properties and v is not None and v != ""}
    missing = [k for k in spec.required if k not in kwargs]
    if missing:
        return {"error": f"missing_arguments:{','.join(missing)}"}
    return spec.fn(**kwargs)
