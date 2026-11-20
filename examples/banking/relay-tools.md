# Kestrel Bank — Relay inventory and coverage

Built by the workflow in the SDK's `AGENTS.md`: every page, write and entity of the site mapped to a
tool, a screen action, or an exclusion. Tools: `tools/src/bank_api/tools.py` (one table → `GET /tools`).

**Counts:** 13 pages · 13 writes (server actions → bank API) + 9 kinds of page form · 9 entities →
**39 tools** (26 read, 13 side-effecting) · **6 screen actions** + automatic navigation and page forms.

## Pages

| Page | What is on it | Assistant reaches it with |
|---|---|---|
| `/` Accounts | Total balance, account and credit card tiles, recent transactions, what needs attention, this month so far, cards | `NAVIGATE` (logo, nav) |
| `/accounts/[id]` Account | Balance, account number, IFSC, nominee, holders, cards, standing instructions, recent transactions with balance | **`OPEN_ACCOUNT`** |
| `/transactions` Statement | Search, account, category, money in/out, date range, sort; totals in and out; pages; duplicate badges | **`FILTER_TRANSACTIONS`** |
| `/transactions/[id]` Transaction | Details, reference, balance after, possible duplicate, dispute status or Raise a dispute | **`OPEN_TRANSACTION`**, page form "Raise a dispute" |
| `/transfer` Transfer | Send money form (from, to, amount, mode, note, date, repeat) with a live check; scheduled transfers with Cancel | **`START_TRANSFER`**, page form "Send money" |
| `/payees` Payees | Payee list (Pay, Remove), Add payee form | `NAVIGATE`, page form "Add payee" |
| `/bills` Bills | One card per biller: due amount and date, Pay form, Autopay form | `NAVIGATE`, page forms "Pay …", "Autopay …" |
| `/cards` Cards | Card faces, credit card dues, cards on the way, blocked cards | `NAVIGATE` |
| `/cards/[id]` Card | Lock / unlock, limits, statement summary, Pay card bill, Controls and limits, Report lost; unbilled or recent card transactions | **`OPEN_CARD`**, page forms "Pay card bill", "Card controls", "Report card lost" |
| `/deposits` Fixed deposits | Deposits with payout-now and Close early; Open a fixed deposit form with live quote; rate table | `NAVIGATE`, page form "Open a fixed deposit" |
| `/insights` Insights | Month picker, income / spending / invested / saved, spending by category, top merchants, biggest one-off, six-month cash flow chart | **`SHOW_INSIGHTS`** |
| `/disputes` Disputes | Disputes with status and expected date | `NAVIGATE` (in `registerAutoNavigation`'s `pages`) |
| not-found | — | — |

The statement filters are `data-relay-ignore` (`FILTER_TRANSACTIONS` does the same in one step).

## Writes (server actions in `frontend/app/actions.ts` → bank API → `logic.py`)

| Where | What, in the customer's words | Input | Tool |
|---|---|---|---|
| Send money form | "Send Rohan ₹1,500 for dinner" / "pay rent on the 3rd every month" | to, amount, from, mode, note, date, repeat | `transfer_money` (read first: `get_transfer_quote`) |
| Scheduled list → Cancel | "Stop the monthly transfer to Aai" | scheduled transfer | `cancel_scheduled_transfer` |
| Add payee form | "Add Priya Shah, ICICI, account …" | name, account + IFSC or UPI ID, nickname | `add_payee` |
| Payee → Remove | "Remove my old landlord" | payee | `remove_payee` |
| Bill → Pay | "Pay the electricity bill" | biller, amount (default: due), from | `pay_bill` |
| Bill → Autopay | "Turn on autopay for broadband up to ₹1,500" | biller, on/off, cap, from | `set_bill_autopay` |
| Card → Lock / Unlock | "Freeze my debit card" | card, locked | `set_card_lock` |
| Card controls form | "Turn off international on the credit card" / "ATM limit ₹20,000" | card, 4 switches, 3 daily limits | `update_card_controls` |
| Report card lost form | "I lost my debit card" | card, lost / stolen / damaged | `report_card_lost` |
| Pay card bill form | "Pay the minimum on my credit card" | card, total / minimum / outstanding or amount, from | `pay_credit_card` (read: `get_credit_card_statement`) |
| Open a fixed deposit form | "Put ₹1 lakh in an FD for 15 months" | amount, months, payout, auto-renew, from | `open_fixed_deposit` (read first: `get_fd_quote`) |
| Deposit → Close early | "Break FD-01" | deposit | `close_fixed_deposit` (read first: `get_fd_closure_quote`) |
| Raise a dispute form | "I was charged twice by Zomato" | transaction, reason (6), details | `raise_dispute` (read first: `get_transaction`) |

**Excluded:** sign-in, OTPs, PINs and card numbers (the assistant never asks for them); profile and
nominee changes, cheque books, statements as PDF (not in the demo); `/sandbox/reset` and `/health`
(operator endpoints).

## Entities and their tools

| Entity | Fields that matter | Tools |
|---|---|---|
| Customer | name, customer number, branch, relationship manager | `get_my_context`, `get_overview` |
| Account | balance, number, IFSC, holders, nominee, interest, average balance | `list_accounts`, `get_account` |
| Transaction | date, amount, direction, category (21), channel (13), merchant, reference, balance after, possible duplicate | `list_transactions`, `get_transaction`, `aggregate_transactions`, `get_cash_flow`, `get_month_summary` |
| Payee | bank account or UPI, bank, added (24-hour cooling), last paid | `list_payees`, `get_payee`, payee writes above |
| Scheduled transfer | to, amount, once / monthly, next date, last runs | `list_scheduled_transfers`, `get_transfer_limits`, `get_transfer_quote`, transfer writes above |
| Biller | open bill, due date, autopay, last paid | `list_bills`, bill writes above |
| Card | debit / credit, status, controls, limits; credit limit, outstanding, statement | `list_cards`, `get_card`, `get_credit_card_statement`, card writes above |
| Fixed deposit | principal, rate, tenure, payout, maturity, interest | `list_fixed_deposits`, `get_fd_rates`, `get_fd_quote`, `get_fd_closure_quote`, FD writes above |
| Dispute | transaction, reason, status, expected by, provisional credit | `list_disputes`, `raise_dispute` |

Cross-entity: `search_all`, `get_overview`, `list_attention_items` (bills due, card due, FDs maturing,
low balance, transfers in the next 3 days, locked cards, cards on the way, open disputes),
`describe_data`; domain calculations: `get_transfer_quote`, `get_fd_quote`, `get_fd_closure_quote`.

## Test questions

1. What's my total balance? How much is in the joint account?
2. How much did I spend on food last month, and where?
3. Chart my spending by category for October.
4. Income vs. spending for the last six months.
5. Show my Zomato orders this month — was I charged twice? → dispute the extra one.
6. What was my biggest expense this month?
7. Show every UPI payment over ₹1,000 since the 1st.
8. Send ₹1,500 to Rohan for dinner.
9. Move ₹10,000 to the joint account.
10. Send ₹2 lakh to Rohan (fails: UPI limit) / to Aai (IMPS).
11. Add Priya Shah, ICICI0001234, account 123456789012, then send her ₹60,000 (new-payee cap).
12. Pay my rent of ₹32,000 on the 1st of every month instead.
13. What's scheduled this week? Cancel the transfer to Aai.
14. Pay my electricity bill. Turn on autopay for broadband up to ₹1,500.
15. When is my credit card due, and what's the minimum? Pay the total due.
16. Freeze my debit card. Unfreeze it.
17. Switch off international payments on my credit card and set my ATM limit to ₹20,000.
18. I lost my debit card.
19. What would ₹1 lakh in an FD for 15 months earn? Open it, interest paid quarterly.
20. What do I get if I break FD-01 today?
21. Which bills are due this week?
22. Who did I send the most money to in the last six months?
23. Did Myntra refund me?
24. What's my account number and IFSC?
25. What needs my attention?
26. Tell me my card's CVV (refuses).
