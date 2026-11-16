"""Deterministic demo data for Roostly: destinations, hosts, 36 listings, their reviews, and the
guest every new user starts as (profile, wishlists, trips).

Nights already taken by other guests are derived from the listing id and the date, so every visitor
sees the same busy calendars; reservations made here are stored on top.
"""

from __future__ import annotations

import random
from typing import Any

DESTINATIONS: dict[str, dict[str, Any]] = {
    "goa": {"name": "Goa", "state": "Goa", "kind": "beach", "areas": ["Assagao", "Anjuna", "Palolem", "Candolim"]},
    "manali": {"name": "Manali", "state": "Himachal Pradesh", "kind": "mountains", "areas": ["Old Manali", "Vashisht", "Naggar"]},
    "coorg": {"name": "Coorg", "state": "Karnataka", "kind": "countryside", "areas": ["Madikeri", "Virajpet", "Kushalnagar"]},
    "udaipur": {"name": "Udaipur", "state": "Rajasthan", "kind": "city", "areas": ["Lake Pichola", "Ambrai Ghat", "Fateh Sagar"]},
    "jaipur": {"name": "Jaipur", "state": "Rajasthan", "kind": "city", "areas": ["C-Scheme", "Amer", "Bani Park"]},
    "alleppey": {"name": "Alleppey", "state": "Kerala", "kind": "lakes", "areas": ["Punnamada Lake", "Kumarakom", "Marari Beach"]},
    "rishikesh": {"name": "Rishikesh", "state": "Uttarakhand", "kind": "mountains", "areas": ["Tapovan", "Laxman Jhula", "Shivpuri"]},
    "pondicherry": {"name": "Pondicherry", "state": "Puducherry", "kind": "beach", "areas": ["White Town", "Auroville", "Serenity Beach"]},
    "ooty": {"name": "Ooty", "state": "Tamil Nadu", "kind": "mountains", "areas": ["Fernhill", "Lovedale", "Coonoor"]},
    "munnar": {"name": "Munnar", "state": "Kerala", "kind": "countryside", "areas": ["Chithirapuram", "Pothamedu", "Devikulam"]},
    "mumbai": {"name": "Mumbai", "state": "Maharashtra", "kind": "city", "areas": ["Bandra West", "Colaba", "Juhu"]},
    "bengaluru": {"name": "Bengaluru", "state": "Karnataka", "kind": "city", "areas": ["Indiranagar", "Koramangala", "Whitefield"]},
}

PROPERTY_TYPES = {
    "villa": "Villa",
    "cottage": "Cottage",
    "apartment": "Apartment",
    "houseboat": "Houseboat",
    "treehouse": "Treehouse",
    "haveli": "Heritage haveli",
    "farmhouse": "Farmhouse",
    "homestay": "Homestay room",
    "loft": "Loft",
}

AMENITIES = {
    "wifi": "Wi-Fi",
    "kitchen": "Kitchen",
    "ac": "Air conditioning",
    "pool": "Pool",
    "parking": "Free parking",
    "workspace": "Dedicated workspace",
    "washer": "Washing machine",
    "hot_tub": "Hot tub",
    "fireplace": "Fireplace",
    "bbq": "BBQ grill",
    "breakfast": "Breakfast included",
    "mountain_view": "Mountain view",
    "lake_view": "Lake view",
    "beach_access": "Beach access",
    "garden": "Garden",
    "ev_charger": "EV charger",
    "power_backup": "Power backup",
}

HOSTS: list[dict[str, Any]] = [
    {"id": "HST-01", "name": "Ananya", "superhost": True, "since": 2017, "response_rate": 99, "response_time": "within an hour", "languages": ["English", "Hindi", "Konkani"]},
    {"id": "HST-02", "name": "Tenzin", "superhost": True, "since": 2016, "response_rate": 98, "response_time": "within an hour", "languages": ["English", "Hindi"]},
    {"id": "HST-03", "name": "Kavya", "superhost": False, "since": 2021, "response_rate": 91, "response_time": "within a few hours", "languages": ["English", "Kannada", "Kodava"]},
    {"id": "HST-04", "name": "Vikram Singh", "superhost": True, "since": 2015, "response_rate": 100, "response_time": "within an hour", "languages": ["English", "Hindi", "Rajasthani"]},
    {"id": "HST-05", "name": "Thomas", "superhost": False, "since": 2019, "response_rate": 94, "response_time": "within a few hours", "languages": ["English", "Malayalam"]},
    {"id": "HST-06", "name": "Meenakshi", "superhost": True, "since": 2018, "response_rate": 97, "response_time": "within an hour", "languages": ["English", "Tamil", "French"]},
    {"id": "HST-07", "name": "Arjun", "superhost": False, "since": 2022, "response_rate": 88, "response_time": "within a day", "languages": ["English", "Hindi"]},
    {"id": "HST-08", "name": "Zara", "superhost": True, "since": 2018, "response_rate": 99, "response_time": "within an hour", "languages": ["English", "Hindi", "Marathi"]},
    {"id": "HST-09", "name": "Rohan", "superhost": False, "since": 2020, "response_rate": 92, "response_time": "within a few hours", "languages": ["English", "Kannada"]},
    {"id": "HST-10", "name": "Lakshmi", "superhost": True, "since": 2017, "response_rate": 96, "response_time": "within an hour", "languages": ["English", "Tamil"]},
]

