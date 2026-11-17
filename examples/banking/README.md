# Kestrel Bank — net banking example

A net banking site for one customer (Arjun Mehta, Pune): two savings accounts (one joint), a
searchable statement over six months, transfers by UPI / IMPS / NEFT with payees and standing
instructions, bills with autopay, a debit and a credit card (lock, controls, limits, replacement,
statement and payment), fixed deposits, disputes and spending insights. A Relay banking assistant
speaks and types, works the site's own screens (statement filters, Transfer page, cards, insights),
and proposes every payment and change for the customer to approve.

| Part | Where | Port |
|---|---|---|
| Bank API + Relay tools (FastAPI, SQLite) | [`tools/`](tools) | 8095 |
| Agent manifest + prompt | [`agents/banking.yaml`](../../agents/banking.yaml) | — |
| Site (Next.js 16 + shadcn) | [`frontend/`](frontend) | 3007 |
| Inventory and coverage | [`relay-tools.md`](relay-tools.md) | — |

```bash
docker compose -f infra/docker/docker-compose.yml up -d --build bank-tools gateway
pnpm --filter @relay/banking-frontend dev          # http://localhost:3007
pnpm --filter @relay/banking-frontend dev:sandbox  # Experience Center mode (private copy per visitor)
```

How it fits together:

- **One implementation of every rule.** `tools/src/bank_api/logic.py` holds balances, transfer modes
  (UPI for UPI payees; IMPS up to ₹5,00,000 or NEFT for bank payees; own-account transfers), limits
  (UPI ₹1,00,000 a day, ₹5,00,000 a day to other people), the new-payee cap (₹50,000 in the first
  24 hours), scheduled and monthly transfers, bills (part payments, insurance in full, autopay with a
  cap), card locks, controls and daily limits, card replacement (₹236 for a lost or stolen debit
  card), credit card statements (15th, due 20 days later, minimum 5% / ₹200), FD rates by tenure,
  quarterly payouts, maturity and early closure (rate for the time held minus 1%), and disputes
  (120 days; a duplicate charge gets a provisional credit at once). The site calls it through its API
  (`/api/…`, from server actions); the assistant calls the same functions as Relay tools.
- **History.** A new customer starts with six months of transactions generated around today
  (salary on the 1st, rent and support for Aai by standing instruction, SIP, bills, card spending, a
  Goa trip, a refund and one duplicate Zomato charge to find), with credit card bills paid in full.
- **Time.** Standing instructions, autopay, FD payouts and maturity, and replacement cards arriving
  are applied when the customer's data is next read — no scheduler.
- **Per-customer data.** Everything belongs to one customer. The site's server starts the Relay
  session for that customer (`lib/session.ts`), so every tool call carries the signed
  `X-Relay-User`; per-customer tools answer `401` without one. The demo has no sign-in page: everyone
  is `BANK_DEMO_CUSTOMER_ID`.
- **Approvals.** All 13 writes are `side_effecting`: the assistant proposes "lock the debit card
  ending ••2207" and the customer approves it in the assistant panel, or submits a form bound to the
  tool. The Transfer, Add payee, Pay card bill, Card controls, Open a fixed deposit and Raise a
  dispute forms are named like their tools, so the assistant fills them and the customer presses the
  button.
- **Screen actions.** `FILTER_TRANSACTIONS`, `OPEN_ACCOUNT`, `OPEN_TRANSACTION`, `OPEN_CARD`,
  `START_TRANSFER` (opens the Transfer page filled in; it checks limits live) and `SHOW_INSIGHTS`,
  plus automatic navigation and page-form filling.
- **Experience Center.** With `NEXT_PUBLIC_RELAY_SANDBOX=1`, `proxy.ts` gives each visitor a sandbox
  cookie and the customer *is* that sandbox: a private copy of the data (`BANK_SANDBOX_DIR`),
  resettable from the header. See [docs/experience-center.md](../../docs/experience-center.md).

Bank API settings: `BANK_DB_PATH` (default `bank.db`), `BANK_SANDBOX_DIR`, `BANK_API_TOKEN` (require a
bearer token from the site's server), `RELAY_TOOLS_SIGNING_SECRET` (verify Relay's signature). Site
settings: `BANK_API_URL`, `BANK_DEMO_CUSTOMER_ID`, and the Relay ones in
[`lib/session.ts`](frontend/lib/session.ts).
