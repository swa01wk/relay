"""Deterministic demo data for Wayline: cities and their boarding points, routes, operators,
daily schedules, operator reviews, coupons and the traveller every new user starts as.

Trips are not stored: a trip is a schedule on a date (``SCH-1042-20261115``). Seats already sold
to other travellers are derived from the trip id, so every visitor sees the same busy buses.
"""

from __future__ import annotations

import random
from typing import Any

# code -> name, state, boarding / dropping points (name, landmark)
CITIES: dict[str, dict[str, Any]] = {
    "BLR": {"name": "Bengaluru", "state": "Karnataka", "points": [
        ("Majestic", "Kempegowda Bus Station"), ("Shanthinagar", "Double Road"), ("Silk Board", "Hosur Road flyover"),
        ("Electronic City", "Infosys Gate 1")]},
    "CHE": {"name": "Chennai", "state": "Tamil Nadu", "points": [
        ("Koyambedu", "CMBT Omni Bus Stand"), ("Guindy", "Kathipara Junction"), ("Tambaram", "Railway station east"),
        ("Porur", "Porur Junction")]},
    "HYD": {"name": "Hyderabad", "state": "Telangana", "points": [
        ("Ameerpet", "Metro station"), ("Kukatpally", "KPHB Colony"), ("Lakdikapul", "Telephone Bhavan"),
        ("Miyapur", "X Roads")]},
    "MUM": {"name": "Mumbai", "state": "Maharashtra", "points": [
        ("Dadar", "Dadar TT Circle"), ("Sion", "Sion Circle"), ("Vashi", "Vashi Plaza"), ("Borivali", "National Park gate")]},
    "PUN": {"name": "Pune", "state": "Maharashtra", "points": [
        ("Swargate", "Swargate Bus Stand"), ("Shivajinagar", "Wakdewadi"), ("Hinjewadi", "Wakad Bridge"),
        ("Katraj", "Katraj Chowk")]},
    "GOA": {"name": "Goa (Panaji)", "state": "Goa", "points": [
        ("Panaji", "Kadamba Bus Stand"), ("Mapusa", "Mapusa Bus Stand"), ("Margao", "Kadamba Margao"),
        ("Porvorim", "O'Coqueiro Junction")]},
    "MYS": {"name": "Mysuru", "state": "Karnataka", "points": [
        ("Mysuru Bus Stand", "Suburban Bus Stand"), ("Hinkal", "Ring Road Junction"), ("Bannimantap", "Depot"),
        ("Srirangapatna", "Highway stop")]},
    "CBE": {"name": "Coimbatore", "state": "Tamil Nadu", "points": [
        ("Gandhipuram", "Omni Bus Stand"), ("Ukkadam", "Bus Terminus"), ("Avinashi Road", "Hope College"),
        ("Singanallur", "Bus Stand")]},
    "COK": {"name": "Kochi", "state": "Kerala", "points": [
        ("Vyttila Hub", "Mobility Hub"), ("Kaloor", "Stadium Junction"), ("Edappally", "Lulu Junction"),
        ("Aluva", "Bypass")]},
    "MNG": {"name": "Mangaluru", "state": "Karnataka", "points": [
        ("Bejai", "KSRTC Bus Stand"), ("Pumpwell", "Circle"), ("Surathkal", "NITK Gate"), ("Hampankatta", "Clock Tower")]},
    "VJA": {"name": "Vijayawada", "state": "Andhra Pradesh", "points": [
        ("Pandit Nehru Bus Station", "PNBS"), ("Benz Circle", "Benz Circle"), ("Ramavarappadu", "Ring Road"),
        ("Gollapudi", "Y Junction")]},
    "MDU": {"name": "Madurai", "state": "Tamil Nadu", "points": [
        ("Mattuthavani", "Integrated Bus Terminus"), ("Arapalayam", "Bus Stand"), ("Periyar", "Bus Stand"),
        ("Thirunagar", "Bypass")]},
}

# (a, b, distance km, typical duration minutes) — every route runs in both directions
_ROUTES: list[tuple[str, str, int, int]] = [
    ("BLR", "CHE", 346, 360),
    ("BLR", "HYD", 570, 570),
    ("BLR", "MYS", 145, 180),
    ("BLR", "GOA", 560, 600),
    ("BLR", "CBE", 365, 420),
    ("BLR", "COK", 550, 600),
    ("BLR", "MNG", 352, 450),
    ("CHE", "HYD", 630, 660),
    ("CHE", "CBE", 505, 510),
    ("CHE", "MDU", 460, 480),
    ("MUM", "PUN", 150, 210),
    ("MUM", "GOA", 590, 660),
    ("PUN", "GOA", 450, 540),
    ("HYD", "VJA", 275, 300),
    ("HYD", "PUN", 560, 600),
]

