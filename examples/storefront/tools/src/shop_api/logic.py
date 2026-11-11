"""The store's business logic — the one implementation behind both the shop API (used by the
storefront) and the Relay tools (used by the assistant). Every rule lives here once: stock checks,
coupon rules, shipping, tax, cancellation and return windows, review eligibility.

Functions for the signed-in shopper read the user from ``current_user()`` (set per request by
``main.py``); catalog reads work without one.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
from typing import Any

from shop_api import db
from shop_api.seeds import CATEGORIES, DEFAULT_SHOPPER, SAMPLE_WISHLIST, sample_history

TAX_RATE = 0.0825
FREE_SHIPPING_FROM = 75.0
SHIPPING = {
    "standard": {"label": "Standard (3–5 business days)", "cost": 5.99, "min_days": 3, "max_days": 5},
    "express": {"label": "Express (1–2 business days)", "cost": 14.99, "min_days": 1, "max_days": 2},
}
PAYMENT_METHODS = {"card_on_file": "Card on file (Visa •••• 4242)", "pay_on_delivery": "Pay on delivery"}
COUNTRIES = ("United States", "Canada", "United Kingdom", "Germany", "India", "Australia")
ORDER_STATUSES = ("processing", "shipped", "delivered", "cancelled", "return_requested")
CANCEL_REASONS = ("changed_my_mind", "found_a_better_price", "ordered_by_mistake", "delivery_too_slow", "other")
RETURN_REASONS = ("damaged", "wrong_item", "not_as_described", "no_longer_needed", "other")
RETURN_WINDOW_DAYS = 30
LOW_STOCK = 10
MAX_QTY = 10

_user: ContextVar[str | None] = ContextVar("shop_user", default=None)


class NoUser(Exception):
    """A per-shopper call without a shopper (the tools service answers 401)."""


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
    _ensure_shopper(user_id)
    return user_id


# ---------------------------------------------------------------- helpers


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _money(value: float) -> float:
    return round(value + 1e-9, 2)


def _error(message: str, **fields: str) -> dict[str, Any]:
    return {"error": message, **({"fields": fields} if fields else {})}


def _stock_status(stock: int) -> str:
    return "out_of_stock" if stock <= 0 else "low_stock" if stock <= LOW_STOCK else "in_stock"


def _card(product: dict[str, Any]) -> dict[str, Any]:
    """The compact product shape used in lists."""
    compare = product.get("compare_at_price")
    on_sale = bool(compare and compare > product["price"])
    return {
        "id": product["id"],
        "name": product["name"],
        "category": product["category"],
        "brand": product["brand"],
        "price": product["price"],
        "compare_at_price": compare if on_sale else None,
        "on_sale": on_sale,
        "discount_pct": round((1 - product["price"] / compare) * 100) if on_sale else 0,
        "rating": product["rating"],
        "review_count": product["review_count"],
        "stock": product["stock"],
        "stock_status": _stock_status(product["stock"]),
        "hue": product["hue"],
        "summary": product["summary"],
    }


def _product(product_id: str) -> dict[str, Any] | None:
    return db.get("products", product_id.strip().upper()) if product_id else None


def _next_id(kind: str, prefix: str, start: int) -> str:
    numbers = [int(m.group(1)) for r in db.rows(kind) if (m := re.fullmatch(rf"{prefix}-(\d+)", r["id"]))]
    return f"{prefix}-{(max(numbers) + 1) if numbers else start}"


def _ensure_shopper(user_id: str) -> None:
    """A new shopper starts with a profile, a wishlist and a short order history (demo)."""
    if db.get("shoppers", user_id) is not None:
        return
    with db.transaction():
        if db.get("shoppers", user_id) is not None:
            return
        db.put("shoppers", {"id": user_id, **DEFAULT_SHOPPER, "created_at": _now().isoformat()})
        db.put("wishlists", {"id": user_id, "product_ids": list(SAMPLE_WISHLIST)})
        db.put("carts", {"id": user_id, "items": [], "coupon": None})
        for entry in sample_history():
            placed = _now() - timedelta(days=entry["days_ago"])
            lines = []
            for sku, qty in entry["items"]:
                product = db.get("products", sku)
                if product:
                    lines.append(_line(product, qty))
            order = _build_order(
                user_id,
                lines,
                coupon=None,
                shipping_method=entry["shipping_method"],
                address=dict(DEFAULT_SHOPPER["address"]),
                email=DEFAULT_SHOPPER["email"],
                payment_method="card_on_file",
                gift_note="",
                placed=placed,
            )
            order["status"] = entry["status"]
            if entry["status"] in ("shipped", "delivered"):
                order["shipped_at"] = (placed + timedelta(days=1)).isoformat()
                order["carrier"] = "UPS"
                order["tracking_number"] = f"1Z999AA1{order['id'][-4:]}{len(lines)}84"
            if entry["status"] == "delivered":
                order["delivered_at"] = (placed + timedelta(days=4)).isoformat()
            db.put("orders", order)


def _line(product: dict[str, Any], quantity: int) -> dict[str, Any]:
    return {
        "product_id": product["id"],
        "name": product["name"],
        "category": product["category"],
        "hue": product["hue"],
        "unit_price": product["price"],
        "quantity": quantity,
        "line_total": _money(product["price"] * quantity),
    }


# ---------------------------------------------------------------- catalog

SORTS = ("featured", "price", "rating", "newest", "best_selling", "discount", "name")


def list_products(
    *,
    query: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_rating: float | None = None,
    in_stock: bool | None = None,
    on_sale: bool | None = None,
    sort_by: str = "featured",
    sort_order: str | None = None,
    limit: int = 24,
    offset: int = 0,
) -> dict[str, Any]:
    cards = [_card(p) for p in db.rows("products")]
    if query and query.strip():
        words = query.lower().split()
        cards = [
            c
            for c in cards
            if all(w in f"{c['name']} {c['brand']} {c['category']} {c['summary']} {c['id']}".lower() for w in words)
        ]
    if category:
        cards = [c for c in cards if c["category"].lower() == category.lower()]
    if brand:
        cards = [c for c in cards if c["brand"].lower() == brand.lower()]
    if min_price is not None:
        cards = [c for c in cards if c["price"] >= min_price]
    if max_price is not None:
        cards = [c for c in cards if c["price"] <= max_price]
    if min_rating is not None:
        cards = [c for c in cards if c["rating"] >= min_rating]
    if in_stock:
        cards = [c for c in cards if c["stock"] > 0]
    if on_sale:
        cards = [c for c in cards if c["on_sale"]]
    sold = {p["id"]: p["sold_last_30d"] for p in db.rows("products")}
    key = {
        "price": lambda c: c["price"],
        "rating": lambda c: (c["rating"], c["review_count"]),
        "newest": lambda c: c["id"],
        "best_selling": lambda c: sold.get(c["id"], 0),
        "discount": lambda c: c["discount_pct"],
        "name": lambda c: c["name"].lower(),
    }.get(sort_by)
    if key is not None:
        descending = (sort_order or ("asc" if sort_by in ("price", "name") else "desc")) == "desc"
        cards.sort(key=key, reverse=descending)
    total = len(cards)
    limit = max(1, min(int(limit or 24), 60))
    offset = max(0, int(offset or 0))
    return {"products": cards[offset : offset + limit], "total": total, "offset": offset, "limit": limit}


def get_product(*, product_id: str) -> dict[str, Any]:
    product = _product(product_id)
    if product is None:
        return _error("not_found: no product with that id — find it with search_products")
    reviews = sorted(
        (r for r in db.rows("reviews") if r["product_id"] == product["id"]), key=lambda r: r["created_at"], reverse=True
    )
    related = [
        _card(p) for p in db.rows("products") if p["category"] == product["category"] and p["id"] != product["id"]
    ][:4]
    result: dict[str, Any] = {
        "product": {**_card(product), "features": product["features"], "sold_last_30d": product["sold_last_30d"]},
        "reviews": reviews[:6],
        "rating_breakdown": {str(n): sum(1 for r in reviews if r["rating"] == n) for n in range(5, 0, -1)},
        "related": related,
    }
    if _user.get():
        user_id = current_user()
        cart = _cart_doc(user_id)
        result["in_cart_quantity"] = next((i["quantity"] for i in cart["items"] if i["product_id"] == product["id"]), 0)
        result["in_wishlist"] = product["id"] in _wishlist_doc(user_id)["product_ids"]
        result["can_review"] = _can_review(user_id, product["id"])
    return result


def compare_products(*, product_ids: list[str]) -> dict[str, Any]:
    products = [p for pid in product_ids[:4] if (p := _product(str(pid)))]
    if len(products) < 2:
        return _error("Give at least two product ids to compare — find them with search_products")
    return {
        "products": [
            {**_card(p), "features": p["features"], "sold_last_30d": p["sold_last_30d"]} for p in products
        ]
    }


def list_categories() -> dict[str, Any]:
    products = db.rows("products")
    out = []
    for category in CATEGORIES:
        mine = [p for p in products if p["category"] == category]
        out.append(
            {
                "category": category,
                "product_count": len(mine),
                "min_price": min(p["price"] for p in mine),
                "max_price": max(p["price"] for p in mine),
                "on_sale": sum(1 for p in mine if _card(p)["on_sale"]),
                "brands": sorted({p["brand"] for p in mine}),
            }
        )
    return {"categories": out}


def aggregate_products(
    *,
    metric: str = "count",
    group_by: str = "category",
    category: str | None = None,
    brand: str | None = None,
    on_sale: bool | None = None,
) -> dict[str, Any]:
    cards = list_products(category=category, brand=brand, on_sale=on_sale, limit=60)["products"]
    groups: dict[str, list[dict[str, Any]]] = {}
    for c in cards:
        label = {
            "category": c["category"],
            "brand": c["brand"],
            "stock_status": c["stock_status"],
            "on_sale": "on sale" if c["on_sale"] else "full price",
            "rating": f"{int(c['rating'])}+ stars",
        }.get(group_by, c["category"])
        groups.setdefault(label, []).append(c)

    def value(items: list[dict[str, Any]]) -> float:
        if metric == "avg_price":
            return _money(sum(i["price"] for i in items) / len(items))
        if metric == "avg_rating":
            return round(sum(i["rating"] for i in items) / len(items), 2)
        if metric == "sum_stock":
            return sum(i["stock"] for i in items)
        return len(items)

    return {"metric": metric, "group_by": group_by, "groups": [{"group": k, "value": value(v)} for k, v in sorted(groups.items())]}


def get_top_products(
    *, rank_by: str = "best_selling", category: str | None = None, direction: str = "desc", limit: int = 5
) -> dict[str, Any]:
    sort = {"best_selling": "best_selling", "top_rated": "rating", "biggest_discount": "discount", "price": "price"}.get(
        rank_by, "best_selling"
    )
    result = list_products(category=category, sort_by=sort, sort_order=direction, limit=limit, on_sale=rank_by == "biggest_discount" or None)
    sold = {p["id"]: p["sold_last_30d"] for p in db.rows("products")}
    for c in result["products"]:
        c["sold_last_30d"] = sold.get(c["id"], 0)
    return {"rank_by": rank_by, "products": result["products"]}


def list_reviews(
    *, product_id: str | None = None, min_rating: int | None = None, max_rating: int | None = None, mine: bool | None = None, limit: int = 20
) -> dict[str, Any]:
    reviews = db.rows("reviews")
    if product_id:
        reviews = [r for r in reviews if r["product_id"] == product_id.strip().upper()]
    if min_rating is not None:
        reviews = [r for r in reviews if r["rating"] >= min_rating]
    if max_rating is not None:
        reviews = [r for r in reviews if r["rating"] <= max_rating]
    if mine:
        user_id = current_user()
        reviews = [r for r in reviews if r.get("user_id") == user_id]
    reviews.sort(key=lambda r: r["created_at"], reverse=True)
    return {"reviews": reviews[: max(1, limit)], "total": len(reviews)}


def get_recommendations(*, limit: int = 6) -> dict[str, Any]:
    """Picks from the categories the shopper buys, saves and has in the cart; skips what they own."""
    user_id = current_user()
    owned = {line["product_id"] for o in _orders(user_id) for line in o["items"]}
    in_cart = {i["product_id"] for i in _cart_doc(user_id)["items"]}
    wished = set(_wishlist_doc(user_id)["product_ids"])
    interest: dict[str, int] = {}
    for pid in owned | in_cart | wished:
        p = db.get("products", pid)
        if p:
            interest[p["category"]] = interest.get(p["category"], 0) + 1
    candidates = [_card(p) for p in db.rows("products") if p["id"] not in owned | in_cart and p["stock"] > 0]
    candidates.sort(key=lambda c: (interest.get(c["category"], 0), c["rating"]), reverse=True)
    picks = candidates[: max(1, limit)]
    for c in picks:
        c["reason"] = (
            f"You like {c['category']}" if interest.get(c["category"]) else "Highly rated"
        ) + (" · on sale" if c["on_sale"] else "")
    return {"products": picks}


# ---------------------------------------------------------------- cart


def _cart_doc(user_id: str) -> dict[str, Any]:
    return db.get("carts", user_id) or {"id": user_id, "items": [], "coupon": None}


def _coupon(code: str | None) -> dict[str, Any] | None:
    return db.get("coupons", code.strip().upper()) if code else None


def _quote(lines: list[dict[str, Any]], coupon: dict[str, Any] | None, shipping_method: str) -> dict[str, Any]:
    subtotal = _money(sum(line["line_total"] for line in lines))
    discount = 0.0
    coupon_note = None
    if coupon and subtotal >= coupon["min_subtotal"]:
        if coupon["kind"] == "percent":
            discount = _money(subtotal * coupon["value"] / 100)
        elif coupon["kind"] == "amount":
            discount = min(subtotal, float(coupon["value"]))
    elif coupon:
        coupon_note = f"{coupon['code']} needs a subtotal of ${coupon['min_subtotal']:.0f}"
    after_discount = _money(subtotal - discount)
    option = SHIPPING.get(shipping_method, SHIPPING["standard"])
    free = bool(coupon and coupon["kind"] == "shipping") or (shipping_method == "standard" and after_discount >= FREE_SHIPPING_FROM)
    shipping = 0.0 if not lines or free else option["cost"]
    tax = _money(after_discount * TAX_RATE)
    return {
        "subtotal": subtotal,
        "discount": _money(discount),
        "shipping": shipping,
        "shipping_method": shipping_method if shipping_method in SHIPPING else "standard",
        "tax": tax,
        "total": _money(after_discount + shipping + tax),
        "free_shipping_remaining": _money(max(0.0, FREE_SHIPPING_FROM - after_discount)) if not free else 0.0,
        "coupon_note": coupon_note,
    }


def get_cart(*, shipping_method: str = "standard") -> dict[str, Any]:
    user_id = current_user()
    cart = _cart_doc(user_id)
    lines, warnings = [], []
    for item in cart["items"]:
        product = db.get("products", item["product_id"])
        if product is None:
            continue
        line = {**_line(product, item["quantity"]), "stock": product["stock"], "stock_status": _stock_status(product["stock"])}
        if product["stock"] <= 0:
            warnings.append(f"{product['name']} is out of stock")
        elif item["quantity"] > product["stock"]:
            warnings.append(f"Only {product['stock']} of {product['name']} left")
        lines.append(line)
    coupon = _coupon(cart.get("coupon"))
    return {
        "items": lines,
        "item_count": sum(line["quantity"] for line in lines),
        "coupon": {"code": coupon["code"], "description": coupon["description"]} if coupon else None,
        "warnings": warnings,
        **_quote(lines, coupon, shipping_method),
    }


def get_shipping_options() -> dict[str, Any]:
    """Cost and delivery dates of each method for the current cart."""
    cart = get_cart()
    today = date.today()
    options = []
    for method, info in SHIPPING.items():
        quote = get_cart(shipping_method=method)
        options.append(
            {
                "method": method,
                "label": info["label"],
                "cost": quote["shipping"],
                "arrives_between": [(today + timedelta(days=info["min_days"])).isoformat(), (today + timedelta(days=info["max_days"])).isoformat()],
                "order_total": quote["total"],
            }
        )
    return {"options": options, "free_standard_shipping_from": FREE_SHIPPING_FROM, "free_shipping_remaining": cart["free_shipping_remaining"]}


def check_coupon(*, code: str) -> dict[str, Any]:
    coupon = _coupon(code)
    if coupon is None:
        return {"valid": False, "code": code.upper(), "message": "No such coupon code"}
    cart = get_cart()
    with_coupon = _quote(cart["items"], coupon, "standard")
    without = _quote(cart["items"], None, "standard")
    eligible = cart["subtotal"] >= coupon["min_subtotal"]
    return {
        "valid": True,
        "code": coupon["code"],
        "description": coupon["description"],
        "applies_to_current_cart": eligible,
        "saving": _money(without["total"] - with_coupon["total"]) if eligible else 0.0,
        "message": None if eligible else f"Needs a subtotal of ${coupon['min_subtotal']:.0f}",
    }


def add_to_cart(*, product_id: str, quantity: int = 1) -> dict[str, Any]:
    product = _product(product_id)
    if product is None:
        return _error("No product with that id — find it with search_products", product_id="unknown product")
    quantity = int(quantity or 1)
    if quantity < 1 or quantity > MAX_QTY:
        return _error(f"Quantity must be between 1 and {MAX_QTY}", quantity="out of range")
    user_id = current_user()
    with db.transaction():
        cart = _cart_doc(user_id)
        existing = next((i for i in cart["items"] if i["product_id"] == product["id"]), None)
        new_qty = (existing["quantity"] if existing else 0) + quantity
        if product["stock"] <= 0:
            return _error(f"{product['name']} is out of stock")
        if new_qty > min(product["stock"], MAX_QTY):
            return _error(f"Only {min(product['stock'], MAX_QTY)} of {product['name']} can be in the cart", quantity="too many")
        if existing:
            existing["quantity"] = new_qty
        else:
            cart["items"].append({"product_id": product["id"], "quantity": quantity, "added_at": _now().isoformat()})
        db.put("carts", cart)
    return {"added": {"product_id": product["id"], "name": product["name"], "quantity": quantity}, "cart": get_cart()}


def update_cart_item(*, product_id: str, quantity: int) -> dict[str, Any]:
    product = _product(product_id)
    user_id = current_user()
    quantity = int(quantity)
    with db.transaction():
        cart = _cart_doc(user_id)
        item = next((i for i in cart["items"] if product and i["product_id"] == product["id"]), None)
        if item is None or product is None:
            return _error("That product is not in the cart", product_id="not in cart")
        if quantity < 1 or quantity > min(MAX_QTY, max(product["stock"], 1)):
            return _error(f"Quantity must be between 1 and {min(MAX_QTY, max(product['stock'], 1))}", quantity="out of range")
        item["quantity"] = quantity
        db.put("carts", cart)
    return {"updated": {"product_id": product["id"], "name": product["name"], "quantity": quantity}, "cart": get_cart()}


def remove_from_cart(*, product_id: str) -> dict[str, Any]:
    user_id = current_user()
    pid = product_id.strip().upper()
    with db.transaction():
        cart = _cart_doc(user_id)
        if not any(i["product_id"] == pid for i in cart["items"]):
            return _error("That product is not in the cart", product_id="not in cart")
        cart["items"] = [i for i in cart["items"] if i["product_id"] != pid]
        db.put("carts", cart)
    return {"removed": pid, "cart": get_cart()}


def clear_cart() -> dict[str, Any]:
    user_id = current_user()
    db.put("carts", {"id": user_id, "items": [], "coupon": None})
    return {"cleared": True, "cart": get_cart()}


def apply_coupon(*, code: str) -> dict[str, Any]:
    coupon = _coupon(code)
    if coupon is None:
        return _error("That coupon code doesn't exist", code="unknown code")
    user_id = current_user()
    with db.transaction():
        cart = _cart_doc(user_id)
        cart["coupon"] = coupon["code"]
        db.put("carts", cart)
    result = get_cart()
    return {"applied": coupon["code"], "note": result["coupon_note"], "cart": result}


def remove_coupon() -> dict[str, Any]:
    user_id = current_user()
    with db.transaction():
        cart = _cart_doc(user_id)
        cart["coupon"] = None
        db.put("carts", cart)
    return {"removed": True, "cart": get_cart()}


# ---------------------------------------------------------------- checkout and orders


def _build_order(
    user_id: str,
    lines: list[dict[str, Any]],
    *,
    coupon: dict[str, Any] | None,
    shipping_method: str,
    address: dict[str, Any],
    email: str,
    payment_method: str,
    gift_note: str,
    placed: datetime,
) -> dict[str, Any]:
    quote = _quote(lines, coupon, shipping_method)
    info = SHIPPING[shipping_method]
    return {
        "id": _next_id("orders", "ORD", 10421),
        "user_id": user_id,
        "status": "processing",
        "placed_at": placed.isoformat(),
        "items": lines,
        "coupon": coupon["code"] if coupon else None,
        **{k: quote[k] for k in ("subtotal", "discount", "shipping", "tax", "total")},
        "shipping_method": shipping_method,
        "estimated_delivery": [
            (placed.date() + timedelta(days=info["min_days"])).isoformat(),
            (placed.date() + timedelta(days=info["max_days"])).isoformat(),
        ],
        "shipping_address": address,
        "email": email,
        "payment_method": payment_method,
        "gift_note": gift_note or "",
        "carrier": None,
        "tracking_number": None,
        "shipped_at": None,
        "delivered_at": None,
        "cancelled_at": None,
        "cancel_reason": None,
        "return": None,
    }


_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def place_order(
    *,
    full_name: str,
    email: str,
    address_line1: str,
    city: str,
    state: str,
    postal_code: str,
    country: str,
    shipping_method: str = "standard",
    payment_method: str = "card_on_file",
    address_line2: str | None = None,
    phone: str | None = None,
    gift_note: str | None = None,
) -> dict[str, Any]:
    """Checkout: validates the address, re-checks stock, charges the method on file, empties the cart."""
    fields: dict[str, str] = {}
    for name, value in (("full_name", full_name), ("address_line1", address_line1), ("city", city), ("state", state), ("postal_code", postal_code)):
        if not str(value or "").strip():
            fields[name] = "required"
    if not _EMAIL.fullmatch(str(email or "").strip()):
        fields["email"] = "not a valid email address"
    if country not in COUNTRIES:
        fields["country"] = f"must be one of {', '.join(COUNTRIES)}"
    if shipping_method not in SHIPPING:
        fields["shipping_method"] = "standard or express"
    if payment_method not in PAYMENT_METHODS:
        fields["payment_method"] = "card_on_file or pay_on_delivery"
    if gift_note and len(gift_note) > 300:
        fields["gift_note"] = "at most 300 characters"
    if fields:
        return _error("Please fix the highlighted fields", **fields)
    user_id = current_user()
    with db.transaction():
        cart = _cart_doc(user_id)
        if not cart["items"]:
            return _error("The cart is empty — add something first")
        lines, problems = [], []
        for item in cart["items"]:
            product = db.get("products", item["product_id"])
            if product is None or product["stock"] < item["quantity"]:
                left = product["stock"] if product else 0
                problems.append(f"{product['name'] if product else item['product_id']}: only {left} left")
                continue
            lines.append(_line(product, item["quantity"]))
        if problems:
            return _error("Some items are no longer available: " + "; ".join(problems) + ". Update the cart and try again.")
        address = {
            "full_name": full_name.strip(),
            "address_line1": address_line1.strip(),
            "address_line2": (address_line2 or "").strip(),
            "city": city.strip(),
            "state": state.strip(),
            "postal_code": postal_code.strip(),
            "country": country,
            "phone": (phone or "").strip(),
        }
        order = _build_order(
            user_id,
            lines,
            coupon=_coupon(cart.get("coupon")),
            shipping_method=shipping_method,
            address=address,
            email=email.strip(),
            payment_method=payment_method,
            gift_note=gift_note or "",
            placed=_now(),
        )
        for line in lines:
            product = db.get("products", line["product_id"])
            assert product is not None
            product["stock"] -= line["quantity"]
            product["sold_last_30d"] += line["quantity"]
            db.put("products", product)
        db.put("orders", order)
        db.put("carts", {"id": user_id, "items": [], "coupon": None})
        shopper = db.get("shoppers", user_id) or {}
        db.put("shoppers", {**shopper, "id": user_id, "address": address, "email": email.strip(), "name": full_name.strip()})
    return {"order": _order_view(order)}


def _orders(user_id: str) -> list[dict[str, Any]]:
    return [o for o in db.rows("orders") if o["user_id"] == user_id]


def _order_view(order: dict[str, Any]) -> dict[str, Any]:
    placed = datetime.fromisoformat(order["placed_at"])
    delivered = datetime.fromisoformat(order["delivered_at"]) if order.get("delivered_at") else None
    return_until = (delivered + timedelta(days=RETURN_WINDOW_DAYS)).date().isoformat() if delivered else None
    timeline = [{"status": "placed", "at": order["placed_at"]}]
    if order.get("shipped_at"):
        timeline.append({"status": "shipped", "at": order["shipped_at"], "carrier": order.get("carrier"), "tracking_number": order.get("tracking_number")})
    if order.get("delivered_at"):
        timeline.append({"status": "delivered", "at": order["delivered_at"]})
    if order.get("cancelled_at"):
        timeline.append({"status": "cancelled", "at": order["cancelled_at"], "reason": order.get("cancel_reason")})
    if order.get("return"):
        timeline.append({"status": "return_requested", "at": order["return"]["requested_at"], "reason": order["return"]["reason"]})
    return {
        **{k: v for k, v in order.items() if k != "user_id"},
        "item_count": sum(line["quantity"] for line in order["items"]),
        "placed_date": placed.date().isoformat(),
        "timeline": timeline,
        "can_cancel": order["status"] == "processing",
        "can_change_address": order["status"] == "processing",
        "can_return": order["status"] == "delivered" and delivered is not None and _now() - delivered <= timedelta(days=RETURN_WINDOW_DAYS),
        "return_window_ends": return_until,
        "payment_label": PAYMENT_METHODS.get(order["payment_method"], order["payment_method"]),
    }


def list_orders(
    *,
    status: str | None = None,
    placed_from: str | None = None,
    placed_to: str | None = None,
    min_total: float | None = None,
    max_total: float | None = None,
    product_id: str | None = None,
    sort_by: str = "placed_at",
    sort_order: str = "desc",
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    orders = [_order_view(o) for o in _orders(current_user())]
    if status:
        orders = [o for o in orders if o["status"] == status]
    if placed_from:
        orders = [o for o in orders if o["placed_date"] >= placed_from]
    if placed_to:
        orders = [o for o in orders if o["placed_date"] <= placed_to]
    if min_total is not None:
        orders = [o for o in orders if o["total"] >= min_total]
    if max_total is not None:
        orders = [o for o in orders if o["total"] <= max_total]
    if product_id:
        orders = [o for o in orders if any(line["product_id"] == product_id.upper() for line in o["items"])]
    orders.sort(key=lambda o: o["total"] if sort_by == "total" else o["placed_at"], reverse=sort_order != "asc")
    total = len(orders)
    summary = [
        {k: o[k] for k in ("id", "status", "placed_date", "total", "item_count", "estimated_delivery", "can_cancel", "can_return")}
        | {"items": [f"{line['quantity']} × {line['name']}" for line in o["items"]]}
        for o in orders[offset : offset + max(1, limit)]
    ]
    return {"orders": summary, "total": total}


def get_order(*, order_id: str) -> dict[str, Any]:
    order = db.get("orders", order_id.strip().upper())
    if order is None or order["user_id"] != current_user():
        return _error("not_found: no order with that id — list them with list_orders")
    return {"order": _order_view(order)}


def aggregate_orders(*, metric: str = "count", group_by: str = "status", placed_from: str | None = None, placed_to: str | None = None) -> dict[str, Any]:
    orders = [_order_view(o) for o in _orders(current_user()) if o["status"] != "cancelled" or group_by == "status"]
    if placed_from:
        orders = [o for o in orders if o["placed_date"] >= placed_from]
    if placed_to:
        orders = [o for o in orders if o["placed_date"] <= placed_to]
    groups: dict[str, float] = {}
    counts: dict[str, int] = {}
    for o in orders:
        if group_by == "category":
            for line in o["items"]:
                groups[line["category"]] = groups.get(line["category"], 0) + (line["line_total"] if metric != "count" else 1)
                counts[line["category"]] = counts.get(line["category"], 0) + 1
            continue
        key = o["placed_date"][:7] if group_by == "month" else o["status"]
        groups[key] = groups.get(key, 0) + (o["total"] if metric != "count" else 1)
        counts[key] = counts.get(key, 0) + 1
    if metric == "avg_total":
        groups = {k: _money(v / counts[k]) for k, v in groups.items()}
    rounded = (lambda v: int(v)) if metric == "count" else _money
    return {"metric": metric, "group_by": group_by, "groups": [{"group": k, "value": rounded(v)} for k, v in sorted(groups.items())]}


def get_spending_over_time(*, months: int = 6) -> dict[str, Any]:
    """Spend per month (cancelled orders excluded), oldest first — ready for a chart."""
    orders = [o for o in _orders(current_user()) if o["status"] != "cancelled"]
    today = date.today().replace(day=1)
    points = []
    for back in range(max(1, min(months, 24)) - 1, -1, -1):
        y, m = today.year, today.month - back
        while m <= 0:
            y, m = y - 1, m + 12
        key = f"{y:04d}-{m:02d}"
        mine = [o for o in orders if o["placed_at"][:7] == key]
        points.append({"month": key, "spend": _money(sum(o["total"] for o in mine)), "orders": len(mine)})
    return {"points": points, "total_spend": _money(sum(p["spend"] for p in points))}


def _own_order(order_id: str) -> dict[str, Any] | None:
    order = db.get("orders", order_id.strip().upper())
    return order if order and order["user_id"] == current_user() else None


def cancel_order(*, order_id: str, reason: str = "changed_my_mind") -> dict[str, Any]:
    if reason not in CANCEL_REASONS:
        return _error("Pick a reason from the list", reason=f"one of {', '.join(CANCEL_REASONS)}")
    with db.transaction():
        order = _own_order(order_id)
        if order is None:
            return _error("No order with that id", order_id="unknown order")
        if order["status"] != "processing":
            return _error(f"{order['id']} is {order['status']} and can no longer be cancelled; a delivered order can be returned instead")
        order["status"] = "cancelled"
        order["cancelled_at"] = _now().isoformat()
        order["cancel_reason"] = reason
        for line in order["items"]:
            product = db.get("products", line["product_id"])
            if product:
                product["stock"] += line["quantity"]
                db.put("products", product)
        db.put("orders", order)
    return {"order": _order_view(order), "refund": order["total"] if order["payment_method"] == "card_on_file" else 0.0}


def request_return(*, order_id: str, reason: str, notes: str | None = None) -> dict[str, Any]:
    fields = {}
    if reason not in RETURN_REASONS:
        fields["reason"] = f"one of {', '.join(RETURN_REASONS)}"
    if notes and len(notes) > 500:
        fields["notes"] = "at most 500 characters"
    if fields:
        return _error("Please fix the highlighted fields", **fields)
    with db.transaction():
        order = _own_order(order_id)
        if order is None:
            return _error("No order with that id", order_id="unknown order")
        view = _order_view(order)
        if not view["can_return"]:
            why = "it hasn't been delivered" if order["status"] != "delivered" else f"the {RETURN_WINDOW_DAYS}-day return window has closed"
            return _error(f"{order['id']} can't be returned: {why}")
        order["status"] = "return_requested"
        order["return"] = {
            "reason": reason,
            "notes": notes or "",
            "requested_at": _now().isoformat(),
            "label": f"RMA-{order['id'][4:]}",
            "refund_amount": order["total"],
        }
        db.put("orders", order)
    return {"order": _order_view(order), "return_label": order["return"]["label"]}


def update_order_address(
    *,
    order_id: str,
    full_name: str | None = None,
    address_line1: str | None = None,
    address_line2: str | None = None,
    city: str | None = None,
    state: str | None = None,
    postal_code: str | None = None,
    country: str | None = None,
    phone: str | None = None,
) -> dict[str, Any]:
    if country is not None and country not in COUNTRIES:
        return _error("Unsupported country", country=f"one of {', '.join(COUNTRIES)}")
    with db.transaction():
        order = _own_order(order_id)
        if order is None:
            return _error("No order with that id", order_id="unknown order")
        if order["status"] != "processing":
            return _error(f"{order['id']} is {order['status']}; only orders that haven't shipped can be re-addressed")
        changes = {
            k: v.strip()
            for k, v in dict(
                full_name=full_name, address_line1=address_line1, address_line2=address_line2, city=city,
                state=state, postal_code=postal_code, country=country, phone=phone,
            ).items()
            if v is not None
        }
        if not changes:
            return _error("Nothing to change — give at least one address field")
        if any(not changes.get(k, "x") for k in ("full_name", "address_line1", "city", "state", "postal_code")):
            return _error("Required address fields can't be empty")
        order["shipping_address"] = {**order["shipping_address"], **changes}
        db.put("orders", order)
    return {"order": _order_view(order), "changed": sorted(changes)}


def reorder(*, order_id: str) -> dict[str, Any]:
    """Buy again: adds the order's items (still in stock) to the cart."""
    order = _own_order(order_id)
    if order is None:
        return _error("No order with that id", order_id="unknown order")
    added, skipped = [], []
    for line in order["items"]:
        result = add_to_cart(product_id=line["product_id"], quantity=line["quantity"])
        (skipped if "error" in result else added).append(line["name"] if "error" not in result else f"{line['name']} ({result['error']})")
    return {"added": added, "skipped": skipped, "cart": get_cart()}


