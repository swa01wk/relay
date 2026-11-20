"""Every Relay tool, defined once: function, description, JSON schema, classification.

``GET /tools`` and ``POST /tools/{name}`` are generated from ``TOOL_SPECS``, and so is the site's API
(``GET /api/{tool}`` for reads, ``POST /api/{tool}`` for writes). Every tool is for the signed-in
customer (the signed ``X-Relay-User``) except the bank's published rates and rules. Writes are
``side_effecting``: the assistant can only propose them, and they run after the customer approves
(or submits a form bound to them). The inventory behind this catalog is in ``../relay-tools.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from vnb_api import logic, payments, products, servicing
from vnb_api.seeds import ACCOUNT_PRODUCTS, BILLER_CATEGORIES, BILLER_PROVIDERS, LOAN_PRODUCTS, LOAN_PURPOSES, LOCKERS, MF_SCHEMES, NPS


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
DATE = {"type": "string", "format": "date", "description": "YYYY-MM-DD"}
AMOUNT = {"type": "integer", "minimum": 1, "title": "Amount (₹)", "description": "Whole rupees"}
MONTHS = {"type": "integer", "minimum": 1, "maximum": 360, "title": "Tenure (months)"}
BEN = {"type": "string", "minLength": 1, "title": "Beneficiary", "description": "Beneficiary id like BEN-03, or their name / nickname — see list_beneficiaries"}
PRODUCT = {"type": "string", "enum": list(LOAN_PRODUCTS), "title": "Loan product"}
PURPOSE = {"type": "string", "enum": list(LOAN_PURPOSES), "title": "Purpose",
           "description": "; ".join(f"{k} = {v}" for k, v in LOAN_PURPOSES.items())}
DEPOSIT = {"type": "string", "minLength": 1, "title": "Deposit", "description": "Like FD-01 — see list_deposits"}
FROM_ACCOUNT = {"type": "string", "title": "From account", "description": "SB-01 (main savings, default) or another savings / current account like SB-02, CA-01"}
RELATION = {"type": "string", "enum": list(products.RELATIONS), "title": "Relation"}
BILLER = {"type": "string", "minLength": 1, "title": "Biller", "description": "Biller id like BLR-01, its nickname, category ('electricity') or consumer number — see list_billers"}

TOOL_SPECS: dict[str, ToolSpec] = {
    # ------------------------------------------------------------ the customer and accounts
    "get_my_context": ToolSpec(
        logic.get_my_context,
        "Who the customer is (name, CIF, age, branch, occupation, salary, CIBIL score, tax slab, family with ages), today's date, balances, "
        "re-KYC status and alerts (KYC overdue, deposits maturing, beneficiaries in cooling). Call first when advice depends on the customer.",
    ),
    "get_account_summary": ToolSpec(logic.get_account_summary, "Every account as the Account Summary page lists it: savings, PPF, SSY, fixed and recurring deposits (current value) and loans (outstanding)."),
    "get_account_details": ToolSpec(
        logic.get_account_details,
        "One account: savings (number, IFSC, MICR, nominee, cheque book series, debit card), PPF (deposit room this year, withdrawal and loan rules), a deposit or a loan.",
        {"account_id": {"type": "string", "minLength": 1, "description": "SB-01 savings, PPF-01, FD-01, RD-01, LN-01…"}},
        ("account_id",),
    ),
    "get_account_statement": ToolSpec(
        logic.get_account_statement,
        "Savings account statement lines (newest first) with the bank's cryptic narration and what it means (`explained`), filtered by dates, last_n, debit/credit, "
        "category, words in the narration or counterparty, amount range; with totals. To show it on the site's own statement page prefer SHOW_STATEMENT.",
        {"account_id": {"type": "string", "enum": ["SB-01"]}, "from_date": DATE, "to_date": DATE,
         "last_n": {"type": "integer", "minimum": 1, "maximum": 200}, "direction": {"type": "string", "enum": ["debit", "credit"]},
         "category": {"type": "string", "enum": list(logic.CATEGORIES)}, "query": {"type": "string"},
         "min_amount": {"type": "integer", "minimum": 0}, "max_amount": {"type": "integer", "minimum": 0},
         "limit": {"type": "integer", "minimum": 1, "maximum": 200}},
    ),
    "get_transaction": ToolSpec(
        logic.get_transaction,
        "One statement line decoded part by part (NEFT / IMPS / UPI / BBPS / ACH codes, IFSC, UPI ID), its category, and whether a complaint can be raised.",
        {"transaction_id": {"type": "string", "minLength": 1, "description": "TXN-100123 or the reference number"}},
        ("transaction_id",),
    ),
    "summarize_spending": ToolSpec(
        logic.summarize_spending,
        "Totals for charts: debits (default) or credits between two dates (default last 90 days), grouped by category, counterparty, month or channel.",
        {"from_date": DATE, "to_date": DATE, "group_by": {"type": "string", "enum": ["category", "counterparty", "month", "channel"]},
         "direction": {"type": "string", "enum": ["debit", "credit"]}},
    ),
    # ------------------------------------------------------------ beneficiaries and transfers
    "list_beneficiaries": ToolSpec(
        logic.list_beneficiaries,
        "Saved beneficiaries with bank, IFSC, masked account, per-beneficiary limit and status (active, or cooling for 4 hours after adding); today's total sent.",
        {"query": {"type": "string"}},
    ),
    "add_beneficiary": ToolSpec(
        logic.add_beneficiary,
        "Adds a beneficiary (name, account number, IFSC, per-beneficiary limit up to ₹10 lakh). They can be paid 4 hours later.",
        {"name": {"type": "string", "minLength": 1, "title": "Name as in their bank account"},
         "account_number": {"type": "string", "pattern": "^[0-9]{9,18}$", "title": "Account number"},
         "confirm_account_number": {"type": "string", "title": "Re-enter account number"},
         "ifsc": {"type": "string", "pattern": "^[A-Za-z]{4}0[A-Za-z0-9]{6}$", "title": "IFSC"},
         "limit": {"type": "integer", "minimum": 1, "maximum": 1000000, "title": "Transfer limit (₹)"},
         "nickname": {"type": "string", "maxLength": 30, "title": "Nickname"}},
        ("name", "account_number", "ifsc"),
        SE,
    ),
    "delete_beneficiary": ToolSpec(logic.delete_beneficiary, "Removes a beneficiary.", {"beneficiary_id": BEN}, ("beneficiary_id",), SE),
    "get_transfer_quote": ToolSpec(
        logic.get_transfer_quote,
        "Checks a transfer without sending: modes available (within VNB, IMPS ≤ ₹5 lakh, NEFT, RTGS ≥ ₹2 lakh), when it arrives, charges, cooling period, "
        "beneficiary limit, today's ₹10 lakh limit, balance after.",
        {"beneficiary_id": BEN, "amount": AMOUNT, "mode": {"type": "string", "enum": list(logic.MODES)}},
        ("beneficiary_id", "amount"),
    ),
    "transfer_funds": ToolSpec(
        logic.transfer_funds,
        "Sends money to a beneficiary from the savings account. Read get_transfer_quote first.",
        {"beneficiary_id": BEN, "amount": AMOUNT, "mode": {"type": "string", "enum": list(logic.MODES), "title": "Mode"},
         "remarks": {"type": "string", "maxLength": 30, "title": "Remarks"}},
        ("beneficiary_id", "amount"),
        SE,
    ),
    # ------------------------------------------------------------ loans
    "list_loan_products": ToolSpec(
        logic.list_loan_products,
        "The bank's retail loans: purposes, rates by CIBIL band and the customer's own rate, tenure, how much (LTV / salary multiple), processing fee, "
        "prepayment charges, collateral, turnaround.",
        {"product": PRODUCT},
    ),
    "recommend_loans": ToolSpec(
        logic.recommend_loans,
        "Which loan is best for this customer's need: evaluates every product for the purpose against their salary, current EMIs (FOIR), CIBIL band, age at the "
        "end of the loan and security (FDs to pledge, gold, property or car price). Returns each option's eligibility and reasons, max amount, rate, EMI, "
        "total interest + fee, ranked cheapest first, the best one with why, and `ask_for` (details that would unlock more options).",
        {"purpose": PURPOSE, "amount": AMOUNT, "tenure_months": MONTHS,
         "property_value": {"type": "integer", "minimum": 1, "description": "For home loans"},
         "vehicle_price": {"type": "integer", "minimum": 1, "description": "On-road price, for car loans"},
         "gold_grams": {"type": "number", "minimum": 1, "description": "22-carat gold the customer could pledge"},
         "for_girl_student": {"type": "boolean", "description": "Education loan for a daughter (0.50% lower)"}},
        ("purpose",),
    ),
    "calculate_emi": ToolSpec(
        logic.calculate_emi,
        "EMI, total interest and a year-by-year principal / interest / balance schedule (for a chart) for an amount and tenure at a rate or a product's rate for this customer.",
        {"amount": AMOUNT, "tenure_months": MONTHS, "rate": {"type": "number", "minimum": 0, "maximum": 30}, "product": PRODUCT},
        ("amount", "tenure_months"),
    ),
    "apply_for_loan": ToolSpec(
        logic.apply_for_loan,
        "Applies for a loan. A loan against FD is sanctioned and credited at once (the FD gets a lien); others create an application the branch follows up. "
        "Read recommend_loans first.",
        {"product": PRODUCT, "amount": AMOUNT, "tenure_months": MONTHS, "purpose": PURPOSE,
         "deposit_id": {**DEPOSIT, "description": "The FD to pledge, for loan_against_fd"},
         "gold_grams": {"type": "number", "minimum": 1}, "property_value": {"type": "integer", "minimum": 1}, "vehicle_price": {"type": "integer", "minimum": 1}},
        ("product", "amount", "tenure_months"),
        SE,
    ),
    "list_my_loans": ToolSpec(logic.list_my_loans, "The customer's loan accounts (outstanding, EMI, EMIs left, next EMI date) and loan applications."),
    "get_prepayment_quote": ToolSpec(
        logic.get_prepayment_quote,
        "What prepaying part of a loan does: charge, EMIs saved, interest saved, and a comparison with what the customer's FD earns after tax.",
        {"loan_id": {"type": "string", "minLength": 1, "description": "Like LN-01"}, "amount": AMOUNT},
        ("loan_id", "amount"),
    ),
    "prepay_loan": ToolSpec(
        logic.prepay_loan, "Prepays part of a loan from the savings account (EMI stays, tenure shortens). Read get_prepayment_quote first.",
        {"loan_id": {"type": "string", "minLength": 1, "title": "Loan"}, "amount": AMOUNT}, ("loan_id", "amount"), SE,
    ),
    # ------------------------------------------------------------ deposits
    "get_deposit_rates": ToolSpec(
        logic.get_deposit_rates,
        "Published FD slab rates (general and senior citizen), the 444-day special, tax saver FD, RD, savings rate, PPF / SSY / SCSS rates, premature closure penalty, TDS rule.",
        per_user=False,
    ),
    "quote_deposit": ToolSpec(
        logic.quote_deposit,
        "What a deposit would earn for this customer: kind fd | special (444 days) | tax_saver (5 years) | rd; rate, maturity amount and date, interest after the "
        "customer's tax, whether TDS applies, 80C saving.",
        {"kind": {"type": "string", "enum": ["fd", "special", "tax_saver", "rd"]}, "amount": AMOUNT, "monthly_amount": AMOUNT,
         "tenure_months": {"type": "integer", "minimum": 1, "maximum": 120}, "tenure_days": {"type": "integer", "minimum": 7, "maximum": 3650},
         "payout": {"type": "string", "enum": ["cumulative", "quarterly", "monthly"]}},
    ),
    "list_deposits": ToolSpec(logic.list_deposits, "The customer's fixed and recurring deposits (current value, maturity amount and date, lien) and PPF."),
    "compare_savings_options": ToolSpec(
        logic.compare_savings_options,
        "Where to put money for N years: FD/RD, PPF top-up, Sukanya Samriddhi for a daughter under 10, tax saver FD, SCSS — value after the customer's tax, "
        "80C saving, lock-in and eligibility, ranked.",
        {"years": {"type": "integer", "minimum": 1, "maximum": 25}, "lump_sum": AMOUNT, "monthly": AMOUNT},
        ("years",),
    ),
    "open_fixed_deposit": ToolSpec(
        logic.open_fixed_deposit,
        "Opens a fixed deposit (e-TDR) from the savings account. scheme fd (choose tenure) | special (444 days) | tax_saver (5 years). Read quote_deposit first.",
        {"amount": AMOUNT, "tenure_months": {"type": "integer", "minimum": 1, "maximum": 120, "title": "Tenure (months)"},
         "tenure_days": {"type": "integer", "minimum": 7, "maximum": 3650, "title": "Tenure (days)"},
         "scheme": {"type": "string", "enum": ["fd", "special", "tax_saver"], "title": "Scheme"},
         "payout": {"type": "string", "enum": ["cumulative", "quarterly", "monthly"], "title": "Interest payout"},
         "auto_renew": {"type": "boolean", "title": "Renew automatically at maturity"}},
        ("amount",),
        SE,
    ),
    "open_recurring_deposit": ToolSpec(
        logic.open_recurring_deposit, "Opens a recurring deposit; the first instalment is debited now.",
        {"monthly_amount": AMOUNT | {"title": "Monthly instalment (₹)"}, "tenure_months": {"type": "integer", "minimum": 12, "maximum": 120, "title": "Tenure (months)"}},
        ("monthly_amount", "tenure_months"), SE,
    ),
    "get_fd_closure_quote": ToolSpec(
        logic.get_fd_closure_quote,
        "What closing a fixed deposit early pays: rate for the period held minus the penalty, payout, what is given up vs. maturity, and the loan-against-FD alternative.",
        {"deposit_id": DEPOSIT}, ("deposit_id",),
    ),
    "close_fixed_deposit": ToolSpec(
        logic.close_fixed_deposit, "Closes a fixed deposit before maturity and credits the payout to savings. Read get_fd_closure_quote first.",
        {"deposit_id": DEPOSIT}, ("deposit_id",), SE,
    ),
    # ------------------------------------------------------------ government schemes
    "list_government_schemes": ToolSpec(
        logic.list_government_schemes,
        "PMJJBY, PMSBY, APY, Sukanya Samriddhi, PPF and SCSS with cost, cover, and whether this customer is eligible (and why not) or already enrolled.",
    ),
    "enroll_in_scheme": ToolSpec(
        logic.enroll_in_scheme,
        "Enrols the customer in PMJJBY (₹2 lakh life cover, ₹436 a year) or PMSBY (₹2 lakh accident cover, ₹20 a year); the premium is debited now and every June.",
        {"scheme": {"type": "string", "enum": ["pmjjby", "pmsby"], "title": "Scheme"}, "nominee_name": {"type": "string", "minLength": 1, "title": "Nominee"},
         "nominee_relation": {"type": "string", "minLength": 1, "title": "Relation"}},
        ("scheme", "nominee_name", "nominee_relation"),
        SE,
    ),
    "open_ssy_account": ToolSpec(
        logic.open_ssy_account,
        "Opens a Sukanya Samriddhi account for a daughter under 10 with a first deposit of ₹250–₹1,50,000.",
        {"girl_name": {"type": "string", "minLength": 1, "title": "Daughter's name"}, "girl_dob": DATE | {"title": "Date of birth"},
         "initial_deposit": AMOUNT | {"minimum": 250, "maximum": 150000, "title": "First deposit (₹)"}},
        ("girl_name", "girl_dob", "initial_deposit"),
        SE,
    ),
    "deposit_to_ppf": ToolSpec(
        logic.deposit_to_ppf, "Deposits into the customer's PPF (max ₹1,50,000 a financial year).", {"amount": AMOUNT}, ("amount",), SE,
    ),
    # ------------------------------------------------------------ e-services
    "request_cheque_book": ToolSpec(
        logic.request_cheque_book,
        "Orders a cheque book (10 / 25 / 50 / 100 leaves) by post to the registered address or for collection at the branch; first 10 leaves a year free.",
        {"leaves": {"type": "integer", "enum": [10, 25, 50, 100], "title": "Leaves"},
         "deliver_to": {"type": "string", "enum": ["registered_address", "branch"], "title": "Deliver to"}},
        (),
        SE,
    ),
    "stop_cheque": ToolSpec(
        logic.stop_cheque, "Stops payment of one cheque or a range from the customer's cheque book (₹100 + GST).",
        {"cheque_from": {"type": "integer", "title": "Cheque number (from)"}, "cheque_to": {"type": "integer", "title": "Cheque number (to)"},
         "reason": {"type": "string", "enum": list(logic.STOP_REASONS), "title": "Reason"}},
        ("cheque_from", "reason"), SE,
    ),
    "get_debit_card": ToolSpec(logic.get_debit_card, "The debit card: status, daily ATM and shop/online limits, international use, any replacement on the way."),
    "block_debit_card": ToolSpec(
        logic.block_debit_card,
        "Blocks the debit card permanently (lost, stolen, damaged, suspected misuse) and optionally orders a replacement (₹300 + GST; free if damaged).",
        {"reason": {"type": "string", "enum": list(logic.BLOCK_REASONS), "title": "Reason"}, "reissue": {"type": "boolean", "title": "Send a new card"}},
        ("reason",), SE,
    ),
    "update_debit_card_usage": ToolSpec(
        logic.update_debit_card_usage, "Changes the debit card's daily ATM limit (≤ ₹1 lakh), shop & online limit (≤ ₹2 lakh) or international use.",
        {"atm_daily_limit": {"type": "integer", "minimum": 0, "maximum": 100000, "title": "ATM limit per day (₹)"},
         "pos_daily_limit": {"type": "integer", "minimum": 0, "maximum": 200000, "title": "Shop & online limit per day (₹)"},
         "international": {"type": "boolean", "title": "International use"}},
        (), SE,
    ),
    "submit_kyc_declaration": ToolSpec(
        logic.submit_kyc_declaration,
        "Re-KYC: the customer declares their KYC details are unchanged (done at once) or gives a new address (then shows proof at a branch within 90 days).",
        {"address_changed": {"type": "boolean", "title": "My address has changed"}, "new_address": {"type": "string", "maxLength": 200, "title": "New address"}},
        (), SE,
    ),
    "get_interest_certificate": ToolSpec(
        logic.get_interest_certificate,
        "Interest earned in a financial year (savings, each deposit), TDS deducted or due, 80TTA deduction and whether Form 15G/15H applies — for filing tax.",
        {"financial_year": {"type": "string", "pattern": "^\\d{4}-\\d{2}$", "description": "Like 2025-26; default this year"}},
    ),
    "raise_complaint": ToolSpec(
        logic.raise_complaint,
        "Registers a complaint (failed ATM/UPI debits, charges, unauthorised transactions, card, loan, KYC…), optionally about one transaction; gives a docket and resolution date.",
        {"category": {"type": "string", "enum": list(logic.COMPLAINT_CATEGORIES), "title": "Category"},
         "description": {"type": "string", "minLength": 10, "maxLength": 1000, "title": "What happened"},
         "transaction_id": {"type": "string", "title": "Transaction (optional)"}},
        ("category", "description"), SE,
    ),
    "list_service_requests": ToolSpec(logic.list_service_requests, "Service requests (cheque books, stop payments, card blocks, re-KYC…) with status, complaints, and scheme enrolments."),
    # ------------------------------------------------------------ accounts: open, close, own transfers
    "list_account_products": ToolSpec(
        products.list_account_products,
        "Savings and current accounts the bank offers (basic BSBD, regular, salary package, senior citizen, minor accounts, current) with features, "
        "minimum balance, charges and whether this customer (or their child) is eligible and why not; the accounts they already hold.",
    ),
    "open_account": ToolSpec(
        products.open_account,
        "Opens a savings or current account for the customer (or a minor account for their daughter, operated by them). 'salary' converts the main "
        "account to the salary package instead (same number). The opening deposit comes from SB-01. Read list_account_products first.",
        {"product": {"type": "string", "enum": list(ACCOUNT_PRODUCTS), "title": "Account type"},
         "nominee_name": {"type": "string", "title": "Nominee"}, "nominee_relation": RELATION,
         "initial_deposit": {"type": "integer", "minimum": 0, "title": "Opening deposit from SB-01 (₹)"},
         "debit_card": {"type": "boolean", "title": "Issue a debit card"}, "cheque_book": {"type": "boolean", "title": "Issue a cheque book"},
         "business_name": {"type": "string", "maxLength": 80, "title": "Business name (current account)"}},
        ("product",), SE,
    ),
    "close_account": ToolSpec(
        products.close_account, "Closes an additional savings / current account; its balance moves to SB-01 and its debit card is blocked.",
        {"account_id": {"type": "string", "minLength": 1, "title": "Account", "description": "Like SB-02 or CA-01 (not SB-01)"}}, ("account_id",), SE,
    ),
    "transfer_between_own_accounts": ToolSpec(
        payments.transfer_between_own_accounts, "Moves money between the customer's own savings / current accounts, instantly and free.",
        {"from_account": FROM_ACCOUNT, "to_account": {"type": "string", "minLength": 1, "title": "To account"}, "amount": AMOUNT,
         "remarks": {"type": "string", "maxLength": 20, "title": "Remarks"}},
        ("from_account", "to_account", "amount"), SE,
    ),
    "set_transfer_limit": ToolSpec(
        payments.set_transfer_limit, "Sets the customer's daily limit for transfers to beneficiaries (₹10,000 to ₹10 lakh) — lower it for safety, raise it for a big payment.",
        {"daily_limit_amount": {"type": "integer", "minimum": 10000, "maximum": 1000000, "title": "Daily limit (₹)"}}, ("daily_limit_amount",), SE,
    ),
    # ------------------------------------------------------------ bills and standing instructions
    "list_billers": ToolSpec(
        payments.list_billers,
        "Registered billers (electricity, gas, broadband, water, mobile recharge, FASTag…) with the current bill, due date, autopay and last payment; "
        "categories and providers that can be added; mobile plans.",
    ),
    "add_biller": ToolSpec(
        payments.add_biller, "Registers a biller (BBPS) by category, provider and consumer number; postpaid bills are fetched at once.",
        {"category": {"type": "string", "enum": list(BILLER_CATEGORIES), "title": "Category"},
         "provider": {"type": "string", "enum": sorted({p for ps in BILLER_PROVIDERS.values() for p in ps}), "title": "Biller"},
         "consumer_number": {"type": "string", "minLength": 4, "title": "Consumer / account number"}, "nickname": {"type": "string", "maxLength": 30, "title": "Nickname"}},
        ("category", "provider", "consumer_number"), SE,
    ),
    "pay_bill": ToolSpec(
        payments.pay_bill, "Pays a registered biller's bill (default: the amount due) or a recharge (amount required).",
        {"biller_id": BILLER, "amount": {"type": "integer", "minimum": 1, "title": "Amount (₹)", "description": "Default: the bill due; required for recharges"},
         "from_account": FROM_ACCOUNT},
        ("biller_id",), SE,
    ),
    "set_bill_autopay": ToolSpec(
        payments.set_bill_autopay, "Turns autopay on (pays each bill on its due date up to max_amount) or off for a postpaid biller.",
        {"biller_id": BILLER, "enabled": {"type": "boolean", "title": "Autopay on"}, "max_amount": {"type": "integer", "minimum": 1, "title": "Pay automatically up to (₹)"},
         "from_account": FROM_ACCOUNT},
        ("biller_id", "enabled"), SE,
    ),
    "list_standing_instructions": ToolSpec(payments.list_standing_instructions, "Standing instructions (monthly automatic transfers) with next date and the monthly total."),
    "create_standing_instruction": ToolSpec(
        payments.create_standing_instruction,
        "Sets up a monthly automatic transfer to a beneficiary or own account on a day of the month, optionally for a number of instalments.",
        {"to": {"type": "string", "minLength": 1, "title": "To", "description": "Beneficiary (BEN-02, name or nickname) or own account (SB-02)"},
         "amount": AMOUNT, "day_of_month": {"type": "integer", "minimum": 1, "maximum": 28, "title": "Day of month"}, "from_account": FROM_ACCOUNT,
         "start_date": DATE | {"title": "Start date"}, "installments": {"type": "integer", "minimum": 1, "maximum": 120, "title": "Number of instalments"},
         "remarks": {"type": "string", "maxLength": 30, "title": "Remarks"}},
        ("to", "amount", "day_of_month"), SE,
    ),
    "cancel_standing_instruction": ToolSpec(
        payments.cancel_standing_instruction, "Cancels a standing instruction.",
        {"standing_instruction_id": {"type": "string", "minLength": 1, "title": "Standing instruction", "description": "Like SI-01"}}, ("standing_instruction_id",), SE,
    ),
    # ------------------------------------------------------------ tax
    "get_tax_payment_guide": ToolSpec(
        payments.get_tax_payment_guide, "Whether the customer must pay advance tax (tax not covered by TDS above ₹10,000), estimated tax on their interest income, due dates.",
    ),
    "pay_tax": ToolSpec(
        payments.pay_tax, "Pays income tax by challan ITNS 280 (advance tax or self-assessment tax) for an assessment year; returns the CIN for the return.",
        {"tax_type": {"type": "string", "enum": list(payments.TAX_TYPES), "title": "Type of payment"}, "amount": AMOUNT,
         "assessment_year": {"type": "string", "pattern": "^\\d{4}-\\d{2}$", "title": "Assessment year", "description": "Like 2027-28; default the coming one"},
         "from_account": FROM_ACCOUNT},
        ("tax_type", "amount"), SE,
    ),
    "list_tax_payments": ToolSpec(payments.list_tax_payments, "Tax challans paid through net banking with CIN and BSR code."),
    # ------------------------------------------------------------ investments: mutual funds, NPS
    "list_mutual_funds": ToolSpec(
        products.list_mutual_funds,
        "VNB Mutual Fund schemes: category, risk, NAV, past returns, expense ratio, exit load, lock-in, minimums and what each suits (with the market-risk disclaimer).",
        per_user=False,
    ),
    "invest_in_mutual_fund": ToolSpec(
        products.invest_in_mutual_fund, "Invests a lumpsum or starts a monthly SIP in a VNB Mutual Fund scheme (first instalment now).",
        {"scheme": {"type": "string", "enum": list(MF_SCHEMES), "title": "Scheme"}, "amount": AMOUNT,
         "mode": {"type": "string", "enum": ["lumpsum", "sip"], "title": "Lumpsum or SIP"}, "sip_day": {"type": "integer", "minimum": 1, "maximum": 28, "title": "SIP day"},
         "from_account": FROM_ACCOUNT},
        ("scheme", "amount"), SE,
    ),
    "list_mf_holdings": ToolSpec(products.list_mf_holdings, "The customer's mutual fund holdings: units, value, gain, SIP and what is still in the ELSS lock-in."),
    "redeem_mutual_fund": ToolSpec(
        products.redeem_mutual_fund, "Redeems units (an amount, or all redeemable) and/or stops the SIP; money goes to SB-01.",
        {"scheme": {"type": "string", "enum": list(MF_SCHEMES), "title": "Scheme"}, "amount": {"type": "integer", "minimum": 1, "title": "Amount (₹), blank = all"},
         "stop_sip": {"type": "boolean", "title": "Stop the SIP"}},
        ("scheme",), SE,
    ),
    "get_nps_details": ToolSpec(products.get_nps_details, "The customer's NPS account (if any), the NPS rules, their tax saving under 80CCD(1B) and years to 60."),
    "open_nps_account": ToolSpec(
        products.open_nps_account, "Opens an NPS Tier I account with an investment choice and a first contribution (min ₹1,000).",
        {"investment_choice": {"type": "string", "enum": list(NPS["choices"]), "title": "Investment choice"},
         "initial_contribution": {"type": "integer", "minimum": 1000, "title": "First contribution (₹)"},
         "nominee_name": {"type": "string", "minLength": 1, "title": "Nominee"}, "nominee_relation": RELATION},
        ("investment_choice", "initial_contribution", "nominee_name", "nominee_relation"), SE,
    ),
    "contribute_to_nps": ToolSpec(products.contribute_to_nps, "Adds a contribution to the customer's NPS Tier I.", {"amount": AMOUNT}, ("amount",), SE),
    # ------------------------------------------------------------ lockers, nominees, cheques, 15G/H
    "get_locker_availability": ToolSpec(products.get_locker_availability, "Safe deposit lockers at the home branch: sizes, yearly rent with GST, availability or waiting list, the rules, and the customer's own."),
    "apply_for_locker": ToolSpec(
        products.apply_for_locker, "Applies for a locker: allotted at once (first year's rent debited) if one is free, otherwise joins the waiting list.",
        {"size": {"type": "string", "enum": list(LOCKERS), "title": "Locker size"}, "nominee_name": {"type": "string", "title": "Nominee"}, "nominee_relation": RELATION},
        ("size",), SE,
    ),
    "list_nominees": ToolSpec(servicing.list_nominees, "The nominee on every account and deposit, and which have none."),
    "update_nominee": ToolSpec(
        servicing.update_nominee, "Registers or changes the nominee of one account or deposit (a minor nominee needs a guardian).",
        {"account_id": {"type": "string", "minLength": 1, "title": "Account / deposit", "description": "SB-01, PPF-01, FD-01, …"},
         "nominee_name": {"type": "string", "minLength": 1, "title": "Nominee"}, "nominee_relation": RELATION, "nominee_dob": DATE | {"title": "Nominee's date of birth"},
         "guardian_name": {"type": "string", "title": "Guardian (if the nominee is a minor)"}},
        ("account_id", "nominee_name", "nominee_relation", "nominee_dob"), SE,
    ),
    "get_cheque_status": ToolSpec(
        servicing.get_cheque_status, "Status of one of the customer's cheques: paid, stopped, unused, or Positive Pay registered.",
        {"cheque_number": {"type": "integer", "description": "Six-digit cheque number"}}, ("cheque_number",),
    ),
    "register_positive_pay": ToolSpec(
        servicing.register_positive_pay, "Registers a high-value cheque the customer has issued (₹50,000+; mandatory from ₹5 lakh) so it is paid only if the details match.",
        {"cheque_number": {"type": "integer", "title": "Cheque number"}, "cheque_date": DATE | {"title": "Cheque date"}, "amount": AMOUNT,
         "payee_name": {"type": "string", "minLength": 1, "title": "Payee name"}},
        ("cheque_number", "cheque_date", "amount", "payee_name"), SE,
    ),
    "submit_form_15g_15h": ToolSpec(
        servicing.submit_form_15g_15h,
        "Submits Form 15G (below 60) / 15H (60+) so no TDS is deducted on deposit interest — refused when the customer's income is taxable (a false declaration is an offence).",
        {"financial_year": {"type": "string", "pattern": "^\\d{4}-\\d{2}$", "title": "Financial year"},
         "estimated_total_income": {"type": "integer", "minimum": 0, "title": "Estimated total income this year (₹)"}},
        (), SE,
    ),
    "describe_bank_rules": ToolSpec(
        logic.describe_bank_rules,
        "The bank's rules and charges in one place: transfer modes and limits, deposit rates, loan rates and fees, service charges, KYC periods, complaint timelines, statement categories.",
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