ROUTES: list[dict[str, Any]] = []
for _a, _b, _km, _mins in _ROUTES:
    for _f, _t in ((_a, _b), (_b, _a)):
        ROUTES.append({"id": f"{_f}-{_t}", "from": _f, "to": _t, "distance_km": _km, "duration_min": _mins})

BUS_TYPES: dict[str, dict[str, Any]] = {
    "ac_sleeper": {"label": "AC Sleeper (2+1)", "ac": True, "sleeper": True, "per_km": 2.3, "speed": 1.0},
    "multi_axle_sleeper": {"label": "Multi-Axle AC Sleeper (2+1)", "ac": True, "sleeper": True, "per_km": 2.8, "speed": 0.95},
    "non_ac_sleeper": {"label": "Non-AC Sleeper (2+1)", "ac": False, "sleeper": True, "per_km": 1.6, "speed": 1.08},
    "ac_seater": {"label": "AC Seater Push-back (2+2)", "ac": True, "sleeper": False, "per_km": 1.5, "speed": 1.0},
    "non_ac_seater": {"label": "Non-AC Seater (2+2)", "ac": False, "sleeper": False, "per_km": 1.05, "speed": 1.1},
}

AMENITIES = {
    "charging_point": "Charging point",
    "water_bottle": "Water bottle",
    "blanket": "Blanket",
    "reading_light": "Reading light",
    "live_tracking": "Live tracking",
    "wifi": "Wi-Fi",
    "cctv": "CCTV",
    "toilet": "Toilet",
}

# id, name, fare factor, base rating, hue (for the logo tile)
OPERATORS: list[dict[str, Any]] = [
    {"id": "OP-NSC", "name": "Northstar Coaches", "factor": 1.12, "rating": 4.5, "hue": 220},
    {"id": "OP-DCC", "name": "Deccan Comfort", "factor": 1.0, "rating": 4.2, "hue": 28},
    {"id": "OP-CRD", "name": "Coastal Rider", "factor": 0.95, "rating": 4.0, "hue": 190},
    {"id": "OP-MLS", "name": "Moonlit Sleepers", "factor": 1.08, "rating": 4.4, "hue": 265},
    {"id": "OP-KBZ", "name": "Konkan Breeze", "factor": 0.98, "rating": 4.1, "hue": 150},
    {"id": "OP-TMT", "name": "Tamarind Tours", "factor": 0.9, "rating": 3.8, "hue": 12},
    {"id": "OP-BBI", "name": "Bluebird Intercity", "factor": 1.04, "rating": 4.3, "hue": 205},
    {"id": "OP-SFW", "name": "Saffron Wheels", "factor": 0.92, "rating": 3.9, "hue": 40},
]

COUPONS: list[dict[str, Any]] = [
    {"code": "WAYLINE10", "title": "10% off any bus", "kind": "percent", "value": 10, "max_discount": 200, "min_fare": 500,
     "description": "10% off the fare, up to ₹200, on bookings of ₹500 or more."},
    {"code": "NIGHTOWL", "title": "₹150 off night buses", "kind": "flat", "value": 150, "min_fare": 800, "night_only": True,
     "description": "₹150 off buses leaving at 9 pm or later, on fares of ₹800 or more."},
    {"code": "GROUP4", "title": "12% off for 3+ seats", "kind": "percent", "value": 12, "max_discount": 400, "min_seats": 3,
     "description": "12% off, up to ₹400, when you book three or more seats together."},
    {"code": "FIRSTRIDE", "title": "₹250 off your first trip", "kind": "flat", "value": 250, "min_fare": 600, "first_booking": True,
     "description": "₹250 off your first Wayline booking (fare ₹600 or more)."},
]

DEFAULT_TRAVELLER: dict[str, Any] = {
    "name": "Priya Nair",
    "email": "priya.nair@example.com",
    "phone": "+91 98765 43210",
    "gender": "female",
    "age": 29,
    "home_city": "BLR",
    "wallet_balance": 750,
    "upi_id": "priya@okwayline",
}
SAMPLE_TRAVELLERS: list[dict[str, Any]] = [
    {"name": "Rahul Nair", "age": 32, "gender": "male"},
    {"name": "Meera Nair", "age": 58, "gender": "female"},
]

# The bookings every new user starts with: route, days from today (negative = past), bus type
# wanted, passengers (indexes: 0 = the user, 1.. = saved travellers), outcome.
SAMPLE_BOOKINGS: list[dict[str, Any]] = [
    {"route": "HYD-BLR", "days": -128, "type": "ac_sleeper", "pax": [0], "outcome": "completed", "rating": 5},
    {"route": "BLR-COK", "days": -96, "type": "multi_axle_sleeper", "pax": [0, 1], "outcome": "completed", "rating": 4},
    {"route": "BLR-GOA", "days": -64, "type": "ac_sleeper", "pax": [0, 1], "outcome": "cancelled"},
    {"route": "BLR-CHE", "days": -41, "type": "ac_seater", "pax": [0, 2], "outcome": "completed", "rating": 4},
    {"route": "CHE-BLR", "days": -18, "type": "ac_sleeper", "pax": [0], "outcome": "completed"},
    {"route": "BLR-HYD", "days": 2, "type": "multi_axle_sleeper", "pax": [0, 1], "outcome": "upcoming"},
    {"route": "BLR-MYS", "days": 12, "type": "ac_seater", "pax": [0, 1, 2], "outcome": "upcoming"},
]