# ---------------------------------------------------------------- wishlist and reviews


def _wishlist_doc(user_id: str) -> dict[str, Any]:
    return db.get("wishlists", user_id) or {"id": user_id, "product_ids": []}


def list_wishlist() -> dict[str, Any]:
    ids = _wishlist_doc(current_user())["product_ids"]
    return {"products": [_card(p) for pid in ids if (p := db.get("products", pid))], "total": len(ids)}


def add_to_wishlist(*, product_id: str) -> dict[str, Any]:
    product = _product(product_id)
    if product is None:
        return _error("No product with that id", product_id="unknown product")
    user_id = current_user()
    with db.transaction():
        wishlist = _wishlist_doc(user_id)
        if product["id"] not in wishlist["product_ids"]:
            wishlist["product_ids"].append(product["id"])
            db.put("wishlists", wishlist)
    return {"saved": product["name"], "wishlist": list_wishlist()}


def remove_from_wishlist(*, product_id: str) -> dict[str, Any]:
    user_id = current_user()
    pid = product_id.strip().upper()
    with db.transaction():
        wishlist = _wishlist_doc(user_id)
        if pid not in wishlist["product_ids"]:
            return _error("That product is not on the wishlist", product_id="not saved")
        wishlist["product_ids"].remove(pid)
        db.put("wishlists", wishlist)
    return {"removed": pid, "wishlist": list_wishlist()}