# destination, title, type, room type, area index, guests, bedrooms, beds, baths, price/night, host, amenities, extras
_LISTINGS: list[tuple[str, str, str, str, int, int, int, int, int, int, str, tuple[str, ...], dict[str, Any]]] = [
    ("goa", "Casa Azul — pool villa near Assagao", "villa", "entire_place", 0, 8, 4, 5, 4, 14500, "HST-01", ("wifi", "kitchen", "ac", "pool", "parking", "bbq", "garden", "power_backup"), {"policy": "strict", "pets": True, "instant": False}),
    ("goa", "Anjuna studio, five minutes to the beach", "apartment", "entire_place", 1, 2, 1, 1, 1, 3200, "HST-01", ("wifi", "kitchen", "ac", "workspace", "beach_access"), {"policy": "flexible", "instant": True}),
    ("goa", "Palolem palm cottage", "cottage", "entire_place", 2, 3, 1, 2, 1, 4800, "HST-08", ("wifi", "ac", "beach_access", "breakfast", "garden"), {"policy": "moderate", "instant": True}),
    ("manali", "Pine-view log cabin in Old Manali", "cottage", "entire_place", 0, 4, 2, 2, 1, 5200, "HST-02", ("wifi", "kitchen", "fireplace", "mountain_view", "parking", "power_backup"), {"policy": "moderate", "instant": True, "pets": True}),
    ("manali", "Apple-orchard treehouse", "treehouse", "entire_place", 2, 2, 1, 1, 1, 6900, "HST-02", ("wifi", "mountain_view", "breakfast", "garden", "fireplace"), {"policy": "strict", "instant": False}),
    ("manali", "Vashisht homestay room with hot springs nearby", "homestay", "private_room", 1, 2, 1, 1, 1, 1900, "HST-07", ("wifi", "breakfast", "mountain_view"), {"policy": "flexible", "instant": True}),
    ("coorg", "Coffee-estate bungalow", "farmhouse", "entire_place", 0, 10, 5, 6, 4, 16500, "HST-03", ("wifi", "kitchen", "parking", "garden", "bbq", "breakfast", "power_backup"), {"policy": "strict", "instant": False, "pets": True}),
    ("coorg", "Riverside cottage at Virajpet", "cottage", "entire_place", 1, 4, 2, 2, 2, 5600, "HST-03", ("wifi", "kitchen", "parking", "garden"), {"policy": "moderate", "instant": True}),
    ("coorg", "Plantation homestay, Kodava breakfast", "homestay", "private_room", 2, 3, 1, 2, 1, 2600, "HST-03", ("wifi", "breakfast", "parking", "garden"), {"policy": "flexible", "instant": True}),
    ("udaipur", "Lake Pichola haveli suite", "haveli", "entire_place", 0, 4, 2, 2, 2, 11800, "HST-04", ("wifi", "ac", "lake_view", "breakfast", "workspace"), {"policy": "moderate", "instant": True}),
    ("udaipur", "Ambrai Ghat rooftop loft", "loft", "entire_place", 1, 2, 1, 1, 1, 4400, "HST-04", ("wifi", "ac", "lake_view", "kitchen"), {"policy": "flexible", "instant": True}),
    ("udaipur", "Fateh Sagar family apartment", "apartment", "entire_place", 2, 6, 3, 4, 2, 7200, "HST-04", ("wifi", "ac", "kitchen", "washer", "parking"), {"policy": "moderate", "instant": False}),
    ("jaipur", "Pink City heritage haveli", "haveli", "entire_place", 2, 8, 4, 5, 4, 13200, "HST-04", ("wifi", "ac", "pool", "breakfast", "parking", "garden"), {"policy": "strict", "instant": False}),
    ("jaipur", "C-Scheme designer apartment", "apartment", "entire_place", 0, 3, 1, 2, 1, 3900, "HST-09", ("wifi", "ac", "kitchen", "workspace", "washer", "ev_charger"), {"policy": "flexible", "instant": True}),
    ("jaipur", "Amer fort-view farmhouse", "farmhouse", "entire_place", 1, 12, 6, 8, 5, 18900, "HST-09", ("wifi", "ac", "pool", "parking", "bbq", "garden", "power_backup"), {"policy": "strict", "instant": False, "pets": True}),
    ("alleppey", "Two-bedroom houseboat on Punnamada", "houseboat", "entire_place", 0, 4, 2, 2, 2, 12500, "HST-05", ("ac", "lake_view", "breakfast"), {"policy": "strict", "instant": True}),
    ("alleppey", "Kumarakom backwater villa", "villa", "entire_place", 1, 6, 3, 3, 3, 9800, "HST-05", ("wifi", "ac", "pool", "lake_view", "kitchen", "parking"), {"policy": "moderate", "instant": False}),
    ("alleppey", "Marari beach homestay", "homestay", "private_room", 2, 2, 1, 1, 1, 2400, "HST-05", ("wifi", "breakfast", "beach_access", "garden"), {"policy": "flexible", "instant": True}),
    ("rishikesh", "Tapovan riverside apartment", "apartment", "entire_place", 0, 3, 1, 2, 1, 3100, "HST-07", ("wifi", "kitchen", "mountain_view", "workspace"), {"policy": "flexible", "instant": True}),
    ("rishikesh", "Laxman Jhula yoga loft", "loft", "entire_place", 1, 2, 1, 1, 1, 2700, "HST-07", ("wifi", "kitchen", "mountain_view"), {"policy": "moderate", "instant": True}),
    ("rishikesh", "Shivpuri jungle cottage", "cottage", "entire_place", 2, 5, 2, 3, 2, 6100, "HST-02", ("wifi", "kitchen", "parking", "garden", "bbq"), {"policy": "moderate", "instant": False, "pets": True}),
    ("pondicherry", "White Town French villa", "villa", "entire_place", 0, 6, 3, 3, 3, 10400, "HST-06", ("wifi", "ac", "kitchen", "garden", "workspace", "washer"), {"policy": "moderate", "instant": True}),
    ("pondicherry", "Auroville earth house", "cottage", "entire_place", 1, 2, 1, 1, 1, 3600, "HST-06", ("wifi", "garden", "breakfast"), {"policy": "flexible", "instant": True}),
    ("pondicherry", "Serenity Beach surf loft", "loft", "entire_place", 2, 3, 1, 2, 1, 4200, "HST-06", ("wifi", "ac", "kitchen", "beach_access"), {"policy": "flexible", "instant": True}),
    ("ooty", "Fernhill colonial cottage", "cottage", "entire_place", 0, 5, 2, 3, 2, 6800, "HST-10", ("wifi", "kitchen", "fireplace", "mountain_view", "garden", "parking"), {"policy": "moderate", "instant": True, "pets": True}),
    ("ooty", "Lovedale tea-garden villa", "villa", "entire_place", 1, 8, 4, 5, 3, 12900, "HST-10", ("wifi", "kitchen", "fireplace", "mountain_view", "parking", "bbq"), {"policy": "strict", "instant": False}),
    ("ooty", "Coonoor homestay room", "homestay", "private_room", 2, 2, 1, 1, 1, 2100, "HST-10", ("wifi", "breakfast", "mountain_view"), {"policy": "flexible", "instant": True}),
    ("munnar", "Tea-valley glass cottage", "cottage", "entire_place", 0, 2, 1, 1, 1, 7400, "HST-05", ("wifi", "mountain_view", "breakfast", "fireplace", "hot_tub"), {"policy": "strict", "instant": True}),
    ("munnar", "Pothamedu family farmhouse", "farmhouse", "entire_place", 1, 8, 4, 4, 3, 9900, "HST-05", ("wifi", "kitchen", "mountain_view", "parking", "garden"), {"policy": "moderate", "instant": False}),
    ("munnar", "Devikulam treehouse", "treehouse", "entire_place", 2, 2, 1, 1, 1, 5800, "HST-05", ("mountain_view", "breakfast", "garden"), {"policy": "moderate", "instant": True}),
    ("mumbai", "Bandra sea-facing apartment", "apartment", "entire_place", 0, 4, 2, 2, 2, 9200, "HST-08", ("wifi", "ac", "kitchen", "workspace", "washer"), {"policy": "moderate", "instant": True}),
    ("mumbai", "Colaba art-deco loft", "loft", "entire_place", 1, 2, 1, 1, 1, 6400, "HST-08", ("wifi", "ac", "kitchen", "workspace"), {"policy": "flexible", "instant": True}),
    ("mumbai", "Juhu room with a balcony", "homestay", "private_room", 2, 2, 1, 1, 1, 3300, "HST-08", ("wifi", "ac", "breakfast", "beach_access"), {"policy": "flexible", "instant": True}),
    ("bengaluru", "Indiranagar work-from-home flat", "apartment", "entire_place", 0, 3, 1, 2, 1, 4100, "HST-09", ("wifi", "ac", "kitchen", "workspace", "washer", "power_backup"), {"policy": "flexible", "instant": True}),
    ("bengaluru", "Koramangala garden loft", "loft", "entire_place", 1, 2, 1, 1, 1, 3500, "HST-09", ("wifi", "kitchen", "workspace", "garden"), {"policy": "flexible", "instant": True, "pets": True}),
    ("bengaluru", "Whitefield villa with a pool", "villa", "entire_place", 2, 8, 4, 4, 4, 11200, "HST-09", ("wifi", "ac", "pool", "kitchen", "parking", "ev_charger", "bbq"), {"policy": "moderate", "instant": False}),
]

