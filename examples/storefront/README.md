# Oakline — ecommerce example

An online store (catalog, product pages, cart, coupons, checkout, orders with tracking, cancellations,
returns, wishlist, reviews) with a Relay shopping assistant that speaks and types, works the store's
own screens, and proposes every change for the shopper to approve.

| Part | Where | Port |
|---|---|---|
| Store API + Relay tools (FastAPI, SQLite) | [`tools/`](tools) | 8092 |
| Agent manifest + prompt | [`agents/storefront.yaml`](../../agents/storefront.yaml) | — |
| Storefront (Next.js 16 + shadcn) | [`frontend/`](frontend) | 3004 |
| Inventory and coverage | [`relay-tools.md`](relay-tools.md) | — |

```bash
docker compose -f infra/docker/docker-compose.yml up -d --build shop-tools gateway
pnpm --filter @relay/storefront-frontend dev          # http://localhost:3004
pnpm --filter @relay/storefront-frontend dev:sandbox  # Experience Center mode (private store per visitor)
```

How it fits together:

- **One implementation of every rule.** `tools/src/shop_api/logic.py` holds stock checks, coupons,
  shipping, tax, cancel/return windows and review eligibility. The storefront calls it through the store
  API (`/api/…`, from its server actions); the assistant calls the same functions as Relay tools.
- **Per-shopper data.** Carts, orders and wishlists belong to a shopper. The storefront's server starts
  the Relay session for that shopper (`lib/session.ts`), so every tool call carries the signed
  `X-Relay-User`; per-shopper tools answer `401` without one. The demo has no sign-in page: everyone is
  the demo shopper (`SHOP_DEMO_SHOPPER_ID`), and each new shopper starts with a short order history.
- **Approvals.** All 14 writes are `side_effecting`: the assistant proposes "add 2 × Pulse Mini Speaker"
  and the shopper approves it in the assistant panel; checkout, returns and reviews can also be shown as
  forms (submitting is the approval). The shopper's own clicks work as in any store.
- **Screen actions.** `FILTER_PRODUCTS`, `OPEN_PRODUCT`, `OPEN_ORDER`, `FILTER_ORDERS` (every page),
  `SET_PRODUCT_QUANTITY` and `SWITCH_PRODUCT_TAB` (product page), plus automatic navigation and page-form
  filling — "ship it to my office at …" fills the checkout form without submitting it.
- **Experience Center.** With `NEXT_PUBLIC_RELAY_SANDBOX=1`, `proxy.ts` gives each visitor a sandbox
  cookie and the shopper *is* that sandbox: a private copy of the store (`SHOP_SANDBOX_DIR`), resettable
  from the header. See [docs/experience-center.md](../../docs/experience-center.md).

Store API settings: `SHOP_DB_PATH` (default `shop.db`), `SHOP_SANDBOX_DIR`, `SHOP_API_TOKEN` (require a
bearer token from the storefront's server), `RELAY_TOOLS_SIGNING_SECRET` (verify Relay's signature).
Storefront settings: [`frontend/.env.example`](frontend/.env.example).
