"""The storefront example's tools service: signed calls, per-shopper data, sandboxes and the
store's business rules (stock, coupons, checkout, cancel, return, reviews)."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

REPO = Path(__file__).resolve().parents[3]


def _as(user: str) -> dict[str, str]:
    return {"X-Relay-User": json.dumps({"id": user})}


@pytest.fixture
def shop(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOP_DB_PATH", str(tmp_path / "shop.db"))
    monkeypatch.setenv("SHOP_SANDBOX_DIR", str(tmp_path / "sandboxes"))
    monkeypatch.delenv("RELAY_TOOLS_SIGNING_SECRET", raising=False)
    monkeypatch.delenv("SHOP_API_TOKEN", raising=False)
    from shop_api.main import app

    return TestClient(app)


def call(client: TestClient, name: str, user: str | None = "alice", **args):
    return client.post(f"/tools/{name}", headers=_as(user) if user else {}, json=args)


def test_every_write_needs_approval_and_schemas_match_functions():
    from shop_api.tools import TOOL_SPECS

    writes = {
        "add_to_cart", "update_cart_item", "remove_from_cart", "clear_cart", "apply_coupon", "remove_coupon",
        "place_order", "cancel_order", "request_return", "update_order_address", "reorder",
        "add_to_wishlist", "remove_from_wishlist", "write_review",
    }
    assert {n for n, s in TOOL_SPECS.items() if s.classification == "side_effecting"} == writes
    assert all(s.classification in ("read_only", "side_effecting") for s in TOOL_SPECS.values())
    for name, spec in TOOL_SPECS.items():
        params = inspect.signature(spec.fn).parameters
        assert set(spec.properties) <= set(params), name  # every schema field is a real argument
        assert set(spec.required) <= set(spec.properties), name
        required_args = {p for p, v in params.items() if v.default is inspect.Parameter.empty}
        assert required_args <= set(spec.required), name


def test_calls_must_be_signed_when_a_secret_is_set(shop, monkeypatch):
    monkeypatch.setenv("RELAY_TOOLS_SIGNING_SECRET", "s3cret")
    assert shop.get("/tools").status_code == 401
    assert call(shop, "search_products").status_code == 401

    from relay_adapter_tools_http import signed_headers

    body = json.dumps({"query": "desk"}).encode()
    user = json.dumps({"id": "alice"})
    headers = signed_headers("s3cret", body, operation="tools.call:search_products", session_id="s1", user=user)
    ok = shop.post("/tools/search_products", content=body, headers={**headers, "X-Relay-Session": "s1", "X-Relay-User": user, "content-type": "application/json"})
    assert ok.status_code == 200 and ok.json()["total"] >= 1
    # The same signature replayed against another tool is refused.
    replay = shop.post("/tools/clear_cart", content=body, headers={**headers, "X-Relay-Session": "s1", "X-Relay-User": user, "content-type": "application/json"})
    assert replay.status_code == 401


def test_per_shopper_tools_need_a_user_and_keep_data_apart(shop):
    assert call(shop, "get_cart", user=None).status_code == 401
    assert call(shop, "search_products", user=None).status_code == 200  # the catalog is public
    assert call(shop, "add_to_cart", product_id="SKU-1002", quantity=2).json()["cart"]["item_count"] == 2
    assert call(shop, "get_cart", user="bob").json()["item_count"] == 0
    alice_orders = {o["id"] for o in call(shop, "list_orders").json()["orders"]}
    bob_orders = {o["id"] for o in call(shop, "list_orders", user="bob").json()["orders"]}
    assert alice_orders and bob_orders and not alice_orders & bob_orders  # each shopper starts with their own history
    one_of_alices = next(iter(alice_orders))
    assert "error" in call(shop, "get_order", user="bob", order_id=one_of_alices).json()
    assert "error" in call(shop, "cancel_order", user="bob", order_id=one_of_alices).json()


def test_checkout_coupon_stock_and_cancel(shop):
    stock_before = call(shop, "get_product", product_id="SKU-1002").json()["product"]["stock"]
    call(shop, "add_to_cart", product_id="SKU-1002", quantity=2)
    assert "error" in call(shop, "add_to_cart", product_id="SKU-1003", quantity=50).json()  # more than in stock
    assert call(shop, "check_coupon", code="save20").json()["applies_to_current_cart"] is False  # needs $150
    assert call(shop, "apply_coupon", code="WELCOME10").json()["cart"]["discount"] == 11.8
    bad = call(shop, "place_order", full_name="Alice", email="nope", address_line1="1 Main St", city="Austin",
               state="TX", postal_code="78701", country="Mars").json()
    assert set(bad["fields"]) == {"email", "country"}
    order = call(shop, "place_order", full_name="Alice", email="alice@example.com", address_line1="1 Main St",
                 city="Austin", state="TX", postal_code="78701", country="United States", shipping_method="express").json()["order"]
    # 2 × $59 − 10% = $106.20; express $14.99; tax 8.25% of $106.20 = $8.76
    assert (order["subtotal"], order["discount"], order["shipping"], order["tax"], order["total"]) == (118.0, 11.8, 14.99, 8.76, 129.95)
    assert call(shop, "get_cart").json()["item_count"] == 0
    assert call(shop, "get_product", product_id="SKU-1002").json()["product"]["stock"] == stock_before - 2
    assert call(shop, "update_order_address", order_id=order["id"], city="Dallas").json()["order"]["shipping_address"]["city"] == "Dallas"
    cancelled = call(shop, "cancel_order", order_id=order["id"], reason="ordered_by_mistake").json()
    assert cancelled["order"]["status"] == "cancelled" and cancelled["refund"] == 129.95
    assert call(shop, "get_product", product_id="SKU-1002").json()["product"]["stock"] == stock_before
    assert "error" in call(shop, "cancel_order", order_id=order["id"]).json()


def test_returns_and_reviews_follow_the_rules(shop):
    orders = call(shop, "list_orders").json()["orders"]
    shipped = next(o for o in orders if o["status"] == "shipped")
    recent = next(o for o in orders if o["status"] == "delivered" and o["can_return"])
    old = next(o for o in orders if o["status"] == "delivered" and not o["can_return"])  # outside the 30-day window
    assert "error" in call(shop, "request_return", order_id=shipped["id"], reason="damaged").json()
    assert "error" in call(shop, "request_return", order_id=old["id"], reason="damaged").json()
    assert call(shop, "request_return", order_id=recent["id"], reason="damaged", notes="Cracked case").json()["return_label"].startswith("RMA-")

    delivered_product = call(shop, "get_order", order_id=old["id"]).json()["order"]["items"][0]["product_id"]
    assert "error" in call(shop, "write_review", product_id="SKU-3006", rating=5, title="Great", body="Never bought it but sure.").json()
    review = call(shop, "write_review", product_id=delivered_product, rating=4, title="Solid", body="Works well on my desk every day.").json()
    assert review["review"]["rating"] == 4
    assert "error" in call(shop, "write_review", product_id=delivered_product, rating=5, title="Again", body="A second review is refused.").json()


def test_every_read_tool_answers(shop):
    from shop_api.tools import TOOL_SPECS

    samples = {
        "get_product": {"product_id": "SKU-1001"},
        "compare_products": {"product_ids": ["SKU-1001", "SKU-1004"]},
        "check_coupon": {"code": "FREESHIP"},
        "get_order": {"order_id": call(shop, "list_orders").json()["orders"][0]["id"]},
        "search_all": {"query": "desk"},
    }
    for name, spec in TOOL_SPECS.items():
        if spec.classification != "read_only":
            continue
        res = call(shop, name, **samples.get(name, {}))
        assert res.status_code == 200 and "error" not in res.json(), (name, res.text)


def test_sandboxes_keep_visitors_apart(shop):
    a, b = "sandbox_" + "a" * 20, "sandbox_" + "b" * 20
    call(shop, "add_to_cart", user=a, product_id="SKU-1002")
    assert call(shop, "get_cart", user=a).json()["item_count"] == 1
    assert call(shop, "get_cart", user=b).json()["item_count"] == 0
    # The store API sees the same sandbox through X-Shop-User.
    assert shop.get("/api/cart", headers={"X-Shop-User": a}).json()["item_count"] == 1
    assert shop.post("/sandbox/reset", headers={"X-Sandbox-Id": a}).json() == {"reset": True}
    assert call(shop, "get_cart", user=a).json()["item_count"] == 0


def test_store_api_errors_and_token(shop, monkeypatch):
    res = shop.post("/api/cart/items", headers={"X-Shop-User": "carol"}, json={"product_id": "SKU-9999"})
    assert res.status_code == 400 and res.json()["fields"] == {"product_id": "unknown product"}
    assert shop.get("/api/products/SKU-9999").status_code == 404
    monkeypatch.setenv("SHOP_API_TOKEN", "t0ken")
    assert shop.get("/api/cart", headers={"X-Shop-User": "carol"}).status_code == 401
    assert shop.get("/api/cart", headers={"X-Shop-User": "carol", "Authorization": "Bearer t0ken"}).status_code == 200


def test_storefront_manifest_parses(monkeypatch):
    from relay_gateway.services.agent_service import parse_manifest

    monkeypatch.setenv("RELAY_SHOP_TOOLS_URL", "http://shop-tools:8092")
    manifest = parse_manifest(REPO / "agents" / "storefront.yaml")
    assert manifest.agent_id == "storefront" and manifest.tools_url == "http://shop-tools:8092"
    assert "Oakline" in manifest.system_prompt and "Aurora Wireless Headphones" in manifest.keyterms