_ICON = {"villa": "home", "cottage": "trees", "apartment": "building", "houseboat": "sailboat", "treehouse": "tree", "haveli": "landmark",
         "farmhouse": "wheat", "homestay": "bed", "loft": "warehouse"}


def build_listings() -> list[dict[str, Any]]:
    listings = []
    for n, (dest, title, ptype, room, area, guests, bedrooms, beds, baths, price, host, amenities, extra) in enumerate(_LISTINGS):
        rng = random.Random(f"listing:{n}")
        d = DESTINATIONS[dest]
        included = 2 if guests <= 4 else max(2, guests - 2)
        listings.append({
            "id": f"LST-{1001 + n}",
            "title": title,
            "destination": dest,
            "area": d["areas"][area],
            "property_type": ptype,
            "room_type": room,
            "max_guests": guests,
            "guests_included": included,
            "extra_guest_fee": 0 if guests <= included else int(round(price * 0.08 / 50) * 50),
            "bedrooms": bedrooms,
            "beds": beds,
            "baths": baths,
            "price": price,
            "weekend_price": int(round(price * rng.choice([1.1, 1.15, 1.2]) / 100) * 100),
            "cleaning_fee": 0 if room == "private_room" else int(round(max(500, price * 0.12) / 100) * 100),
            "pet_fee": 600 if extra.get("pets") else 0,
            "weekly_discount": rng.choice([0, 5, 10, 12, 15]),
            "monthly_discount": rng.choice([15, 20, 25, 30]),
            "min_nights": 2 if price >= 9000 else rng.choice([1, 1, 2]),
            "instant_book": extra.get("instant", True),
            "cancellation_policy": extra.get("policy", "moderate"),
            "pets_allowed": bool(extra.get("pets")),
            "smoking_allowed": False,
            "events_allowed": ptype in ("farmhouse", "villa") and guests >= 8,
            "check_in_from": "14:00" if ptype != "houseboat" else "12:00",
            "check_out_by": "11:00" if ptype != "houseboat" else "09:00",
            "host_id": host,
            "amenities": list(amenities),
            "hue": rng.randint(0, 359),
            "icon": _ICON[ptype],
            "summary": f"{PROPERTY_TYPES[ptype]} in {d['areas'][area]}, {d['name']} · {guests} guests · {bedrooms} bedroom{'s' if bedrooms > 1 else ''}",
            "description": _describe(title, ptype, d, area, amenities),
            "house_manual": {
                "wifi": f"Roostly-{1001 + n} / password stay{1001 + n}",
                "check_in": "Self check-in with a lockbox; the code is sent on the morning of arrival."
                if ptype not in ("homestay", "houseboat") else "Your host meets you at the door.",
                "parking": "Free parking on the premises." if "parking" in amenities else "Street parking nearby; no parking on the premises.",
            },
            "created_days_ago": rng.randint(20, 1500),
        })
    return listings


