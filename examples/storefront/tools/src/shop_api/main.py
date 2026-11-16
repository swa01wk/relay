"""Oakline's backend: the store API the storefront calls (``/api/…``) and the Relay tools the
assistant calls (``GET /tools``, ``POST /tools/{name}``). Both run the same ``logic`` functions.

Who the shopper is:
- Relay tools: the signed ``X-Relay-User`` header (the storefront's server started the session for
  that shopper). Per-shopper tools without one get ``401``.
- Store API: ``X-Shop-User``, set by the storefront's server after its own sign-in. The API is for
  that server only (private network); set ``SHOP_API_TOKEN`` to require it as a bearer token too.
"""

from __future__ import annotations

import hmac
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from shop_api import logic, sandbox
from shop_api.relay_signature import relay_user, require_relay_signature
from shop_api.tools import TOOL_SPECS, call_tool, tool_manifest

app = FastAPI(title="Oakline store API + Relay tools", version="0.1.0")


@contextmanager
def _as_shopper(user_id: str | None) -> Iterator[None]:
    """Run on this shopper's data: their sandbox file (Experience Center) and their rows."""
    with sandbox.use(user_id), logic.as_user(user_id):
        yield


@app.exception_handler(logic.NoUser)
async def _no_user(_request: Request, _exc: logic.NoUser) -> JSONResponse:
    return JSONResponse({"detail": "this needs a signed-in shopper"}, status_code=401)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------- Relay tools


@app.get("/tools", dependencies=[Depends(require_relay_signature)])
async def list_tools() -> dict[str, Any]:
    return {"tools": tool_manifest()}


