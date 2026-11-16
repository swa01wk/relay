# Oakline storefront — Relay inventory and coverage

Built by the workflow in the SDK's `AGENTS.md`: every page, write and entity of the store mapped to a
tool, a screen action, or an exclusion. Tools: `tools/src/shop_api/tools.py` (one table → `GET /tools`).

**Counts:** 9 pages · 14 writes (server actions → store API) + 1 page form per write that has fields ·
7 entities → **35 tools** (21 read, 14 side-effecting) · **7 screen actions** + automatic navigation and page forms.

## Pages

| Page | What is on it | Assistant reaches it with |
|---|---|---|
| `/` Home | Hero, category tiles, Deals / Picked for you / Best sellers shelves | `NAVIGATE` (logo link) |
| `/products` Catalog | Filter sidebar (category, brand, price, rating, in stock, on sale), sort, product grid | `NAVIGATE`, **`FILTER_PRODUCTS`** |
| `/products/[id]` Product | Price, stock, qty picker, Add to cart, Save, Details / Reviews tabs, review form, related | **`OPEN_PRODUCT`**, `SET_PRODUCT_QUANTITY`, `SWITCH_PRODUCT_TAB`, page form "Write a review" |
| `/cart` Cart | Lines with qty stepper and remove, coupon form, free-shipping progress, summary | `NAVIGATE` (header link) |
| `/checkout` Checkout | Contact, address, shipping method, payment method, gift note, Place order | `NAVIGATE` (`pages` entry), page form "Checkout" |
| `/orders` Orders | Status filter chips, order list | `NAVIGATE`, **`FILTER_ORDERS`** |
| `/orders/[id]` Order | Tracking timeline, items, totals, address, Cancel / Change address / Return forms, Buy again | **`OPEN_ORDER`**, page forms "Cancel order", "Change shipping address", "Return items" |
| `/wishlist` Wishlist | Saved products | `NAVIGATE` (header link) |
| not-found | — | — |

Deals (`/products?on_sale=1`) and Checkout are listed in `registerAutoNavigation`'s `pages`; the rest are links on screen.

## Writes (server actions in `frontend/app/actions.ts` → store API → `logic.py`)

| Where | What, in the shopper's words | Input | Tool |
|---|---|---|---|
| Add to cart (cards, product page) | "Add this to my cart" | product, quantity 1–10 ≤ stock | `add_to_cart` |
| Cart qty stepper | "Make it two" | product, quantity | `update_cart_item` |
| Cart Remove / stepper to 0 | "Take the kettle out" | product | `remove_from_cart` |
| `DELETE /api/cart` | "Empty my cart" | — | `clear_cart` |
| Coupon form | "Use WELCOME10" | code | `apply_coupon` (read first: `check_coupon`) |
| Coupon × | "Remove the coupon" | — | `remove_coupon` |
| Save / heart button | "Save it for later" / "remove it from my wishlist" | product | `add_to_wishlist`, `remove_from_wishlist` |
| Checkout form | "Check out" | email, phone, full name, address 1/2, city, state, postal code, country (6), shipping (standard/express), payment (card on file / pay on delivery), gift note ≤ 300 | `place_order` (form-bound) |
| Cancel form (processing orders) | "Cancel that order" | order, reason (5) | `cancel_order` |
| Change address form (processing) | "Ship it to my office instead" | order + any address field | `update_order_address` |
| Return form (delivered ≤ 30 days) | "Return the earbuds, they're broken" | order, reason (5), notes ≤ 500 | `request_return` |
| Buy again | "Order that again" | order | `reorder` |
| Review form (delivered, not yet reviewed) | "Review the lamp: 4 stars…" | product, rating 1–5, headline ≤ 120, review 10–2000 | `write_review` |

**Excluded:** card entry (payments use the method on file — the demo charges nothing); sign-in (the demo has one shopper per browser/sandbox); `/sandbox/reset` and `/health` (operator endpoints).

## Entities and their tools