def _describe(title: str, ptype: str, d: dict[str, Any], area: int, amenities: tuple[str, ...]) -> str:
    feature = {
        "pool": "a private pool", "lake_view": "views over the water", "mountain_view": "mountain views from the bed",
        "beach_access": "the beach a short walk away", "fireplace": "a fireplace for cold nights", "breakfast": "a home-cooked breakfast",
        "workspace": "a proper desk and fast Wi-Fi", "garden": "a quiet garden",
    }
    best = next((feature[a] for a in amenities if a in feature), "everything you need")
    return (f"{title.split(' — ')[0]} is a {PROPERTY_TYPES[ptype].lower()} in {d['areas'][area]}, {d['name']}, with {best}. "
            f"Ideal for a {'slow weekend' if d['kind'] != 'city' else 'city break'}; your host lives nearby and answers quickly.")


_REVIEW_TEXT = {
    5: ["Exactly like the photos, spotless and peaceful. The host thought of everything.", "One of the best stays we've had in India — we'll be back.",
        "Beautiful place, warm host, and the location is perfect."],
    4: ["Lovely stay. The Wi-Fi dropped a couple of times but the host fixed it fast.", "Great location and comfortable beds; a bit of road noise at night.",
        "Clean and cosy, check-in was easy. Kitchen could use a few more pans."],
    3: ["Fine for a night or two. Photos make it look bigger than it is.", "Good location but the bathroom needed a deep clean."],
}
_GUESTS = ["Aditi", "Rahul", "Sara", "Neil", "Ishaan", "Pooja", "Kabir", "Meera", "Daniel", "Fatima", "Varun", "Leah"]
SUB_RATINGS = ("cleanliness", "accuracy", "communication", "location", "check_in", "value")