def _can_review(user_id: str, product_id: str) -> bool:
    bought = any(
        o["status"] in ("delivered", "return_requested") and any(line["product_id"] == product_id for line in o["items"])
        for o in _orders(user_id)
    )
    already = any(r.get("user_id") == user_id and r["product_id"] == product_id for r in db.rows("reviews"))
    return bought and not already


def write_review(*, product_id: str, rating: int, title: str, body: str) -> dict[str, Any]:
    product = _product(product_id)
    fields = {}
    if product is None:
        fields["product_id"] = "unknown product"
    if not isinstance(rating, int) or not 1 <= rating <= 5:
        fields["rating"] = "1 to 5 stars"
    if not (title or "").strip() or len(title) > 120:
        fields["title"] = "1–120 characters"
    if len((body or "").strip()) < 10 or len(body) > 2000:
        fields["body"] = "10–2000 characters"
    if fields:
        return _error("Please fix the highlighted fields", **fields)
    assert product is not None
    user_id = current_user()
    if not _can_review(user_id, product["id"]):
        return _error("You can review a product once, after it has been delivered to you")
    shopper = db.get("shoppers", user_id) or {}
    with db.transaction():
        review = {
            "id": _next_id("reviews", "REV", 1),
            "product_id": product["id"],
            "author": shopper.get("name", "Shopper").split(" ")[0] + " (you)",
            "user_id": user_id,
            "rating": rating,
            "title": title.strip(),
            "body": body.strip(),
            "created_at": date.today().isoformat(),
        }
        db.put("reviews", review)
        ratings = [r["rating"] for r in db.rows("reviews") if r["product_id"] == product["id"]]
        product["rating"] = round(sum(ratings) / len(ratings), 1)
        product["review_count"] = len(ratings)
        db.put("products", product)
    return {"review": review, "product_rating": product["rating"]}


