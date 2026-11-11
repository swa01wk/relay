"""Deterministic demo data for the Oakline store: catalog, reviews, coupons and the sample
order history every new shopper starts with."""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

CATEGORIES = ("Audio", "Home Office", "Kitchen", "Outdoor", "Wellness", "Accessories")
BRANDS = ("Oakline", "Northpeak", "Sonora", "Hearth & Co", "Fieldwork", "Calma")

# id, name, category, brand, price, compare_at (sale when set), stock, hue, summary, features
_PRODUCTS: list[tuple[str, str, str, str, float, float | None, int, int, str, tuple[str, ...]]] = [
    ("SKU-1001", "Aurora Wireless Headphones", "Audio", "Sonora", 179.0, 219.0, 34, 262,
     "Over-ear noise-cancelling headphones with 40-hour battery.", ("Active noise cancelling", "40 h battery", "USB-C fast charge")),
    ("SKU-1002", "Pulse Mini Speaker", "Audio", "Sonora", 59.0, None, 120, 200,
     "Pocket Bluetooth speaker, waterproof, surprisingly loud.", ("IP67 waterproof", "12 h battery", "Pair two for stereo")),
    ("SKU-1003", "Studio Monitor Pair", "Audio", "Sonora", 329.0, None, 9, 215,
     "Powered bookshelf monitors for desks and small rooms.", ("50 W per side", "Optical + RCA in", "Walnut cabinet")),
    ("SKU-1004", "Echo Buds Pro", "Audio", "Sonora", 129.0, 149.0, 58, 280,
     "True wireless earbuds with transparency mode.", ("ANC + transparency", "Wireless charging case", "Sweat resistant")),
    ("SKU-1005", "Vinyl Turntable Classic", "Audio", "Oakline", 249.0, None, 6, 25,
     "Belt-drive turntable with built-in preamp.", ("33/45 RPM", "Built-in phono preamp", "Bluetooth out")),
    ("SKU-2001", "Summit Standing Desk", "Home Office", "Northpeak", 549.0, 649.0, 14, 30,
     "Dual-motor sit-stand desk with memory presets.", ("Dual motor", "4 memory presets", "160 × 75 cm top")),
    ("SKU-2002", "Ergo Mesh Chair", "Home Office", "Northpeak", 389.0, None, 22, 210,
     "Breathable mesh chair with adjustable lumbar support.", ("Adjustable lumbar", "4D armrests", "12-year warranty")),
    ("SKU-2003", "Lumen Desk Lamp", "Home Office", "Oakline", 79.0, None, 75, 45,
     "Dimmable LED lamp with warm-to-cool colour control.", ("5 colour temperatures", "USB-C charging port", "Touch dimmer")),
    ("SKU-2004", "Felt Desk Mat XL", "Home Office", "Oakline", 39.0, None, 140, 160,
     "Wool felt mat that quiets the keyboard and protects the desk.", ("Merino wool felt", "90 × 40 cm", "Non-slip base")),
    ("SKU-2005", "Monitor Arm Duo", "Home Office", "Northpeak", 159.0, 189.0, 3, 220,
     "Gas-spring arm for two monitors up to 32 inches.", ("Holds 2 × 9 kg", "Cable management", "VESA 75/100")),
    ("SKU-2006", "Mechanical Keyboard 75", "Home Office", "Northpeak", 139.0, None, 41, 260,
     "Hot-swappable 75% keyboard with tactile switches.", ("Hot-swap switches", "Bluetooth + USB-C", "PBT keycaps")),
    ("SKU-3001", "Pour-Over Coffee Set", "Kitchen", "Hearth & Co", 64.0, None, 55, 30,
     "Ceramic dripper, glass carafe and gooseneck kettle.", ("Ceramic dripper", "600 ml carafe", "Gooseneck kettle")),
    ("SKU-3002", "Cast Iron Skillet 26 cm", "Kitchen", "Hearth & Co", 49.0, 59.0, 80, 15,
     "Pre-seasoned skillet that goes from stove to oven.", ("Pre-seasoned", "Oven safe 260 °C", "Lifetime warranty")),
    ("SKU-3003", "Chef's Knife 20 cm", "Kitchen", "Hearth & Co", 89.0, None, 37, 0,
     "Forged stainless chef's knife with a full tang.", ("Forged steel", "Full tang", "Hand-sharpened edge")),
    ("SKU-3004", "Smart Kettle", "Kitchen", "Oakline", 99.0, 119.0, 0, 190,
     "Variable-temperature kettle with keep-warm.", ("40–100 °C presets", "1.7 l", "Keep warm 2 h")),
    ("SKU-3005", "Stoneware Dinner Set", "Kitchen", "Hearth & Co", 119.0, None, 18, 35,
     "Twelve-piece reactive-glaze stoneware for four.", ("12 pieces", "Dishwasher safe", "Microwave safe")),
    ("SKU-3006", "Espresso Grinder", "Kitchen", "Hearth & Co", 199.0, None, 11, 20,
     "Conical burr grinder with 40 grind settings.", ("Conical burrs", "40 settings", "Low retention")),
    ("SKU-4001", "Trail Daypack 24 L", "Outdoor", "Fieldwork", 89.0, None, 64, 145,
     "Lightweight daypack with a ventilated back panel.", ("24 litres", "Rain cover", "Hydration sleeve")),
    ("SKU-4002", "Ultralight Tent 2P", "Outdoor", "Fieldwork", 299.0, 349.0, 12, 100,
     "Two-person freestanding tent, 1.4 kg packed.", ("1.4 kg", "Freestanding", "Two vestibules")),
    ("SKU-4003", "Insulated Bottle 750 ml", "Outdoor", "Fieldwork", 34.0, None, 210, 175,
     "Keeps drinks cold 24 h or hot 12 h.", ("Double wall steel", "Leak-proof lid", "Dishwasher safe")),
    ("SKU-4004", "Camp Stove Compact", "Outdoor", "Fieldwork", 69.0, None, 27, 10,
     "Folding canister stove that boils a litre in 4 minutes.", ("Piezo ignition", "3,000 W", "Folds to 9 cm")),
    ("SKU-4005", "Down Sleeping Bag", "Outdoor", "Fieldwork", 239.0, 279.0, 8, 230,
     "Comfortable to −5 °C, packs to the size of a loaf.", ("650-fill down", "Comfort −5 °C", "Compression sack")),
    ("SKU-5001", "Cork Yoga Mat", "Wellness", "Calma", 79.0, None, 46, 95,
     "Natural cork top with a grippy rubber base.", ("Cork + natural rubber", "6 mm", "Carry strap")),
    ("SKU-5002", "Aroma Diffuser", "Wellness", "Calma", 45.0, 55.0, 70, 300,
     "Ultrasonic diffuser with soft ambient light.", ("8 h runtime", "Auto shut-off", "Whisper quiet")),
    ("SKU-5003", "Massage Gun Lite", "Wellness", "Calma", 119.0, None, 19, 0,
     "Quiet percussion massager with four heads.", ("5 speeds", "4 heads", "3 h battery")),
    ("SKU-5004", "Sleep Sound Machine", "Wellness", "Calma", 49.0, None, 88, 250,
     "White noise and nature sounds with a sleep timer.", ("20 sounds", "Sleep timer", "Night light")),
    ("SKU-5005", "Weighted Blanket 7 kg", "Wellness", "Calma", 139.0, 169.0, 15, 220,
     "Breathable weighted blanket with a washable cover.", ("7 kg", "Cooling cover", "Machine washable cover")),
    ("SKU-6001", "Leather Laptop Sleeve 14\"", "Accessories", "Oakline", 69.0, None, 52, 30,
     "Full-grain leather sleeve with a felt lining.", ("Full-grain leather", "Felt lining", "Fits 13–14\"")),
    ("SKU-6002", "Braided USB-C Cable 2 m", "Accessories", "Oakline", 19.0, None, 400, 205,
     "100 W braided cable that survives a backpack.", ("100 W PD", "2 metres", "Braided nylon")),
    ("SKU-6003", "Wireless Charging Stand", "Accessories", "Sonora", 49.0, 59.0, 95, 215,
     "15 W stand that charges in portrait or landscape.", ("15 W Qi2", "Portrait or landscape", "Case friendly")),
    ("SKU-6004", "Canvas Tote Weekender", "Accessories", "Fieldwork", 99.0, None, 23, 40,
     "Waxed canvas weekender with a shoe pocket.", ("Waxed canvas", "38 litres", "Shoe pocket")),
    ("SKU-6005", "Travel Adapter Universal", "Accessories", "Northpeak", 35.0, None, 0, 200,
     "One adapter for 150 countries with 4 USB ports.", ("150+ countries", "2 × USB-C, 2 × USB-A", "Fused")),
]