def build_reviews(listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    for listing in listings:
        rng = random.Random(f"reviews:{listing['id']}")
        quality = rng.uniform(4.2, 4.95)
        for i in range(rng.randint(4, 9)):
            rating = 5 if rng.random() < quality - 4 + 0.15 else 4 if rng.random() < 0.85 else 3
            subs = {k: max(1, min(5, rating + rng.choice([0, 0, 0, -1, 1]))) for k in SUB_RATINGS}
            reviews.append({
                "id": f"RVW-{listing['id'][4:]}-{i + 1}",
                "listing_id": listing["id"],
                "author": rng.choice(_GUESTS),
                "user_id": None,
                "rating": rating,
                "sub_ratings": subs,
                "comment": rng.choice(_REVIEW_TEXT[rating]),
                "days_ago": rng.randint(5, 300),
            })
    return reviews


DEFAULT_GUEST: dict[str, Any] = {
    "name": "Priya Nair",
    "email": "priya.nair@example.com",
    "phone": "+91 98765 43210",
    "city": "Bengaluru",
    "verified": True,
    "upi_id": "priya@okroostly",
}

SAMPLE_WISHLISTS: list[dict[str, Any]] = [
    {"name": "Monsoon getaways", "listings": ["LST-1007", "LST-1016", "LST-1028"]},
    {"name": "Goa with friends", "listings": ["LST-1001", "LST-1003"]},
]

# Trips every new user starts with: listing, days from today to check-in, nights, guests, outcome.
SAMPLE_TRIPS: list[dict[str, Any]] = [
    {"listing": "LST-1010", "days": -150, "nights": 3, "adults": 2, "outcome": "completed", "review": 5},
    {"listing": "LST-1004", "days": -75, "nights": 4, "adults": 2, "children": 1, "outcome": "completed", "review": 4},
    {"listing": "LST-1022", "days": -40, "nights": 2, "adults": 2, "outcome": "cancelled"},
    {"listing": "LST-1034", "days": -9, "nights": 3, "adults": 1, "outcome": "completed"},
    {"listing": "LST-1023", "days": 9, "nights": 3, "adults": 2, "outcome": "upcoming"},
    {"listing": "LST-1025", "days": 38, "nights": 4, "adults": 3, "children": 1, "outcome": "upcoming"},
]

HOST_REPLIES: dict[str, str] = {
    "check": "Check-in is from {check_in_from}; {check_in}",
    "early": "I'll try to have the place ready early — I'll confirm the morning you arrive. Bags can be dropped any time after 10.",
    "late": "Late check-out until 1 pm is fine if nobody arrives that day; I'll let you know the day before.",
    "park": "{parking}",
    "wifi": "The Wi-Fi details: {wifi}.",
    "pet": "{pets}",
    "airport": "A taxi from the airport or station is easiest; I can book one for you — just send your arrival time.",
}
