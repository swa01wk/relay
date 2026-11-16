# Wayline — bus booking example

An intercity bus booking site for South and West India: search with filters and a fare calendar,
a two-deck seat map, boarding and dropping points, passenger details, offers, and a trips page
with cancellation, rescheduling, boarding-point changes and ratings. A Relay travel assistant
speaks and types, works the site's own screens (search, seat map, passenger form), and proposes
every booking and change for the traveller to approve.

| Part | Where | Port |
|---|---|---|
| Booking API + Relay tools (FastAPI, SQLite) | [`tools/`](tools) | 8093 |
| Agent manifest + prompt | [`agents/bus-booking.yaml`](../../agents/bus-booking.yaml) | — |
| Site (Next.js 16 + shadcn) | [`frontend/`](frontend) | 3005 |
| Inventory and coverage | [`relay-tools.md`](relay-tools.md) | — |

```bash
docker compose -f infra/docker/docker-compose.yml up -d --build bus-tools gateway
pnpm --filter @relay/bus-frontend dev          # http://localhost:3005
pnpm --filter @relay/bus-frontend dev:sandbox  # Experience Center mode (private copy per visitor)
```

How it fits together:

- **One implementation of every rule.** `tools/src/bus_api/logic.py` holds seat availability, the
  women-only seat rule (a seat next to a woman traveller can only be booked for a woman), fares
  (upper berths ₹50 cheaper, Friday/Sunday +10%), coupons, 5% GST on AC buses, the booking cut-off,
  the cancellation tiers (10% from 48 h, 25% from 24 h, 50% from 12 h, 75% from 6 h, none after),
  rescheduling (once, ₹100 + fare difference, until 12 h) and boarding-point changes (until 4 h).
  The site calls it through the booking API (`/api/…`, from its server actions); the assistant calls
  the same functions as Relay tools.
- **Trips are generated, bookings are stored.** 30 routes × 5–7 daily schedules are seeded; a trip is
  a schedule on a date (`SCH-1042-20261120`), bookable up to 60 days ahead. Seats other travellers
  bought are derived from the trip id, so every visitor sees the same busy buses.
- **Per-traveller data.** Bookings, saved travellers, wallet and reviews belong to a traveller. The
  site's server starts the Relay session for that traveller (`lib/session.ts`), so every tool call
  carries the signed `X-Relay-User`; per-traveller tools answer `401` without one. The demo has no
  sign-in page: everyone is Priya Nair (`BUS_DEMO_TRAVELLER_ID`), who starts with two saved
  travellers, a ₹750 wallet and seven bookings (two upcoming, four completed, one cancelled).
- **Approvals.** All 7 writes are `side_effecting`: the assistant proposes "book L4 and L5 for Priya
  and Rahul" and the traveller approves it in the assistant panel; a booking can also be a form
  bound to `book_tickets` (submitting is the approval). The traveller's own clicks work as on any site.
- **Screen actions.** `SEARCH_BUSES`, `OPEN_TRIP`, `OPEN_BOOKING`, `FILTER_BOOKINGS` (every page) and
  `SELECT_SEATS` (seat map: seats, boarding / dropping points, and on to checkout), plus automatic
  navigation and page-form filling — "me and Rahul" fills the Passenger details form without paying.
- **Experience Center.** With `NEXT_PUBLIC_RELAY_SANDBOX=1`, `proxy.ts` gives each visitor a sandbox
  cookie and the traveller *is* that sandbox: a private copy of the data (`BUS_SANDBOX_DIR`),
  resettable from the header. See [docs/experience-center.md](../../docs/experience-center.md).

Booking API settings: `BUS_DB_PATH` (default `bus.db`), `BUS_SANDBOX_DIR`, `BUS_API_TOKEN` (require a
bearer token from the site's server), `RELAY_TOOLS_SIGNING_SECRET` (verify Relay's signature).
Site settings: [`frontend/.env.example`](frontend/.env.example).