_REVIEW_TITLES = {
    5: ["Absolutely love it", "Worth every penny", "Better than expected", "Five stars, no notes"],
    4: ["Really good", "Solid buy", "Happy with it", "Great with one small gripe"],
    3: ["It's fine", "Okay for the price", "Mixed feelings"],
    2: ["Not for me", "Disappointing"],
    1: ["Broke quickly", "Would not buy again"],
}
_REVIEW_BODIES = {
    5: "Exactly as described and the quality is excellent. I use it every day.",
    4: "Very good overall. Build quality is great; I'd change one minor detail.",
    3: "Does the job, but I expected a bit more for the price.",
    2: "Not what I hoped for. It works, but I'm thinking of returning it.",
    1: "Stopped working within a few weeks. Support was helpful, though.",
}
_REVIEWERS = ["Priya K.", "Sam O.", "Lena M.", "Diego R.", "Aisha B.", "Tom W.", "Mei L.", "Jonas H.", "Ana P.", "Chris D."]

COUPONS: list[dict[str, Any]] = [
    {"code": "WELCOME10", "kind": "percent", "value": 10, "min_subtotal": 0, "description": "10% off your order"},
    {"code": "SAVE20", "kind": "amount", "value": 20, "min_subtotal": 150, "description": "$20 off orders over $150"},
    {"code": "FREESHIP", "kind": "shipping", "value": 0, "min_subtotal": 0, "description": "Free standard or express shipping"},
]


