"""Every Relay tool, defined once: function, description, JSON schema, classification.

``GET /tools`` and ``POST /tools/{name}`` are both generated from ``TOOL_SPECS``. Writes are
``side_effecting``: the assistant can only propose them, and they run after the guest approves
(or submits a form bound to them). The inventory behind this catalog is in ``../relay-tools.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from stays_api import logic
from stays_api.seeds import AMENITIES, DESTINATIONS, PROPERTY_TYPES


@dataclass(frozen=True)
class ToolSpec:
    fn: Callable[..., dict[str, Any]]
    description: str
    properties: dict[str, Any] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    classification: str = "read_only"
    # Needs a signed-in guest (X-Relay-User); the service answers 401 without one.
    per_user: bool = True

    @property
    def input_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {"type": "object", "properties": self.properties}
        if self.required:
            schema["required"] = list(self.required)
        return schema


SE = "side_effecting"
_DESTS = ", ".join(d["name"] for d in DESTINATIONS.values())
DESTINATION = {"type": "string", "description": f"A destination ({_DESTS}), a state (Kerala, Rajasthan…) or a kind (beach, mountains, countryside, lakes, city)"}
LISTING_ID = {"type": "string", "minLength": 1, "title": "Home", "description": "Listing id like LST-1004 — find it with search_listings"}
TRIP_ID = {"type": "string", "minLength": 1, "title": "Trip", "description": "Trip id like RSV-50004, or its confirmation code — find it with list_trips"}
DATE = {"type": "string", "format": "date"}
SORT_ORDER = {"type": "string", "enum": ["asc", "desc"]}
GUESTS = {
    "adults": {"type": "integer", "minimum": 1, "title": "Adults", "description": "Age 13+"},
    "children": {"type": "integer", "minimum": 0, "title": "Children", "description": "Ages 2–12"},
    "infants": {"type": "integer", "minimum": 0, "title": "Infants", "description": "Under 2 — don't count towards guests"},
    "pets": {"type": "integer", "minimum": 0, "maximum": 2, "title": "Pets"},
}
STAR = {"type": "integer", "minimum": 1, "maximum": 5, "enum": [1, 2, 3, 4, 5]}

TOOL_SPECS: dict[str, ToolSpec] = {
    # ------------------------------------------------------------ homes (reads)
    "search_listings": ToolSpec(
        logic.search_listings,
        "Search homes: destination (name, state or kind like 'beach'), check_in / check_out (only homes free for those "
        "nights, with the stay total), guests (adults, children, infants, pets), price per night range (₹), property "
        "type, room type, minimum bedrooms / beds / baths, amenities (all required), instant_book, superhost, min_rating; "
        "sort_by recommended|price|rating|reviews|newest. Returns compact listings and `total`. To show results on the "
        "site's own search page prefer the SEARCH_STAYS screen action.",
        {
            "destination": DESTINATION,
            "check_in": DATE,
            "check_out": DATE,
            **GUESTS,
            "min_price": {"type": "integer", "minimum": 0, "description": "Per night, ₹"},
            "max_price": {"type": "integer", "minimum": 0, "description": "Per night, ₹"},
            "property_type": {"type": "string", "enum": list(PROPERTY_TYPES)},
            "room_type": {"type": "string", "enum": list(logic.ROOM_TYPES)},
            "min_bedrooms": {"type": "integer", "minimum": 1},
            "min_beds": {"type": "integer", "minimum": 1},
            "min_baths": {"type": "integer", "minimum": 1},
            "amenities": {"type": "array", "items": {"type": "string", "enum": list(AMENITIES)}},
            "instant_book": {"type": "boolean"},
            "superhost": {"type": "boolean"},
            "min_rating": {"type": "number", "minimum": 0},
            "sort_by": {"type": "string", "enum": list(logic.SORTS)},
            "sort_order": SORT_ORDER,
            "limit": {"type": "integer", "minimum": 1},
        },
        per_user=False,
    ),
    "get_listing": ToolSpec(
        logic.get_listing,
        "One home: description, rooms, amenities, house rules (check-in / check-out times, pets, smoking, events), fees "
        "and discounts, minimum stay, cancellation policy, host, rating breakdown, latest reviews, booked nights in the "
        "next 60 days and which of the guest's wishlists it is in.",
        {"listing_id": LISTING_ID},
        ("listing_id",),
        per_user=False,
    ),
    "check_availability": ToolSpec(
        logic.check_availability,
        "Availability: with check_in / check_out, whether those nights are free (and which aren't); otherwise a month "
        "calendar (month YYYY-MM) with each night's availability and price.",
        {"listing_id": LISTING_ID, "month": {"type": "string", "description": "YYYY-MM"}, "check_in": DATE, "check_out": DATE},
        ("listing_id",),
        per_user=False,
    ),
    "get_price_quote": ToolSpec(
        logic.get_price_quote,
        "Exact price for a stay: each night (weekend / peak), extra-guest fee, weekly or monthly discount, cleaning and pet "
        "fees, 12% service fee, GST (12% or 18%), total — plus whether the nights are free and if it books instantly.",
        {"listing_id": LISTING_ID, "check_in": DATE, "check_out": DATE, **GUESTS},
        ("listing_id", "check_in", "check_out"),
        per_user=False,
    ),
    "compare_listings": ToolSpec(
        logic.compare_listings,
        "Two to four homes side by side (type, rooms, guests, price, rating, superhost, policy, amenities; with dates also "
        "availability and stay total) — for a comparison surface.",
        {"listing_ids": {"type": "array", "items": {"type": "string"}, "description": "2–4 listing ids"}, "check_in": DATE, "check_out": DATE},
        ("listing_ids",),
        per_user=False,
    ),
    "list_destinations": ToolSpec(logic.list_destinations, "Every destination with its state, kind, areas, number of homes, price range and average rating.", per_user=False),
    "aggregate_listings": ToolSpec(
        logic.aggregate_listings,
        "Home statistics: metric count|avg_price|min_price|avg_rating grouped by destination|property_type|room_type|kind|bedrooms, optionally in one destination. Feeds charts.",
        {"metric": {"type": "string", "enum": ["count", "avg_price", "min_price", "avg_rating"]},
         "group_by": {"type": "string", "enum": ["destination", "property_type", "room_type", "kind", "bedrooms"]}, "destination": DESTINATION},
        per_user=False,
    ),
    "get_top_listings": ToolSpec(
        logic.get_top_listings,
        "Rankings: rating, reviews, price_low (cheapest), price_high or value (rating per rupee), optionally in one destination.",
        {"rank_by": {"type": "string", "enum": ["rating", "reviews", "price_low", "price_high", "value"]}, "destination": DESTINATION,
         "limit": {"type": "integer", "minimum": 1}},
        per_user=False,
    ),
    "list_reviews": ToolSpec(
        logic.list_reviews,
        "Reviews, newest first: for a listing, by min_rating / max_rating, or mine=true for the guest's own.",
        {"listing_id": LISTING_ID, "min_rating": {"type": "integer", "minimum": 1}, "max_rating": {"type": "integer", "minimum": 1},
         "mine": {"type": "boolean"}, "limit": {"type": "integer", "minimum": 1}},
        per_user=False,
    ),
    "get_host": ToolSpec(
        logic.get_host, "A host: superhost, hosting since, response rate and time, languages, their homes and average rating.",
        {"host_id": {"type": "string", "description": "Like HST-04 (get_listing's host)"}}, ("host_id",), per_user=False,
    ),
    # ------------------------------------------------------------ the guest and wishlists
    "get_my_context": ToolSpec(
        logic.get_my_context,
        "Who the guest is: name, email, phone, city, payment methods, wishlists, next trip, trips taken and lifetime spend.",
    ),
    "list_wishlists": ToolSpec(logic.list_wishlists, "The guest's wishlists with the homes in each."),
    "get_wishlist": ToolSpec(logic.get_wishlist, "One wishlist (by id or name) with its homes.", {"wishlist_id": {"type": "string"}}, ("wishlist_id",)),
    "create_wishlist": ToolSpec(
        logic.create_wishlist, "Creates a named wishlist, optionally with a first home.",
        {"name": {"type": "string", "minLength": 1, "maxLength": 50, "title": "Name"}, "listing_id": LISTING_ID}, ("name",), SE,
    ),
    "save_to_wishlist": ToolSpec(
        logic.save_to_wishlist,
        "Saves a home to a wishlist (by name or id; a new name creates the list; default: the first list).",
        {"listing_id": LISTING_ID, "wishlist": {"type": "string", "title": "Wishlist", "description": "Name or id"}}, ("listing_id",), SE,
    ),
    "remove_from_wishlist": ToolSpec(
        logic.remove_from_wishlist, "Removes a home from one wishlist, or from every list when none is given.",
        {"listing_id": LISTING_ID, "wishlist": {"type": "string", "title": "Wishlist"}}, ("listing_id",), SE,
    ),
    # ------------------------------------------------------------ trips
    "reserve_stay": ToolSpec(
        logic.reserve_stay,
        "Books a home for the given nights and guests, paid by UPI or the card on file. Instant-book homes confirm at "
        "once; other hosts get a request with message_to_host (required for them) and accept or decline — the guest is "
        "charged only on acceptance. Checks availability, minimum stay, guest limit and pets. Show it as a form so the "
        "guest reviews dates, guests and price before paying.",
        {
            "listing_id": LISTING_ID,
            "check_in": {**DATE, "title": "Check-in"},
            "check_out": {**DATE, "title": "Check-out"},
            **GUESTS,
            "message_to_host": {"type": "string", "maxLength": 1000, "title": "Message to the host",
                                "description": "Who's coming and why — write the complete message (required for request-to-book homes)"},
            "payment_method": {"type": "string", "enum": list(logic.PAYMENT_METHODS), "title": "Pay with"},
        },
        ("listing_id", "check_in", "check_out", "adults"),
        SE,
    ),
    "list_trips": ToolSpec(
        logic.list_trips,
        "The guest's trips: filter by status (requested|upcoming|in_stay|completed|cancelled|declined), destination, "
        "check-in date range; sort_by check_in|booked_at|amount. Returns home, dates, guests, amount paid, can_cancel, "
        "refund_pct_now, can_review and `total`.",
        {"status": {"type": "string", "enum": list(logic.TRIP_STATUSES)}, "destination": DESTINATION, "check_in_from": DATE, "check_in_to": DATE,
         "sort_by": {"type": "string", "enum": ["check_in", "booked_at", "amount"]}, "sort_order": SORT_ORDER, "limit": {"type": "integer", "minimum": 1}},
    ),
    "get_trip": ToolSpec(
        logic.get_trip,
        "One trip: home, dates and check-in / check-out times, guests, price breakdown, payment, refunds, cancellation "
        "policy and refund % now, house manual (Wi-Fi, check-in, parking — once confirmed), messages and history.",
        {"reservation_id": TRIP_ID},
        ("reservation_id",),
    ),
    "get_cancellation_quote": ToolSpec(
        logic.get_cancellation_quote,
        "What cancelling a trip now would refund under the home's policy (and until when it is fully refundable). Use before proposing a cancellation.",
        {"reservation_id": TRIP_ID},
        ("reservation_id",),
    ),
    "cancel_reservation": ToolSpec(
        logic.cancel_reservation,
        "Cancels an upcoming trip or an open request under the home's cancellation policy; refunds to the original payment method.",
        {"reservation_id": TRIP_ID, "reason": {"type": "string", "enum": list(logic.CANCEL_REASONS), "title": "Reason"}},
        ("reservation_id",),
        SE,
    ),
    "change_reservation": ToolSpec(
        logic.change_reservation,
        "Changes an upcoming trip's dates and/or guests if the nights are free: the guest pays any increase; a decrease is "
        "refunded while the trip is fully refundable. Give only what changes.",
        {"reservation_id": TRIP_ID, "check_in": {**DATE, "title": "New check-in"}, "check_out": {**DATE, "title": "New check-out"}, **GUESTS},
        ("reservation_id",),
        SE,
    ),
    "message_host": ToolSpec(
        logic.message_host,
        "Sends a message to the host of a trip (questions about check-in, parking, early arrival…); the host's reply comes back in the thread.",
        {"reservation_id": TRIP_ID, "message": {"type": "string", "minLength": 1, "maxLength": 1000, "title": "Message",
                                                 "description": "The complete message in the guest's words — write the full text"}},
        ("reservation_id", "message"),
        SE,
    ),
    "list_messages": ToolSpec(
        logic.list_messages, "The inbox: one thread per trip with the last message; with reservation_id, that thread's messages.",
        {"reservation_id": TRIP_ID},
    ),
    "write_review": ToolSpec(
        logic.write_review,
        "Publishes the guest's review of a completed stay (within 14 days of check-out, once): overall 1–5, optional 1–5 "
        "for cleanliness, accuracy, communication, location, check-in and value, and the text.",
        {"reservation_id": TRIP_ID, "rating": {**STAR, "title": "Overall"},
         "comment": {"type": "string", "minLength": 20, "maxLength": 2000, "title": "Review", "description": "The complete review in the guest's words — write the full text"},
         "cleanliness": {**STAR, "title": "Cleanliness"}, "accuracy": {**STAR, "title": "Accuracy"}, "communication": {**STAR, "title": "Communication"},
         "location": {**STAR, "title": "Location"}, "check_in": {**STAR, "title": "Check-in"}, "value": {**STAR, "title": "Value"}},
        ("reservation_id", "rating", "comment"),
        SE,
    ),
    "aggregate_trips": ToolSpec(
        logic.aggregate_trips,
        "Trip statistics for the guest: metric count|sum_paid|nights|avg_night grouped by status|month|destination|property_type|host.",
        {"metric": {"type": "string", "enum": ["count", "sum_paid", "nights", "avg_night"]},
         "group_by": {"type": "string", "enum": ["status", "month", "destination", "property_type", "host"]}},
    ),
    "get_travel_spend_over_time": ToolSpec(
        logic.get_travel_spend_over_time,
        "The guest's spend (after refunds), bookings and nights stayed per month for the last `months` (default 12) — for a chart.",
        {"months": {"type": "integer", "minimum": 1, "maximum": 24}},
    ),
    # ------------------------------------------------------------ cross-entity
    "get_overview": ToolSpec(logic.get_overview, "A summary for 'what's going on?': next trip, recent trips, wishlists and what needs attention."),
    "list_attention_items": ToolSpec(
        logic.list_attention_items,
        "What needs the guest's attention: requests awaiting the host, check-ins within 3 days, free cancellation ending soon, stays to review.",
    ),
    "search_all": ToolSpec(
        logic.search_all,
        "One free-text search over destinations, areas, homes, hosts and the guest's trips and wishlists.",
        {"query": {"type": "string", "minLength": 1}},
        ("query",),
        per_user=False,
    ),
    "describe_data": ToolSpec(
        logic.describe_data,
        "The site's vocabulary and rules: destinations, property and room types, amenities, pricing (weekend, peak, fees, "
        "discounts, GST), stay rules, booking vs. requests, cancellation policies, changes and reviews.",
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