# ---------------------------------------------------------------- cross-entity


def get_my_context() -> dict[str, Any]:
    user_id = current_user()
    shopper = db.get("shoppers", user_id) or {}
    orders = [_order_view(o) for o in _orders(user_id)]
    return {
        "shopper": {"name": shopper.get("name"), "email": shopper.get("email"), "default_address": shopper.get("address")},
        "cart_items": get_cart()["item_count"],
        "wishlist_items": len(_wishlist_doc(user_id)["product_ids"]),
        "orders": len(orders),
        "open_orders": sum(1 for o in orders if o["status"] in ("processing", "shipped")),
        "lifetime_spend": _money(sum(o["total"] for o in orders if o["status"] != "cancelled")),
        "payment_methods": PAYMENT_METHODS,
    }


def get_overview() -> dict[str, Any]:
    cart = get_cart()
    orders = list_orders(limit=5)["orders"]
    return {
        "cart": {k: cart[k] for k in ("item_count", "subtotal", "total", "free_shipping_remaining")},
        "recent_orders": orders,
        "on_sale_count": list_products(on_sale=True, limit=60)["total"],
        "attention": list_attention_items()["items"][:5],
    }


def list_attention_items() -> dict[str, Any]:
    user_id = current_user()
    items: list[dict[str, Any]] = []
    for o in (_order_view(o) for o in _orders(user_id)):
        if o["status"] == "shipped":
            items.append({"type": "order_in_transit", "id": o["id"], "message": f"{o['id']} is on its way, arriving by {o['estimated_delivery'][1]}"})
        if o["status"] == "processing":
            items.append({"type": "order_processing", "id": o["id"], "message": f"{o['id']} hasn't shipped yet — it can still be cancelled or its address changed"})
        if o["can_return"] and o["return_window_ends"]:
            items.append({"type": "return_window", "id": o["id"], "message": f"{o['id']} can be returned until {o['return_window_ends']}"})
        for line in o["items"] if o["status"] == "delivered" else []:
            if _can_review(user_id, line["product_id"]):
                items.append({"type": "review_pending", "id": line["product_id"], "message": f"How is your {line['name']}? You can review it"})
    cart = get_cart()
    for warning in cart["warnings"]:
        items.append({"type": "cart_stock", "id": None, "message": warning})
    for c in list_wishlist()["products"]:
        if c["on_sale"]:
            items.append({"type": "wishlist_sale", "id": c["id"], "message": f"{c['name']} from your wishlist is {c['discount_pct']}% off"})
        if c["stock_status"] == "low_stock":
            items.append({"type": "wishlist_low_stock", "id": c["id"], "message": f"Only {c['stock']} {c['name']} left"})
    return {"items": items, "total": len(items)}