def _times_for(rng: random.Random, duration: int) -> list[str]:
    if duration >= 420:  # long routes: mostly overnight
        slots = ["06:30", "08:00", "13:30", "19:00", "19:45", "20:30", "21:00", "21:30", "22:00", "22:45", "23:15", "23:45"]
        count = rng.randint(5, 7)
    else:
        slots = ["05:30", "06:15", "07:00", "08:30", "10:00", "12:30", "14:00", "16:30", "18:00", "20:00", "21:30", "23:00"]
        count = rng.randint(5, 7)
    return sorted(rng.sample(slots, count))


def build_schedules() -> list[dict[str, Any]]:
    """Every bus that runs daily: route, operator, type, departure time, duration, fare."""
    schedules: list[dict[str, Any]] = []
    number = 1001
    for route in ROUTES:
        rng = random.Random(f"wayline:{route['id']}")
        long_route = route["duration_min"] >= 420
        for depart in _times_for(rng, route["duration_min"]):
            hour = int(depart[:2])
            overnight = long_route and (hour >= 18 or hour < 5)
            if overnight:
                bus_type = rng.choice(["ac_sleeper", "ac_sleeper", "multi_axle_sleeper", "multi_axle_sleeper", "non_ac_sleeper"])
            elif long_route:
                bus_type = rng.choice(["ac_seater", "ac_sleeper", "non_ac_seater"])
            else:
                bus_type = rng.choice(["ac_seater", "ac_seater", "non_ac_seater", "ac_sleeper"])
            spec = BUS_TYPES[bus_type]
            operator = rng.choice(OPERATORS)
            duration = int(round(route["duration_min"] * spec["speed"] * rng.uniform(0.96, 1.06) / 5) * 5)
            fare = max(199, int(round(route["distance_km"] * spec["per_km"] * operator["factor"] * rng.uniform(0.92, 1.1) / 10) * 10 - 1))
            amenities = ["charging_point", "water_bottle", "reading_light"]
            if spec["ac"]:
                amenities.append("cctv")
            if spec["sleeper"] and spec["ac"]:
                amenities.append("blanket")
            if operator["rating"] >= 4.2 or rng.random() < 0.4:
                amenities.append("live_tracking")
            if bus_type == "multi_axle_sleeper":
                amenities += ["wifi", "toilet"] if rng.random() < 0.5 else ["wifi"]
            schedules.append({
                "id": f"SCH-{number}",
                "route": route["id"],
                "from": route["from"],
                "to": route["to"],
                "distance_km": route["distance_km"],
                "operator_id": operator["id"],
                "bus_type": bus_type,
                "departs": depart,
                "duration_min": duration,
                "fare": fare,
                "amenities": amenities,
                "rating_offset": round(rng.uniform(-0.25, 0.2), 2),
            })
            number += 1
    return schedules


_REVIEW_TEXT = {
    5: ["Clean bus, left right on time and the driver was careful all night.", "Very comfortable berth, got proper sleep. Will book again.",
        "Staff were polite and the live tracking link actually worked."],
    4: ["Good overall. Reached 20 minutes late but the bus was clean.", "Comfortable seats, charging points worked. AC was a bit cold.",
        "Decent trip, boarding point was easy to find."],
    3: ["Okay for the price. The bus stopped a little too long for dinner.", "Berth was fine but the blanket wasn't fresh."],
    2: ["Left 45 minutes late from the first boarding point.", "AC was weak for most of the night."],
}
_REVIEWERS = ["Arjun K.", "Sneha R.", "Vikram S.", "Ananya P.", "Rohit M.", "Divya T.", "Karthik V.", "Fatima S.", "Nikhil J.", "Lakshmi I."]


def build_reviews() -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    number = 1
    for operator in OPERATORS:
        rng = random.Random(f"reviews:{operator['id']}")
        for i in range(rng.randint(5, 8)):
            drift = rng.random()
            rating = 5 if drift < (operator["rating"] - 3.2) / 2 else 4 if drift < 0.8 else 3 if drift < 0.93 else 2
            reviews.append({
                "id": f"REV-{number:04d}",
                "operator_id": operator["id"],
                "route": rng.choice(ROUTES)["id"],
                "author": rng.choice(_REVIEWERS),
                "user_id": None,
                "rating": rating,
                "comment": rng.choice(_REVIEW_TEXT[rating]),
                "days_ago": rng.randint(3, 160),
            })
            number += 1
    return reviews