| Entity | Fields that matter | Tools |
|---|---|---|
| Product | category (6), brand (6), price, compare-at (sale), rating, stock (low ≤ 10), sold last 30 d | `search_products` (list/search/filter/sort), `get_product`, `compare_products`, `aggregate_products`, `get_top_products`, `list_categories` |
| Review | product, rating 1–5, author, date | `list_reviews`, `write_review` |
| Cart (per shopper) | lines, coupon, totals (8.25 % tax, free standard shipping ≥ $75) | `get_cart`, `get_shipping_options`, `check_coupon`, cart writes above |
| Coupon | WELCOME10 (10 %), SAVE20 ($20 ≥ $150), FREESHIP | `check_coupon`, `apply_coupon`, `remove_coupon` |
| Order (per shopper) | status (processing, shipped, delivered, cancelled, return_requested), dates, totals, tracking | `list_orders`, `get_order`, `aggregate_orders`, `get_spending_over_time`, order writes above |
| Wishlist (per shopper) | products | `list_wishlist`, `add_to_wishlist`, `remove_from_wishlist` |
| Shopper | name, email, default address, payment methods | `get_my_context` |

Cross-entity: `search_all`, `get_overview`, `list_attention_items` (in transit, not yet shipped, return windows, reviews to write, cart stock, wishlist sales and low stock), `get_recommendations`, `describe_data`; domain calculations: `get_shipping_options`, `check_coupon`, `get_spending_over_time`.

## Coverage check

| Check | Holds |
|---|---|
| Pages → reachable by `NAVIGATE` | ✓ 8 of 8 (not-found excluded) |
| Detail views → `OPEN_<ENTITY>` | ✓ `OPEN_PRODUCT`, `OPEN_ORDER` |
| Lists with filters → `FILTER_<LIST>` | ✓ `FILTER_PRODUCTS` (incl. sort), `FILTER_ORDERS` |
| Writes and forms → `side_effecting` tools | ✓ 14 of 14 |
| Entities → list / get / aggregate (+ writes) | ✓ |
| Cross-entity tools | ✓ `search_all`, `get_overview`, `list_attention_items`, `get_my_context`, `describe_data`, rankings, comparison, timeseries |

## Questions it should answer (≤ 4 rounds each)

1. "Noise-cancelling headphones under $200" → `FILTER_PRODUCTS` (or `search_products`)
2. "Compare the Aurora and the Echo Buds" → `search_products` → `compare_products` → comparison surface
3. "What's the best-rated thing in Kitchen?" → `get_top_products`
4. "How many products are on sale per category?" → `aggregate_products` → bar chart
5. "Is the smart kettle in stock?" → `search_products` / `get_product`
6. "What do people say about the standing desk?" → `get_product` → `SWITCH_PRODUCT_TAB` reviews
7. "Add two Pulse speakers to my cart" → `search_products` → `add_to_cart` (approval)
8. "Change the speakers to one" → `update_cart_item` (approval)
9. "Remove the bottle" → `remove_from_cart` (approval)
10. "Would SAVE20 work?" → `check_coupon`
11. "Apply WELCOME10" → `apply_coupon` (approval)
12. "How much more for free shipping?" → `get_cart`
13. "Check out with express to my office at …" → `get_my_context` + `get_cart` → form bound to `place_order` (or fill the Checkout page form)
14. "Where's my latest order?" → `list_orders` → `OPEN_ORDER`
15. "Cancel it, I ordered by mistake" → `cancel_order` (approval)
16. "Ship order 10424 to 12 Pine St instead" → `update_order_address` (approval)
17. "Return my earbuds, they arrived damaged" → `list_orders` → `request_return` (form/approval)
18. "Order the coffee set again" → `list_orders` → `reorder` (approval)
19. "Save the weighted blanket for later" → `add_to_wishlist` (approval)
20. "Anything on my wishlist on sale?" → `list_wishlist`
21. "Write a 5-star review of the desk lamp" → `write_review` form (or fill the page form)
22. "How much did I spend in the last six months?" → `get_spending_over_time` → chart
23. "What did I spend most on?" → `aggregate_orders` by category
24. "Anything I should know about?" → `list_attention_items`
25. "Recommend something for my desk" → `get_recommendations` / `search_products`
26. "Show me only delivered orders" → `FILTER_ORDERS`
27. "Empty my cart" → `clear_cart` (approval)
28. "What payment methods do I have?" → `get_my_context`