@app.post("/tools/{name}", dependencies=[Depends(require_relay_signature)])
async def run_tool(name: str, request: Request, arguments: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    spec = TOOL_SPECS.get(name)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"unknown tool {name}")
    user = relay_user(request)
    if spec.per_user and user is None:
        raise HTTPException(status_code=401, detail="this tool needs the session's shopper (X-Relay-User)")
    try:
        with _as_shopper(user["id"] if user else None):
            result = call_tool(name, arguments)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if str(result.get("error", "")).startswith("missing_arguments"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ---------------------------------------------------------------- store API (for the storefront's server)


def shopper(
    x_shop_user: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> str | None:
    token = os.environ.get("SHOP_API_TOKEN", "").strip()
    if token and not hmac.compare_digest(authorization or "", f"Bearer {token}"):
        raise HTTPException(status_code=401, detail="store API token required")
    return (x_shop_user or "").strip() or None


def _run(user_id: str | None, fn: Any, **kwargs: Any) -> Any:
    with _as_shopper(user_id):
        result = fn(**{k: v for k, v in kwargs.items() if v is not None})
    if isinstance(result, dict) and result.get("error"):
        status = 404 if str(result["error"]).startswith("not_found") else 400
        return JSONResponse(result, status_code=status)
    return result


@app.get("/api/products")
def api_products(
    user: str | None = Depends(shopper),
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
) -> Any:
    return _run(
        user, logic.list_products, query=query, category=category, brand=brand, min_price=min_price, max_price=max_price,
        min_rating=min_rating, in_stock=in_stock, on_sale=on_sale, sort_by=sort_by, sort_order=sort_order, limit=limit, offset=offset,
    )


@app.get("/api/products/{product_id}")
def api_product(product_id: str, user: str | None = Depends(shopper)) -> Any:
    return _run(user, logic.get_product, product_id=product_id)


@app.post("/api/products/{product_id}/reviews")
def api_review(product_id: str, body: dict[str, Any] = Body(...), user: str | None = Depends(shopper)) -> Any:
    rating = body.get("rating")
    return _run(user, logic.write_review, product_id=product_id, rating=int(rating) if str(rating).isdigit() else rating,
                title=str(body.get("title", "")), body=str(body.get("body", "")))


@app.get("/api/categories")
def api_categories(user: str | None = Depends(shopper)) -> Any:
    return _run(user, logic.list_categories)


@app.get("/api/recommendations")
def api_recommendations(user: str | None = Depends(shopper), limit: int = 4) -> Any:
    return _run(user, logic.get_recommendations, limit=limit)


@app.get("/api/me")
def api_me(user: str | None = Depends(shopper)) -> Any:
    return _run(user, logic.get_my_context)


@app.get("/api/cart")
def api_cart(user: str | None = Depends(shopper), shipping_method: str = "standard") -> Any:
    return _run(user, logic.get_cart, shipping_method=shipping_method)


@app.post("/api/cart/items")
def api_cart_add(body: dict[str, Any] = Body(...), user: str | None = Depends(shopper)) -> Any:
    return _run(user, logic.add_to_cart, product_id=str(body.get("product_id", "")), quantity=int(body.get("quantity") or 1))


@app.patch("/api/cart/items/{product_id}")
def api_cart_update(product_id: str, body: dict[str, Any] = Body(...), user: str | None = Depends(shopper)) -> Any:
    return _run(user, logic.update_cart_item, product_id=product_id, quantity=int(body.get("quantity") or 0))


@app.delete("/api/cart/items/{product_id}")
def api_cart_remove(product_id: str, user: str | None = Depends(shopper)) -> Any:
    return _run(user, logic.remove_from_cart, product_id=product_id)


@app.delete("/api/cart")
def api_cart_clear(user: str | None = Depends(shopper)) -> Any:
    return _run(user, logic.clear_cart)


@app.post("/api/cart/coupon")
def api_coupon(body: dict[str, Any] = Body(...), user: str | None = Depends(shopper)) -> Any:
    return _run(user, logic.apply_coupon, code=str(body.get("code", "")))


@app.delete("/api/cart/coupon")
def api_coupon_remove(user: str | None = Depends(shopper)) -> Any:
    return _run(user, logic.remove_coupon)


@app.get("/api/shipping-options")
def api_shipping(user: str | None = Depends(shopper)) -> Any:
    return _run(user, logic.get_shipping_options)


@app.post("/api/checkout")
def api_checkout(body: dict[str, Any] = Body(...), user: str | None = Depends(shopper)) -> Any:
    allowed = TOOL_SPECS["place_order"].properties
    return _run(user, logic.place_order, **{k: str(v) for k, v in body.items() if k in allowed and v is not None})


@app.get("/api/orders")
def api_orders(user: str | None = Depends(shopper), status: str | None = None, sort_by: str = "placed_at", sort_order: str = "desc") -> Any:
    return _run(user, logic.list_orders, status=status, sort_by=sort_by, sort_order=sort_order, limit=50)


@app.get("/api/orders/{order_id}")
def api_order(order_id: str, user: str | None = Depends(shopper)) -> Any:
    return _run(user, logic.get_order, order_id=order_id)


@app.post("/api/orders/{order_id}/cancel")
def api_cancel(order_id: str, body: dict[str, Any] = Body(default_factory=dict), user: str | None = Depends(shopper)) -> Any:
    return _run(user, logic.cancel_order, order_id=order_id, reason=str(body.get("reason") or "changed_my_mind"))


@app.post("/api/orders/{order_id}/return")
def api_return(order_id: str, body: dict[str, Any] = Body(...), user: str | None = Depends(shopper)) -> Any:
    return _run(user, logic.request_return, order_id=order_id, reason=str(body.get("reason", "")), notes=body.get("notes"))


@app.patch("/api/orders/{order_id}/address")
def api_address(order_id: str, body: dict[str, Any] = Body(...), user: str | None = Depends(shopper)) -> Any:
    allowed = TOOL_SPECS["update_order_address"].properties
    return _run(user, logic.update_order_address, order_id=order_id, **{k: str(v) for k, v in body.items() if k in allowed and k != "order_id"})


@app.post("/api/orders/{order_id}/reorder")
def api_reorder(order_id: str, user: str | None = Depends(shopper)) -> Any:
    return _run(user, logic.reorder, order_id=order_id)


@app.get("/api/wishlist")
def api_wishlist(user: str | None = Depends(shopper)) -> Any:
    return _run(user, logic.list_wishlist)


@app.post("/api/wishlist")
def api_wishlist_add(body: dict[str, Any] = Body(...), user: str | None = Depends(shopper)) -> Any:
    return _run(user, logic.add_to_wishlist, product_id=str(body.get("product_id", "")))


@app.delete("/api/wishlist/{product_id}")
def api_wishlist_remove(product_id: str, user: str | None = Depends(shopper)) -> Any:
    return _run(user, logic.remove_from_wishlist, product_id=product_id)


@app.post("/sandbox/reset")
async def reset_sandbox(x_sandbox_id: str | None = Header(default=None)) -> dict[str, Any]:
    """Experience Center: throw away one visitor's store data (see ``sandbox.py``)."""
    if not sandbox.reset(x_sandbox_id):
        raise HTTPException(status_code=404, detail="no such sandbox")
    return {"reset": True}


def run() -> None:
    import uvicorn

    uvicorn.run("shop_api.main:app", host="0.0.0.0", port=int(os.environ.get("SHOP_TOOLS_PORT", "8092")))