def search_all(*, query: str) -> dict[str, Any]:
    q = query.strip().lower()
    hits = [{"type": "product", "id": c["id"], "title": c["name"]} for c in list_products(query=query, limit=8)["products"]]
    if _user.get():
        for o in _orders(current_user()):
            if q in o["id"].lower() or any(q in line["name"].lower() for line in o["items"]):
                hits.append({"type": "order", "id": o["id"], "title": f"Order {o['id']} ({o['status']})"})
    hits += [{"type": "category", "id": c, "title": c} for c in CATEGORIES if q in c.lower()]
    return {"hits": hits[:15], "total": len(hits)}


def describe_data() -> dict[str, Any]:
    return {
        "store": "Oakline — home, office, kitchen, outdoor and wellness goods. Prices in USD.",
        "categories": list(CATEGORIES),
        "brands": sorted({p["brand"] for p in db.rows("products")}),
        "product_sorts": list(SORTS),
        "order_statuses": list(ORDER_STATUSES),
        "shipping_methods": {k: v["label"] for k, v in SHIPPING.items()},
        "free_standard_shipping_from": FREE_SHIPPING_FROM,
        "tax_rate": TAX_RATE,
        "payment_methods": PAYMENT_METHODS,
        "countries": list(COUNTRIES),
        "cancel_reasons": list(CANCEL_REASONS),
        "return_reasons": list(RETURN_REASONS),
        "return_window_days": RETURN_WINDOW_DAYS,
        "coupons": "Codes are entered by the shopper; check one with check_coupon.",
    }
