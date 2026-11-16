# Roostly — vacation rental example

A site for booking homes across India — villas, cottages, houseboats, havelis, treehouses and
homestays in twelve destinations — with search by place, dates and guests, listing pages with an
availability calendar and price breakdown, instant book or request-to-book, trips with host messages,
changes, cancellations and reviews, and wishlists. A Relay trip assistant speaks and types, works the
site's own screens (search, booking panel, Confirm and pay), and proposes every booking and change
for the guest to approve.

| Part | Where | Port |
|---|---|---|
| Site API + Relay tools (FastAPI, SQLite) | [`tools/`](tools) | 8094 |
| Agent manifest + prompt | [`agents/stays.yaml`](../../agents/stays.yaml) | — |
| Site (Next.js 16 + shadcn) | [`frontend/`](frontend) | 3006 |
| Inventory and coverage | [`relay-tools.md`](relay-tools.md) | — |

```bash
docker compose -f infra/docker/docker-compose.yml up -d --build stays-tools gateway
pnpm --filter @relay/stays-frontend dev          # http://localhost:3006
pnpm --filter @relay/stays-frontend dev:sandbox  # Experience Center mode (private copy per visitor)
```

How it fits together:

- **One implementation of every rule.** `tools/src/stays_api/logic.py` holds availability, minimum
  stays (up to 30 nights, 365 days ahead), guest limits (infants don't count; pets only where allowed),
  nightly prices (Friday/Saturday weekend price, 20 Dec–4 Jan +30%), extra-guest, cleaning and pet
  fees, weekly / monthly discounts, the 12% service fee, GST (12%, or 18% when the average night is
  above ₹7,500), instant book vs. requests, the three cancellation policies (flexible, moderate,
  strict), date / guest changes, host replies, reviews (14 days after check-out) and wishlists. The
  site calls it through its API (`/api/…`, from server actions); the assistant calls the same
  functions as Relay tools.
- **Calendars.** Nights other guests booked are derived from the listing id and the date, so every
  visitor sees the same busy calendars; reservations made here are stored on top.
- **Requests.** A request-to-book home needs a message to the host; the demo host answers two minutes
  later (accepts if the nights are still free). Nothing is charged until then.
- **Per-guest data.** Trips, messages, wishlists and reviews belong to a guest. The site's server
  starts the Relay session for that guest (`lib/session.ts`), so every tool call carries the signed
  `X-Relay-User`; per-guest tools answer `401` without one. The demo has no sign-in page: everyone is
  Priya Nair (`STAYS_DEMO_GUEST_ID`), who starts with two wishlists and six trips (two upcoming, three
  completed — one waiting for a review — and one cancelled).
- **Approvals.** All 8 writes are `side_effecting`: the assistant proposes "book Casa Azul 20–23 Dec
  for six" and the guest approves it in the assistant panel; a booking or review can also be a form
  bound to the tool (submitting is the approval).
- **Screen actions.** `SEARCH_STAYS`, `OPEN_LISTING`, `OPEN_TRIP`, `FILTER_TRIPS`, `OPEN_WISHLIST`
  (every page) and `SET_STAY` (booking panel: dates, guests, and on to Confirm and pay), plus automatic
  navigation and page-form filling — "tell the host we arrive at 4" fills the Confirm and pay form
  without paying.
- **Experience Center.** With `NEXT_PUBLIC_RELAY_SANDBOX=1`, `proxy.ts` gives each visitor a sandbox
  cookie and the guest *is* that sandbox: a private copy of the data (`STAYS_SANDBOX_DIR`), resettable
  from the header. See [docs/experience-center.md](../../docs/experience-center.md).

Site API settings: `STAYS_DB_PATH` (default `stays.db`), `STAYS_SANDBOX_DIR`, `STAYS_API_TOKEN`
(require a bearer token from the site's server), `RELAY_TOOLS_SIGNING_SECRET` (verify Relay's
signature). Site settings: [`frontend/.env.example`](frontend/.env.example).
