"""Every Relay tool, defined once: function, description, JSON schema, classification.

``GET /tools`` and ``POST /tools/{name}`` are both generated from ``TOOL_SPECS``. Writes are
``side_effecting``: the assistant can only propose them, and they run after the shopper approves
(or submits a form bound to them). The inventory behind this catalog is in ``../relay-tools.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from shop_api import logic
from shop_api.seeds import BRANDS, CATEGORIES


@dataclass(frozen=True)
class ToolSpec:
    fn: Callable[..., dict[str, Any]]
    description: str
    properties: dict[str, Any] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    classification: str = "read_only"
    # Needs a signed-in shopper (X-Relay-User); the service answers 401 without one.
    per_user: bool = True

    @property
    def input_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {"type": "object", "properties": self.properties}
        if self.required:
            schema["required"] = list(self.required)
        return schema


SE = "side_effecting"
PRODUCT_ID = {"type": "string", "minLength": 1, "title": "Product", "description": "Product id like SKU-1001 — find it with search_products"}
ORDER_ID = {"type": "string", "minLength": 1, "title": "Order", "description": "Order id like ORD-10423 — find it with list_orders"}
DATE = {"type": "string", "format": "date"}
SORT_ORDER = {"type": "string", "enum": ["asc", "desc"]}
CATEGORY = {"type": "string", "enum": list(CATEGORIES)}
BRAND = {"type": "string", "enum": list(BRANDS)}
ADDRESS = {
    "full_name": {"type": "string", "minLength": 1, "title": "Full name", "maxLength": 80},
    "address_line1": {"type": "string", "minLength": 1, "title": "Address", "description": "Street and number"},
    "address_line2": {"type": "string", "title": "Apartment, suite (optional)"},
    "city": {"type": "string", "minLength": 1, "title": "City"},
    "state": {"type": "string", "minLength": 1, "title": "State / province"},
    "postal_code": {"type": "string", "minLength": 1, "title": "Postal code"},
    "country": {"type": "string", "enum": list(logic.COUNTRIES), "title": "Country"},
    "phone": {"type": "string", "title": "Phone (optional)", "description": "For delivery questions"},
}

TOOL_SPECS: dict[str, ToolSpec] = {
    # ------------------------------------------------------------ catalog (reads)
    "search_products": ToolSpec(
        logic.list_products,
        "Search and filter the catalog. Free-text `query` over name, brand, category and summary; filters for "
        "category, brand, price range (USD), minimum rating, in stock and on sale; sort_by featured|price|rating|"
        "newest|best_selling|discount|name. Returns compact products (id, price, sale price, rating, stock status) "
        "and `total`. With no arguments it lists the whole catalog. To show results on the store's own catalog page "
        "prefer the FILTER_PRODUCTS screen action.",
        {
            "query": {"type": "string"},
            "category": CATEGORY,
            "brand": BRAND,
            "min_price": {"type": "number", "minimum": 0},
            "max_price": {"type": "number", "minimum": 0},
            "min_rating": {"type": "number", "minimum": 0, "description": "0–5 stars"},
            "in_stock": {"type": "boolean"},
            "on_sale": {"type": "boolean"},
            "sort_by": {"type": "string", "enum": list(logic.SORTS)},
            "sort_order": SORT_ORDER,
            "limit": {"type": "integer", "minimum": 1, "description": "Default 24, max 60"},
            "offset": {"type": "integer", "minimum": 0},
        },
        per_user=False,
    ),
    "get_product": ToolSpec(
        logic.get_product,
        "One product with features, stock, rating breakdown, the latest reviews and related products; for the "
        "shopper also how many are in their cart, whether it is on their wishlist and whether they can review it.",
        {"product_id": PRODUCT_ID},
        ("product_id",),
        per_user=False,
    ),
    "compare_products": ToolSpec(
        logic.compare_products,
        "Two to four products side by side (price, sale, rating, stock, features) — for a comparison surface.",
        {"product_ids": {"type": "array", "items": {"type": "string"}, "description": "2–4 product ids"}},
        ("product_ids",),
        per_user=False,
    ),
    "list_categories": ToolSpec(
        logic.list_categories,
        "Every category with its product count, price range, number on sale and brands.",
        per_user=False,
    ),
    "aggregate_products": ToolSpec(
        logic.aggregate_products,
        "Catalog statistics: metric count|avg_price|avg_rating|sum_stock grouped by category|brand|stock_status|"
        "on_sale|rating, optionally filtered by category, brand or on_sale. Feeds charts.",
        {
            "metric": {"type": "string", "enum": ["count", "avg_price", "avg_rating", "sum_stock"]},
            "group_by": {"type": "string", "enum": ["category", "brand", "stock_status", "on_sale", "rating"]},
            "category": CATEGORY,
            "brand": BRAND,
            "on_sale": {"type": "boolean"},
        },
        per_user=False,
    ),
    "get_top_products": ToolSpec(
        logic.get_top_products,
        "Rankings: best_selling (units sold in the last 30 days), top_rated, biggest_discount or price; optional "
        "category; direction desc (default) or asc; limit (default 5).",
        {
            "rank_by": {"type": "string", "enum": ["best_selling", "top_rated", "biggest_discount", "price"]},
            "category": CATEGORY,
            "direction": SORT_ORDER,
            "limit": {"type": "integer", "minimum": 1},
        },
        per_user=False,
    ),
    "list_reviews": ToolSpec(
        logic.list_reviews,
        "Product reviews, newest first: filter by product_id, min_rating / max_rating (1–5), or mine=true for the "
        "shopper's own reviews.",
        {
            "product_id": PRODUCT_ID,
            "min_rating": {"type": "integer", "minimum": 1},
            "max_rating": {"type": "integer", "minimum": 1},
            "mine": {"type": "boolean"},
            "limit": {"type": "integer", "minimum": 1},
        },
        per_user=False,
    ),
    "get_recommendations": ToolSpec(
        logic.get_recommendations,
        "Products picked for this shopper from the categories they buy, save and have in the cart (excludes what "
        "they already own), each with a short reason.",
        {"limit": {"type": "integer", "minimum": 1}},
    ),
    # ------------------------------------------------------------ cart
    "get_cart": ToolSpec(
        logic.get_cart,
        "The shopper's cart: lines with unit price, quantity and stock, coupon, and the totals (subtotal, discount, "
        "shipping for the chosen method, 8.25% tax, total) plus how much more is needed for free shipping and any "
        "stock warnings.",
        {"shipping_method": {"type": "string", "enum": list(logic.SHIPPING)}},
    ),
    "get_shipping_options": ToolSpec(
        logic.get_shipping_options,
        "Shipping methods for the current cart with cost, delivery date range and resulting order total.",
    ),
    "check_coupon": ToolSpec(
        logic.check_coupon,
        "Checks a coupon code without applying it: whether it exists, what it does, whether the current cart "
        "qualifies and how much it would save.",
        {"code": {"type": "string", "minLength": 1}},
        ("code",),
    ),
    "add_to_cart": ToolSpec(
        logic.add_to_cart,
        "Adds a product to the shopper's cart (or raises its quantity). Checks stock; at most 10 of one product.",
        {"product_id": PRODUCT_ID, "quantity": {"type": "integer", "minimum": 1, "title": "Quantity", "description": "Defaults to 1"}},
        ("product_id",),
        SE,
    ),
    "update_cart_item": ToolSpec(
        logic.update_cart_item,
        "Sets the quantity of a product already in the cart (1–10, no more than in stock). To remove it use "
        "remove_from_cart.",
        {"product_id": PRODUCT_ID, "quantity": {"type": "integer", "minimum": 1, "title": "Quantity"}},
        ("product_id", "quantity"),
        SE,
    ),
    "remove_from_cart": ToolSpec(
        logic.remove_from_cart, "Removes a product from the cart.", {"product_id": PRODUCT_ID}, ("product_id",), SE
    ),
    "clear_cart": ToolSpec(logic.clear_cart, "Empties the cart and removes its coupon.", classification=SE),
    "apply_coupon": ToolSpec(
        logic.apply_coupon,
        "Applies a coupon code to the cart (replaces any other coupon). Use check_coupon first to see the saving.",
        {"code": {"type": "string", "minLength": 1, "title": "Coupon code"}},
        ("code",),
        SE,
    ),
    "remove_coupon": ToolSpec(logic.remove_coupon, "Removes the coupon from the cart.", classification=SE),
    # ------------------------------------------------------------ checkout and orders
    "place_order": ToolSpec(
        logic.place_order,
        "Checkout: places an order for everything in the cart, shipped to the given address, paid with the chosen "
        "method, and empties the cart. Re-checks stock and applies the cart's coupon. Prefill the address from "
        "get_my_context's default address. Show it as a form so the shopper reviews the address before paying.",
        {
            **{k: ADDRESS[k] for k in ("full_name", "address_line1", "address_line2", "city", "state", "postal_code", "country")},
            "email": {"type": "string", "format": "email", "title": "Email", "description": "For the order confirmation"},
            "phone": ADDRESS["phone"],
            "shipping_method": {"type": "string", "enum": list(logic.SHIPPING), "title": "Shipping", "description": "standard (free over $75) or express"},
            "payment_method": {"type": "string", "enum": list(logic.PAYMENT_METHODS), "title": "Payment", "description": "card_on_file (Visa •••• 4242) or pay_on_delivery"},
            "gift_note": {"type": "string", "maxLength": 300, "title": "Gift note (optional)", "description": "The complete gift message to print on the packing slip — write the full note"},
        },
        ("full_name", "email", "address_line1", "city", "state", "postal_code", "country"),
        SE,
    ),
    "list_orders": ToolSpec(
        logic.list_orders,
        "The shopper's orders, newest first: filter by status (processing|shipped|delivered|cancelled|"
        "return_requested), placed_from / placed_to dates, min_total / max_total (USD) or a product_id they "
        "contain; sort_by placed_at|total. Returns items, totals, delivery estimate, can_cancel, can_return and `total`.",
        {
            "status": {"type": "string", "enum": list(logic.ORDER_STATUSES)},
            "placed_from": DATE,
            "placed_to": DATE,
            "min_total": {"type": "number", "minimum": 0},
            "max_total": {"type": "number", "minimum": 0},
            "product_id": {"type": "string"},
            "sort_by": {"type": "string", "enum": ["placed_at", "total"]},
            "sort_order": SORT_ORDER,
            "limit": {"type": "integer", "minimum": 1},
            "offset": {"type": "integer", "minimum": 0},
        },
    ),
    "get_order": ToolSpec(
        logic.get_order,
        "One order with line items, totals, shipping address, payment, tracking timeline (carrier, tracking "
        "number), delivery estimate, and whether it can be cancelled, re-addressed or returned (and until when).",
        {"order_id": ORDER_ID},
        ("order_id",),
    ),
    "aggregate_orders": ToolSpec(
        logic.aggregate_orders,
        "Order statistics for the shopper: metric count|sum_total|avg_total grouped by status|month|category, "
        "optional placed_from / placed_to. Spend by category counts line totals.",
        {
            "metric": {"type": "string", "enum": ["count", "sum_total", "avg_total"]},
            "group_by": {"type": "string", "enum": ["status", "month", "category"]},
            "placed_from": DATE,
            "placed_to": DATE,
        },
    ),
    "get_spending_over_time": ToolSpec(
        logic.get_spending_over_time,
        "The shopper's spend and order count per month for the last `months` (default 6), oldest first — for a "
        "line or bar chart.",
        {"months": {"type": "integer", "minimum": 1}},
    ),
    "cancel_order": ToolSpec(
        logic.cancel_order,
        "Cancels an order that hasn't shipped yet (status processing), restocks its items and refunds a card "
        "payment in full.",
        {
            "order_id": ORDER_ID,
            "reason": {"type": "string", "enum": list(logic.CANCEL_REASONS), "title": "Reason", "description": "Defaults to changed_my_mind"},
        },
        ("order_id",),
        SE,
    ),
    "request_return": ToolSpec(
        logic.request_return,
        "Starts a return for a delivered order within 30 days of delivery; creates a return label (RMA) and a "
        "full refund once the parcel arrives back.",
        {
            "order_id": ORDER_ID,
            "reason": {"type": "string", "enum": list(logic.RETURN_REASONS), "title": "Reason"},
            "notes": {"type": "string", "maxLength": 500, "title": "Notes (optional)", "description": "What is wrong, in the shopper's words — write the complete note"},
        },
        ("order_id", "reason"),
        SE,
    ),
    "update_order_address": ToolSpec(
        logic.update_order_address,
        "Changes the shipping address of an order that hasn't shipped yet. Give only the fields that change.",
        {"order_id": ORDER_ID, **ADDRESS},
        ("order_id",),
        SE,
    ),
    "reorder": ToolSpec(
        logic.reorder,
        "Buy again: adds every item of a past order that is still in stock to the cart (at the current price).",
        {"order_id": ORDER_ID},
        ("order_id",),
        SE,
    ),
    # ------------------------------------------------------------ wishlist and reviews
    "list_wishlist": ToolSpec(logic.list_wishlist, "Products the shopper saved, with price, sale and stock status."),
    "add_to_wishlist": ToolSpec(
        logic.add_to_wishlist, "Saves a product to the shopper's wishlist.", {"product_id": PRODUCT_ID}, ("product_id",), SE
    ),
    "remove_from_wishlist": ToolSpec(
        logic.remove_from_wishlist, "Removes a product from the wishlist.", {"product_id": PRODUCT_ID}, ("product_id",), SE
    ),
    "write_review": ToolSpec(
        logic.write_review,
        "Publishes the shopper's review of a product delivered to them (one review per product).",
        {
            "product_id": PRODUCT_ID,
            "rating": {"type": "integer", "minimum": 1, "enum": [1, 2, 3, 4, 5], "title": "Rating", "description": "1–5 stars"},
            "title": {"type": "string", "minLength": 1, "title": "Headline", "description": "A short summary, up to 120 characters"},
            "body": {"type": "string", "minLength": 10, "maxLength": 2000, "title": "Review", "description": "The complete review text in the shopper's voice — write the full review"},
        },
        ("product_id", "rating", "title", "body"),
        SE,
    ),
    # ------------------------------------------------------------ cross-entity
    "get_my_context": ToolSpec(
        logic.get_my_context,
        "Who the shopper is: name, email, default shipping address, cart and wishlist counts, open orders, "
        "lifetime spend and payment methods on file. Use it to prefill checkout.",
    ),
    "get_overview": ToolSpec(
        logic.get_overview, "A summary for 'how are things?': cart totals, recent orders, items on sale and what needs attention."
    ),
    "list_attention_items": ToolSpec(
        logic.list_attention_items,
        "What needs the shopper's attention: orders in transit or not yet shipped, return windows closing, "
        "products waiting for a review, cart stock problems, wishlist items on sale or almost sold out.",
    ),
    "search_all": ToolSpec(
        logic.search_all,
        "One free-text search over products, the shopper's orders and categories; returns {type, id, title} hits.",
        {"query": {"type": "string", "minLength": 1}},
        ("query",),
        per_user=False,
    ),
    "describe_data": ToolSpec(
        logic.describe_data,
        "The store's vocabulary: categories, brands, sorts, order statuses, shipping methods and costs, tax rate, "
        "payment methods, countries, cancel and return reasons, return window.",
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
    kwargs = {k: v for k, v in arguments.items() if k in spec.properties and v is not None}
    missing = [k for k in spec.required if k not in kwargs]
    if missing:
        return {"error": f"missing_arguments:{','.join(missing)}"}
    return spec.fn(**kwargs)
