# Vasundhara National Bank — public-sector net banking example

A made-up public-sector bank's internet banking portal, built to look and feel like the real ones in India: a link-farm landing
page, a login page with captcha and a virtual keyboard, a maroon tab bar and an accordion menu tree, scrolling notices, a session
timer, passbook statements with cryptic narrations (`TO TRANSFER-NEFT*GGBK0000214*N…*RAJESH GUPTA--`), dense rate tables and forms
full of fine print. That is the point: on a portal like this, customers don't know which loan, deposit or scheme is right for them,
what a charge means, or where a form lives. **VNB Sahayak**, a Relay assistant, works it out from the customer's own numbers,
explains it plainly, takes them to the right screen, fills its forms, and proposes every change for approval.

The customer is Ramesh Chandra Verma (47, a state-government teacher in Lucknow, ₹82,000 a month, CIBIL 768, 20% tax slab, wife,
a 9-year-old daughter and a 71-year-old mother). He has a savings account, PPF, a ₹3 lakh FD, a tax saver FD, a recurring deposit
and a car loan, and his re-KYC is overdue.

| Part | Where | Port |
|---|---|---|
| Bank API + Relay tools (FastAPI, SQLite) | [`tools/`](tools) | 8096 |
| Agent manifest + prompt | [`agents/national-bank.yaml`](../../agents/national-bank.yaml) | — |
| Portal (Next.js 16) | [`frontend/`](frontend) | 3008 |
| Inventory and coverage | [`relay-tools.md`](relay-tools.md) | — |

```bash
docker compose -f infra/docker/docker-compose.yml up -d --build vnb-tools gateway
pnpm --filter @relay/national-bank-frontend dev          # http://localhost:3008
pnpm --filter @relay/national-bank-frontend dev:sandbox  # Experience Center mode (private copy per visitor)
```

What to ask: "I need ₹2 lakh for my mother's surgery — which loan is best?" (a loan against his FD at 8% beats a personal loan at
11.45% and keeps the FD earning; gold needs a weight first), "What is this ₹590 charge?", "Where should I save ₹5,000 a month for
10 years?" (Sukanya Samriddhi for his daughter, before she turns 10), "Should I prepay my car loan or open another FD?", "My KYC is
overdue", "Send the rent to my house owner".

How it fits together:

- **One implementation of every rule.** `tools/src/vnb_api/logic.py` holds the statement and its narration codes; beneficiaries
  (4-hour cooling period, per-beneficiary limits up to ₹10 lakh) and transfers (within VNB, IMPS up to ₹5 lakh, NEFT, RTGS from
  ₹2 lakh, ₹10 lakh a day); seven loan products with rates by CIBIL band, FOIR, age at the end of the loan, LTV and fees + GST,
  and `recommend_loans`, which ranks the products for a need by yearly cost among those whose EMI stays within 60% of salary;
  EMIs, prepayment and the FD-vs-prepay comparison; FD slab rates, the 444-day special, tax saver FDs, RDs, quarterly compounding,
  premature-closure penalty and TDS; PPF, SSY and SCSS; PMJJBY / PMSBY / APY eligibility; cheque books, stop payment, debit card
  limits and blocking; re-KYC; interest certificates; complaints with RBI-style resolution times.
- **The site API is generated from the tool table.** `GET /api/<read tool>` and `POST /api/<write tool>` run the same functions
  as the Relay tools, so every portal form is named like its tool (`data-relay-form`, field names = parameters): the assistant
  fills them and the customer submits. Writes go through `frontend/app/actions.ts` (an allow-list).
- **Per-customer data.** The portal's server starts the Relay session for the customer (`lib/session.ts`), so every tool call
  carries the signed `X-Relay-User`; per-customer tools answer `401` without one. The login page is decorative: everyone is
  `VNB_DEMO_CUSTOMER_ID`.
- **Everything a retail customer does online.** Accounts: open a savings / salary / minor / current account (`products.py`
  checks eligibility — e.g. a basic BSBD account can't sit beside another savings account, the salary package converts the main
  account and adds free accident cover), close extra ones, move money between own accounts, set the daily transfer limit,
  download the statement as CSV. Payments (`payments.py`): bills and recharges over BBPS with autopay, standing instructions,
  income-tax challans with an advance-tax check. Investments: VNB mutual funds (lumpsum, SIP, redemption with the ELSS lock-in),
  NPS with the extra 80CCD(1B) deduction. Servicing (`servicing.py`): nominees on every account and deposit (a minor nominee
  needs a guardian), Positive Pay and cheque status, Form 15G/15H (refused when income is taxable), lockers with a waiting list.
  Change password is site-only: the assistant never sees passwords.
- **Approvals.** All 35 writes are `side_effecting`: the assistant proposes them and the customer approves in the panel, or it
  fills the portal's form and the customer ticks the declaration and submits.
- **Screen actions.** `SHOW_STATEMENT` (any savings / current account), `START_TRANSFER` and `SHOW_LOAN_PRODUCT`, plus automatic navigation (the decorative
  `/info/…` links are excluded) and page forms (up to 8 per page: e-Services has six).
- **Existing data.** Billers and standing instructions were added after the first release; customers created earlier get them
  on their next request (`_seed_extras`).
- **Experience Center.** With `NEXT_PUBLIC_RELAY_SANDBOX=1`, `proxy.ts` gives each visitor a sandbox cookie and the customer
  *is* that sandbox: a private copy of the data (`VNB_SANDBOX_DIR`), resettable. See
  [docs/experience-center.md](../../docs/experience-center.md).

Bank API settings: `VNB_DB_PATH` (default `vnb.db`), `VNB_SANDBOX_DIR`, `VNB_API_TOKEN` (require a bearer token from the site's
server), `RELAY_TOOLS_SIGNING_SECRET` (verify Relay's signature). Site settings: `VNB_API_URL`, `VNB_DEMO_CUSTOMER_ID`, and the
Relay ones in [`lib/session.ts`](frontend/lib/session.ts).

The bank, its people, IFSC prefixes and every rate are made up; rules are modelled on how Indian public-sector banks publish them.
