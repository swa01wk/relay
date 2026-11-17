"""Every Relay tool, defined once: function, description, JSON schema, classification.

``GET /tools`` and ``POST /tools/{name}`` are both generated from ``TOOL_SPECS``. Every tool is for
the signed-in customer (the signed ``X-Relay-User``), except the bank's public catalogues. Writes
are ``side_effecting``: the assistant can only propose them, and they run after the customer
approves (or submits a form bound to them). The inventory behind this catalog is in
``../relay-tools.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from bank_api import logic
from bank_api.seeds import CATEGORIES


@dataclass(frozen=True)
class ToolSpec:
    fn: Callable[..., dict[str, Any]]
    description: str
    properties: dict[str, Any] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    classification: str = "read_only"
    # Needs a signed-in customer (X-Relay-User); the service answers 401 without one.
    per_user: bool = True

    @property
    def input_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {"type": "object", "properties": self.properties}
        if self.required:
            schema["required"] = list(self.required)
        return schema


SE = "side_effecting"
DATE = {"type": "string", "format": "date"}
SORT_ORDER = {"type": "string", "enum": ["asc", "desc"]}
AMOUNT = {"type": "integer", "minimum": 1, "title": "Amount (₹)", "description": "Whole rupees"}
ACCOUNT = {"type": "string", "title": "From account", "description": "ACC-01 (Premier Savings ••4821, default) or ACC-02 (Joint Savings ••7730)",
           "enum": ["ACC-01", "ACC-02"]}
ACCOUNT_OR_CARD = {"type": "string", "description": "ACC-01, ACC-02, or a card (CRD-02 credit card, CRD-01 debit card)"}
CARD = {"type": "string", "minLength": 1, "title": "Card", "description": "Card id like CRD-01 (debit) / CRD-02 (credit), or its last four digits — see list_cards"}
TXN = {"type": "string", "minLength": 1, "title": "Transaction", "description": "Transaction id like TXN-100394 (list_transactions) or its reference"}
PAYEE = {"type": "string", "minLength": 1, "title": "Payee", "description": "Payee id like PAY-02, or their name / nickname — see list_payees"}
BILLER = {"type": "string", "minLength": 1, "title": "Biller", "description": "Biller id like BLR-01, or its name / nickname ('electricity') — see list_bills"}
DEPOSIT = {"type": "string", "minLength": 1, "title": "Fixed deposit", "description": "Like FD-01 — see list_fixed_deposits"}
CATEGORY = {"type": "string", "enum": list(CATEGORIES)}
TX_FILTERS = {
    "account_id": ACCOUNT_OR_CARD,
    "from_date": DATE,
    "to_date": DATE,
    "category": CATEGORY,
    "direction": {"type": "string", "enum": list(logic.DIRECTIONS), "description": "debit = money out, credit = money in"},
}

TOOL_SPECS: dict[str, ToolSpec] = {
    # ------------------------------------------------------------ the customer and accounts
    "get_my_context": ToolSpec(
        logic.get_my_context,
        "Who the customer is (name, customer number, branch, relationship manager), today's date, their accounts with balances, "
        "cards, number of payees and the next scheduled transfer.",
    ),
    "get_overview": ToolSpec(
        logic.get_overview,
        "A summary for 'how am I doing?': balances, cards (credit card dues), this month's income and spending, recent transactions and what needs attention.",
    ),
    "list_accounts": ToolSpec(logic.list_accounts, "The customer's bank accounts with balances and money in / out this month, plus the total."),
    "get_account": ToolSpec(
        logic.get_account,
        "One account: full number, IFSC, branch, interest rate, nominee, holders, balance vs. the average-balance requirement, cards, "
        "scheduled transfers and the last 10 transactions.",
        {"account_id": {"type": "string", "minLength": 1, "description": "ACC-01, ACC-02, 'savings', 'joint' or the last four digits"}},
        ("account_id",),
    ),
    # ------------------------------------------------------------ transactions and insights
    "list_transactions": ToolSpec(
        logic.list_transactions,
        "Transactions, newest first: filter by account or card, date range, category, direction (debit/credit), channel, amount range, "
        "free text (merchant, description, reference); sort_by date|amount. Returns transactions with balance after (bank accounts) and possible_duplicate (same merchant, amount and day), "
        "`total`, money_in and money_out for the whole match. To show them on the site's own statement page prefer FILTER_TRANSACTIONS.",
        {**TX_FILTERS,
         "channel": {"type": "string", "enum": list(logic.CHANNELS)},
         "min_amount": {"type": "integer", "minimum": 0}, "max_amount": {"type": "integer", "minimum": 0},
         "query": {"type": "string", "description": "Merchant, words in the description, or a reference"},
         "sort_by": {"type": "string", "enum": list(logic.SORTS)}, "sort_order": SORT_ORDER,
         "limit": {"type": "integer", "minimum": 1, "maximum": 200}, "offset": {"type": "integer", "minimum": 0}},
    ),
    "get_transaction": ToolSpec(
        logic.get_transaction,
        "One transaction: account, merchant or payee, channel, reference, balance after, possible duplicates (same merchant, amount and day), "
        "any dispute, and whether it can be disputed.",
        {"transaction_id": TXN},
        ("transaction_id",),
    ),
    "aggregate_transactions": ToolSpec(
        logic.aggregate_transactions,
        "Totals for charts: metric sum|count|avg of debits (spending, default) or credits, grouped by category|merchant|month|week|channel|account|weekday, "
        "optionally for an account or card, date range or category. Leaves out transfers between own accounts and card bill payments unless include_internal.",
        {"metric": {"type": "string", "enum": ["sum", "count", "avg"]},
         "group_by": {"type": "string", "enum": ["category", "merchant", "month", "week", "channel", "account", "weekday"]},
         **TX_FILTERS, "include_internal": {"type": "boolean"}},
    ),
    "get_cash_flow": ToolSpec(
        logic.get_cash_flow,
        "Income, spending (after refunds), money invested and net per month for the last `months` (≤ 6) — for a chart.",
        {"months": {"type": "integer", "minimum": 1, "maximum": 6}, "account_id": ACCOUNT_OR_CARD},
    ),
    "get_month_summary": ToolSpec(
        logic.get_month_summary,
        "One month (default this month): income, spending, invested, saved, savings rate, change vs. last month, top categories and merchants, biggest expense.",
        {"month": {"type": "string", "description": "YYYY-MM"}},
    ),
    # ------------------------------------------------------------ payees and transfers
    "list_payees": ToolSpec(
        logic.list_payees,
        "Saved payees (bank account or UPI) with bank, masked account, when added, new-payee cooling period and the last amount paid.",
        {"query": {"type": "string"}},
    ),
    "get_payee": ToolSpec(
        logic.get_payee, "One payee with recent transfers, total paid in the last six months and scheduled transfers to them.", {"payee_id": PAYEE}, ("payee_id",),
    ),
    "add_payee": ToolSpec(
        logic.add_payee,
        "Adds a payee by bank account (account number + IFSC) or UPI ID. For their first 24 hours a new payee can receive at most ₹50,000 in total.",
        {"name": {"type": "string", "minLength": 2, "maxLength": 80, "title": "Name", "description": "As on their bank account"},
         "account_number": {"type": "string", "title": "Account number", "description": "9–18 digits"},
         "ifsc": {"type": "string", "title": "IFSC", "description": "11 characters like HDFC0001234"},
         "upi_id": {"type": "string", "title": "UPI ID", "description": "Instead of account + IFSC, like name@okicici"},
         "nickname": {"type": "string", "maxLength": 30, "title": "Nickname"}},
        ("name",),
        SE,
    ),
    "remove_payee": ToolSpec(logic.remove_payee, "Removes a payee and cancels their scheduled transfers.", {"payee_id": PAYEE}, ("payee_id",), SE),
    "get_transfer_quote": ToolSpec(
        logic.get_transfer_quote,
        "Checks a transfer before proposing it: whether it can go (balance, UPI / IMPS / daily limits, new-payee cap), the mode, when it arrives, "
        "balance after and warnings. Use before transfer_money.",
        {"to": {"type": "string", "minLength": 1, "description": "Payee (id, name or nickname) or own account (ACC-02 / 'joint')"},
         "amount": AMOUNT, "from_account": ACCOUNT, "mode": {"type": "string", "enum": ["upi", "imps", "neft"]}},
        ("to", "amount"),
    ),
    "get_transfer_limits": ToolSpec(logic.get_transfer_limits, "Transfer limits and what is left today, and payees still in their 24-hour cooling period."),
    "transfer_money": ToolSpec(
        logic.transfer_money,
        "Sends money to a payee (UPI for UPI payees; IMPS or NEFT for bank payees) or to the customer's other account. With a future "
        "transfer_date it is scheduled; repeat=monthly sets up a standing instruction from that date (default today). Show it as a form so the "
        "customer checks the payee and amount.",
        {"to": {"type": "string", "minLength": 1, "title": "To", "description": "Payee (PAY-02, name or nickname) or own account (ACC-02 / 'joint')"},
         "amount": AMOUNT,
         "from_account": ACCOUNT,
         "mode": {"type": "string", "enum": ["upi", "imps", "neft"], "title": "Send by", "description": "Leave empty to pick automatically"},
         "note": {"type": "string", "maxLength": 60, "title": "Note", "description": "Shows on the statement, like 'Rent' or 'Dinner'"},
         "transfer_date": {**DATE, "title": "Date", "description": "Today unless later"},
         "repeat": {"type": "string", "enum": list(logic.REPEATS), "title": "Repeat"}},
        ("to", "amount"),
        SE,
    ),
    "list_scheduled_transfers": ToolSpec(
        logic.list_scheduled_transfers,
        "Scheduled and standing-instruction transfers (status active by default; also completed, failed, cancelled) with next date and last runs.",
        {"status": {"type": "string", "enum": ["active", "completed", "failed", "cancelled"]}},
    ),
    "cancel_scheduled_transfer": ToolSpec(
        logic.cancel_scheduled_transfer, "Cancels a scheduled transfer or standing instruction.",
        {"scheduled_id": {"type": "string", "minLength": 1, "title": "Scheduled transfer", "description": "Like SCH-01"}}, ("scheduled_id",), SE,
    ),
    # ------------------------------------------------------------ bills
    "list_bills": ToolSpec(
        logic.list_bills,
        "Registered billers (electricity, mobile, broadband, gas, insurance) with the open bill, due date, days left, autopay settings and last payment.",
        {"status": {"type": "string", "enum": ["due", "paid"]}},
    ),
    "pay_bill": ToolSpec(
        logic.pay_bill,
        "Pays a biller: the amount due by default, or part of it / an advance (insurance premiums only in full).",
        {"biller_id": BILLER, "amount": {**AMOUNT, "description": "Leave empty to pay the amount due"}, "from_account": ACCOUNT},
        ("biller_id",),
        SE,
    ),
    "set_bill_autopay": ToolSpec(
        logic.set_bill_autopay,
        "Turns autopay on or off for a biller; when on, bills up to max_amount are paid on the due date from the chosen account.",
        {"biller_id": BILLER, "enabled": {"type": "boolean", "title": "Autopay on"}, "max_amount": {**AMOUNT, "title": "Pay bills up to (₹)"},
         "from_account": ACCOUNT},
        ("biller_id", "enabled"),
        SE,
    ),
    # ------------------------------------------------------------ cards
    "list_cards": ToolSpec(
        logic.list_cards,
        "Debit and credit cards: status (active, locked, blocked, on_the_way), controls, daily limits; credit card limit, outstanding, available credit, "
        "reward points and the latest statement's dues.",
    ),
    "get_card": ToolSpec(
        logic.get_card, "One card with controls, limits and their maximums, plus unbilled (credit) or recent (debit) card transactions.", {"card_id": CARD}, ("card_id",),
    ),
    "set_card_lock": ToolSpec(
        logic.set_card_lock, "Locks a card (no new card payments or withdrawals; reversible) or unlocks it. For a lost or stolen card use report_card_lost.",
        {"card_id": CARD, "locked": {"type": "boolean", "title": "Locked"}}, ("card_id", "locked"), SE,
    ),
    "update_card_controls": ToolSpec(
        logic.update_card_controls,
        "Turns online, international, contactless or ATM (debit only) use on or off and sets daily limits (ATM debit ≤ ₹1,00,000; shop and online "
        "≤ ₹5,00,000 debit or the credit limit). Give only what changes.",
        {"card_id": CARD, "online": {"type": "boolean", "title": "Online payments"}, "international": {"type": "boolean", "title": "International use"},
         "contactless": {"type": "boolean", "title": "Contactless"}, "atm": {"type": "boolean", "title": "ATM withdrawals"},
         "atm_daily_limit": {"type": "integer", "minimum": 0, "title": "ATM limit a day (₹)"},
         "pos_daily_limit": {"type": "integer", "minimum": 0, "title": "Shop limit a day (₹)"},
         "online_daily_limit": {"type": "integer", "minimum": 0, "title": "Online limit a day (₹)"}},
        ("card_id",),
        SE,
    ),
    "report_card_lost": ToolSpec(
        logic.report_card_lost,
        "Blocks a lost, stolen or damaged card for good and orders a replacement (arrives in 5 days; ₹236 for a lost or stolen debit card). Can't be undone.",
        {"card_id": CARD, "reason": {"type": "string", "enum": list(logic.REPORT_REASONS), "title": "What happened"}},
        ("card_id", "reason"),
        SE,
    ),
    "get_credit_card_statement": ToolSpec(
        logic.get_credit_card_statement,
        "A credit card statement (latest by default, or statement_month YYYY-MM): period, purchases, payments, statement balance, minimum due, due date, "
        "what is still due now and its transactions.",
        {"card_id": CARD, "statement_month": {"type": "string", "description": "YYYY-MM"}},
    ),
    "pay_credit_card": ToolSpec(
        logic.pay_credit_card,
        "Pays the credit card from a savings account: pay=total_due (default), minimum_due or outstanding (everything incl. unbilled), or a given amount.",
        {"card_id": CARD, "pay": {"type": "string", "enum": ["total_due", "minimum_due", "outstanding"], "title": "Pay"},
         "amount": {**AMOUNT, "description": "Instead of pay, a custom amount"}, "from_account": ACCOUNT},
        (),
        SE,
    ),
    # ------------------------------------------------------------ fixed deposits
    "list_fixed_deposits": ToolSpec(
        logic.list_fixed_deposits, "Fixed deposits: amount, rate, dates, payout, auto-renew, maturity amount, interest and days to maturity.",
        {"status": {"type": "string", "enum": ["active", "matured", "closed"]}},
    ),
    "get_fd_rates": ToolSpec(logic.get_fd_rates, "Fixed deposit interest rates by tenure, the minimum and the early-closure penalty.", per_user=False),
    "get_fd_quote": ToolSpec(
        logic.get_fd_quote, "What a new fixed deposit would earn: rate, maturity date and amount, interest (or the quarterly payout).",
        {"amount": AMOUNT, "tenure_months": {"type": "integer", "minimum": 1, "maximum": 120}, "payout": {"type": "string", "enum": list(logic.FD_PAYOUTS)}},
        ("amount", "tenure_months"),
        per_user=False,
    ),
    "open_fixed_deposit": ToolSpec(
        logic.open_fixed_deposit,
        "Opens a fixed deposit from a savings account (min ₹10,000; 1–120 months). Read get_fd_quote first.",
        {"amount": AMOUNT, "tenure_months": {"type": "integer", "minimum": 1, "maximum": 120, "title": "Tenure (months)"},
         "payout": {"type": "string", "enum": list(logic.FD_PAYOUTS), "title": "Interest"}, "auto_renew": {"type": "boolean", "title": "Renew at maturity"},
         "from_account": ACCOUNT},
        ("amount", "tenure_months"),
        SE,
    ),
    "get_fd_closure_quote": ToolSpec(
        logic.get_fd_closure_quote, "What closing a fixed deposit early would pay now (rate for the time held minus 1%) vs. at maturity. Use before proposing a closure.",
        {"deposit_id": DEPOSIT}, ("deposit_id",),
    ),
    "close_fixed_deposit": ToolSpec(
        logic.close_fixed_deposit, "Closes a fixed deposit before maturity and credits the payout to its linked account.", {"deposit_id": DEPOSIT}, ("deposit_id",), SE,
    ),
    # ------------------------------------------------------------ disputes
    "raise_dispute": ToolSpec(
        logic.raise_dispute,
        "Disputes a card, UPI, ATM, bill or auto-debit payment from the last 120 days. A duplicate charge (same merchant, amount and day) is credited "
        "back provisionally at once. Read get_transaction first.",
        {"transaction_id": TXN, "reason": {"type": "string", "enum": list(logic.DISPUTE_REASONS), "title": "Reason"},
         "details": {"type": "string", "maxLength": 1000, "title": "What happened",
                     "description": "In the customer's words — required for wrong_amount, not_received and other"}},
        ("transaction_id", "reason"),
        SE,
    ),
    "list_disputes": ToolSpec(
        logic.list_disputes, "The customer's disputes with status, expected date and any provisional credit.",
        {"status": {"type": "string", "enum": ["under_review", "resolved", "rejected"]}},
    ),
    # ------------------------------------------------------------ cross-entity
    "list_attention_items": ToolSpec(
        logic.list_attention_items,
        "What needs attention: bills due within a week, the credit card due date, FDs maturing, low balances, scheduled transfers in the next 3 days, "
        "locked cards, cards on the way, open disputes.",
    ),
    "search_all": ToolSpec(
        logic.search_all,
        "One free-text search over accounts, cards, payees, billers, fixed deposits and transactions (by merchant or reference).",
        {"query": {"type": "string", "minLength": 1}},
        ("query",),
    ),
    "describe_data": ToolSpec(
        logic.describe_data,
        "The bank's vocabulary and rules: categories, channels, transfer modes and limits, new-payee cooling, bills and autopay, card controls and "
        "replacement, credit card statements, FD rates and early closure, disputes.",
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
    kwargs = {k: v for k, v in arguments.items() if k in spec.properties and v is not None and v != ""}
    missing = [k for k in spec.required if k not in kwargs]
    if missing:
        return {"error": f"missing_arguments:{','.join(missing)}"}
    return spec.fn(**kwargs)