def build_products() -> list[dict[str, Any]]:
    rng = random.Random(7)
    products = []
    for pid, name, category, brand, price, compare_at, stock, hue, summary, features in _PRODUCTS:
        products.append(
            {
                "id": pid,
                "name": name,
                "category": category,
                "brand": brand,
                "price": price,
                "compare_at_price": compare_at,
                "stock": stock,
                "hue": hue,
                "summary": summary,
                "features": list(features),
                "rating": 0.0,
                "review_count": 0,
                "sold_last_30d": rng.randint(5, 180),
            }
        )
    return products


def build_reviews(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A few reviews per product; product ratings are computed from them (logic.refresh_rating)."""
    rng = random.Random(11)
    today = date.today()
    reviews = []
    for product in products:
        for i in range(rng.randint(2, 5)):
            rating = rng.choices([5, 4, 3, 2, 1], weights=[45, 30, 13, 7, 5])[0]
            reviews.append(
                {
                    "id": f"REV-{len(reviews) + 1:04d}",
                    "product_id": product["id"],
                    "author": rng.choice(_REVIEWERS),
                    "user_id": None,
                    "rating": rating,
                    "title": rng.choice(_REVIEW_TITLES[rating]),
                    "body": _REVIEW_BODIES[rating],
                    "created_at": (today - timedelta(days=rng.randint(3, 300))).isoformat(),
                }
            )
    return reviews


def sample_history(today: date | None = None) -> list[dict[str, Any]]:
    """Orders every new shopper starts with: (days ago, status, [(sku, qty)], shipping method)."""
    return [
        {"days_ago": 41, "status": "delivered", "items": [("SKU-2003", 1), ("SKU-2004", 1)], "shipping_method": "standard"},
        {"days_ago": 12, "status": "delivered", "items": [("SKU-1004", 1)], "shipping_method": "express"},
        {"days_ago": 3, "status": "shipped", "items": [("SKU-3001", 1), ("SKU-4003", 2)], "shipping_method": "standard"},
    ]


SAMPLE_WISHLIST = ["SKU-2001", "SKU-1001", "SKU-5005"]

DEFAULT_SHOPPER = {
    "name": "Alex Morgan",
    "email": "alex.morgan@example.com",
    "address": {
        "full_name": "Alex Morgan",
        "address_line1": "742 Evergreen Terrace",
        "address_line2": "",
        "city": "Portland",
        "state": "OR",
        "postal_code": "97205",
        "country": "United States",
        "phone": "",
    },
}
