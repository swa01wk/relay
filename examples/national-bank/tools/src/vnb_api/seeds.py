"""Vasundhara National Bank's demo data: one retail customer, the bank's product catalogue and rates.

The bank, its people, IFSC prefixes and every rate here are made up for the demo. Rates and rules are
modelled on how Indian public-sector banks publish theirs (slabs by tenure, senior-citizen extra, CIBIL
bands, FOIR, processing fee plus 18% GST), so the questions customers ask are realistic.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

BANK = "Vasundhara National Bank"
IFSC_PREFIX = "VNBA0"
GST = 0.18
HISTORY_DAYS = 185

def emi(principal: float, rate: float, months: int) -> int:
    """Monthly instalment for a loan at ``rate`` % p.a. over ``months`` (reducing balance)."""
    r = rate / 1200
    if months <= 0:
        return int(round(principal))
    if r == 0:
        return int(round(principal / months))
    return int(round(principal * r * (1 + r) ** months / ((1 + r) ** months - 1)))


# ---------------------------------------------------------------- the customer

DEFAULT_CUSTOMER: dict[str, Any] = {
    "name": "Ramesh Chandra Verma",
    "cif": "80451297364",
    "username": "rcverma79",
    "dob": "1979-03-14",
    "gender": "male",
    "mobile": "+91 98XXXXX412",
    "email": "rc.v****@mail.com",
    "pan": "AXXPV****K",
    "address": "C-214, Sector 11, Indira Nagar, Lucknow, Uttar Pradesh 226016",
    "branch": "Hazratganj, Lucknow",
    "branch_code": "04512",
    "ifsc": "VNBA0004512",
    "occupation": "Salaried — State Government (Senior Teacher, Govt. Inter College)",
    "employer_type": "government",
    "retirement_age": 60,
    "has_pension": True,
    "net_monthly_income": 82000,
    "cibil_score": 768,
    "income_tax_slab_percent": 20,
    "tax_regime": "old",
    "risk_category": "low",
    # Re-KYC: low-risk customers every 10 years (RBI master direction); last done Aug 2016.
    "kyc_last_updated": "2016-08-05",
    "family": [
        {"name": "Sunita Verma", "relation": "wife", "dob": "1982-11-02"},
        {"name": "Ananya Verma", "relation": "daughter", "dob": "2017-06-20"},
        {"name": "Kamla Devi", "relation": "mother", "dob": "1955-01-09"},
    ],
}

# ---------------------------------------------------------------- products and rates

# Fixed deposit rates (% p.a.) by tenure in days; senior citizens (60+) get SENIOR_EXTRA more.
FD_SLABS: list[dict[str, Any]] = [
    {"label": "7 days to 45 days", "min_days": 7, "max_days": 45, "rate": 3.50},
    {"label": "46 days to 179 days", "min_days": 46, "max_days": 179, "rate": 5.50},
    {"label": "180 days to 210 days", "min_days": 180, "max_days": 210, "rate": 6.25},
    {"label": "211 days to less than 1 year", "min_days": 211, "max_days": 364, "rate": 6.50},
    {"label": "1 year to less than 2 years", "min_days": 365, "max_days": 729, "rate": 6.80},
    {"label": "2 years to less than 3 years", "min_days": 730, "max_days": 1094, "rate": 7.00},
    {"label": "3 years to less than 5 years", "min_days": 1095, "max_days": 1824, "rate": 6.75},
    {"label": "5 years and up to 10 years", "min_days": 1825, "max_days": 3650, "rate": 6.50},
]
SPECIAL_FD = {"name": "Vasundhara Utsav 444 days", "days": 444, "rate": 7.25, "valid_till": "2027-03-31"}
SENIOR_EXTRA = 0.50
TAX_SAVER = {"name": "VNB Tax Saver FD", "years": 5, "rate": 6.50, "max_per_year": 150000}
SB_RATE = 2.70  # savings bank, % p.a., credited quarterly

SMALL_SAVINGS = {
    "ppf": {"name": "Public Provident Fund (PPF)", "rate": 7.1, "min_year": 500, "max_year": 150000, "years": 15,
            "tax": "EEE — deposits qualify under 80C, interest and maturity tax-free"},
    "ssy": {"name": "Sukanya Samriddhi Yojana (SSY)", "rate": 8.2, "min_year": 250, "max_year": 150000, "deposit_years": 15,
            "years": 21, "girl_max_age": 10, "tax": "EEE — deposits qualify under 80C, interest and maturity tax-free"},
    "scss": {"name": "Senior Citizens' Savings Scheme (SCSS)", "rate": 8.2, "min": 1000, "max": 3000000, "years": 5, "min_age": 60,
             "tax": "Deposit qualifies under 80C; interest is taxable, paid quarterly"},
}

GOVT_SCHEMES: dict[str, dict[str, Any]] = {
    "pmjjby": {
        "name": "Pradhan Mantri Jeevan Jyoti Bima Yojana (PMJJBY)",
        "kind": "Life insurance",
        "cover": 200000,
        "premium": 436,
        "join_age": (18, 50),
        "cover_till_age": 55,
        "summary": "₹2 lakh life cover for death from any cause, ₹436 a year auto-debited every 1 June–31 May.",
    },
    "pmsby": {
        "name": "Pradhan Mantri Suraksha Bima Yojana (PMSBY)",
        "kind": "Accident insurance",
        "cover": 200000,
        "premium": 20,
        "join_age": (18, 70),
        "cover_till_age": 70,
        "summary": "₹2 lakh for accidental death or total disability (₹1 lakh partial), ₹20 a year auto-debited.",
    },
    "apy": {
        "name": "Atal Pension Yojana (APY)",
        "kind": "Pension",
        "join_age": (18, 40),
        "summary": "Guaranteed pension of ₹1,000–₹5,000 a month from 60; contribution depends on joining age. "
                   "Not open to income-tax payers since 1 Oct 2022.",
        "taxpayer_excluded": True,
    },
}

GOLD_RATE_PER_GRAM_22K = 7450  # demo valuation used for gold loans

# Retail loan catalogue. Rates are % p.a. by CIBIL band (>=800, 750–799, 700–749, below 700).
LOAN_PRODUCTS: dict[str, dict[str, Any]] = {
    "home_loan": {
        "name": "Vasundhara Griha Home Loan",
        "purposes": ["home_purchase", "home_construction"],
        "rates": [8.50, 8.65, 8.95, 9.65],
        "max_tenure_months": 360,
        "max_age_at_end": 70,
        "foir": 0.60,
        "ltv": "90% up to ₹30 lakh, 80% up to ₹75 lakh, 75% above",
        "processing": {"percent": 0.35, "min": 2000, "max": 10000},
        "prepayment": "No charge (floating rate)",
        "collateral": "Mortgage of the property",
        "turnaround": "7–10 working days after documents",
        "min_amount": 300000,
        "max_amount": 50000000,
        "notes": ["Women borrowers 0.05% lower", "Tax: principal under 80C, interest up to ₹2 lakh under 24(b) (old regime)"],
    },
    "home_improvement": {
        "name": "Griha Sudhaar Home Improvement Loan",
        "purposes": ["home_renovation"],
        "rates": [9.00, 9.15, 9.45, 10.15],
        "max_tenure_months": 180,
        "max_age_at_end": 70,
        "foir": 0.60,
        "ltv": "Up to 80% of the estimate",
        "processing": {"percent": 0.35, "min": 2000, "max": 10000},
        "prepayment": "No charge",
        "collateral": "Mortgage of the house being improved",
        "turnaround": "5–7 working days",
        "min_amount": 100000,
        "max_amount": 10000000,
        "notes": ["Needs the house's title papers and a contractor's estimate"],
    },
    "car_loan": {
        "name": "Vasundhara Vahan Car Loan",
        "purposes": ["vehicle"],
        "rates": [9.15, 9.40, 9.90, 10.40],
        "max_tenure_months": 84,
        "max_age_at_end": 70,
        "foir": 0.60,
        "ltv": "Up to 90% of the on-road price",
        "processing": {"percent": 0.40, "min": 1000, "max": 7500},
        "prepayment": "2% of the amount prepaid in the first 2 years, nil after",
        "collateral": "Hypothecation of the car",
        "turnaround": "2–3 working days",
        "min_amount": 100000,
        "max_amount": 10000000,
        "notes": ["Electric cars 0.20% lower"],
    },
    "personal_loan": {
        "name": "Jan Vetan Personal Loan (salaried)",
        "purposes": ["personal_need", "medical", "wedding", "travel", "home_renovation", "vehicle", "education"],
        "rates": [11.45, 11.95, 12.85, 14.60],
        "govt_employee_discount": 0.50,
        "max_tenure_months": 72,
        "max_age_at_end": 60,
        "foir": 0.50,
        "income_multiple": 24,
        "ltv": "Up to 24 × net monthly salary, max ₹20 lakh",
        "processing": {"percent": 1.50, "min": 1000, "max": 15000},
        "prepayment": "3% of the amount prepaid",
        "collateral": "None",
        "turnaround": "Same day for salary-account holders",
        "min_amount": 25000,
        "max_amount": 2000000,
        "notes": ["Salary must be credited to a VNB account", "Government employees 0.50% lower"],
    },
    "education_loan": {
        "name": "Vidya Shree Education Loan",
        "purposes": ["education"],
        "rates": [8.15, 8.65, 9.15, 10.15],
        "girl_discount": 0.50,
        "max_tenure_months": 180,
        "max_age_at_end": 75,
        "foir": 0.60,
        "ltv": "Full cost up to ₹7.5 lakh without collateral; above that 100% security",
        "processing": {"percent": 0.0, "min": 0, "max": 0},
        "prepayment": "No charge",
        "collateral": "None up to ₹7.5 lakh (parent co-borrows)",
        "turnaround": "7–15 working days (admission letter needed)",
        "min_amount": 50000,
        "max_amount": 5000000,
        "moratorium": "Course period + 1 year (simple interest during it)",
        "notes": ["Interest paid is deductible under 80E for 8 years", "Needs an admission letter"],
    },
    "gold_loan": {
        "name": "Swarna Gold Loan",
        "purposes": ["personal_need", "medical", "wedding", "travel", "education", "home_renovation", "vehicle"],
        "rates": [9.60, 9.60, 9.60, 9.60],
        "max_tenure_months": 36,
        "max_age_at_end": 99,
        "foir": None,
        "ltv": f"75% of the gold's value (22 carat at ₹{GOLD_RATE_PER_GRAM_22K:,}/g demo rate)",
        "processing": {"percent": 0.25, "min": 250, "max": 5000},
        "prepayment": "No charge",
        "collateral": "Gold ornaments pledged at the branch",
        "turnaround": "Same day at the branch",
        "min_amount": 20000,
        "max_amount": 5000000,
        "notes": ["Bring the ornaments to the branch; no income proof needed", "Bullet repayment allowed up to 12 months"],
    },
    "loan_against_fd": {
        "name": "e-Loan against Fixed Deposit",
        "purposes": ["personal_need", "medical", "wedding", "travel", "education", "home_renovation", "vehicle"],
        "rate_over_fd": 1.00,
        "max_tenure_months": None,  # until the deposit matures
        "max_age_at_end": 120,
        "foir": None,
        "ltv": "Up to 90% of the deposit (not tax-saver FDs)",
        "processing": {"percent": 0.0, "min": 0, "max": 0},
        "prepayment": "No charge; repay any time",
        "collateral": "Lien on your fixed deposit (it keeps earning)",
        "turnaround": "Instant in net banking",
        "min_amount": 5000,
        "max_amount": 50000000,
        "notes": ["The FD is not broken and keeps earning its rate", "Interest = FD rate + 1%"],
    },
}
LOAN_PURPOSES = {
    "home_purchase": "Buying a house or flat",
    "home_construction": "Building a house",
    "home_renovation": "Repairs or renovation",
    "vehicle": "Buying a car",
    "education": "Education (self or children)",
    "medical": "Medical expenses",
    "wedding": "Wedding",
    "travel": "Travel",
    "personal_need": "Any other personal need",
}

# ---------------------------------------------------------------- the customer's products

CAR_LOAN = {"principal": 650000, "rate": 9.20, "months": 84}
CAR_EMI = emi(CAR_LOAN["principal"], CAR_LOAN["rate"], CAR_LOAN["months"])

DEBIT_CARD = {"id": "CARD-01", "network": "RuPay Classic", "number_masked": "6078 XXXX XXXX 7731", "status": "active",
              "atm_daily_limit": 40000, "pos_daily_limit": 75000, "international": False, "expiry": "08/29"}

BENEFICIARIES = [
    {"id": "BEN-01", "name": "Sunita Verma", "nickname": "Wife", "account_number": "30218846120", "ifsc": "VNBA0004512",
     "bank": BANK, "branch": "Hazratganj, Lucknow", "limit": 200000, "added_days_ago": 900},
    {"id": "BEN-02", "name": "Kamla Devi", "nickname": "Amma", "account_number": "30107715234", "ifsc": "VNBA0001877",
     "bank": BANK, "branch": "Aliganj, Lucknow", "limit": 100000, "added_days_ago": 1400},
    {"id": "BEN-03", "name": "Rajesh Gupta", "nickname": "House owner", "account_number": "50100377281904", "ifsc": "GGBK0000214",
     "bank": "Ganga Gramin Bank", "branch": "Indira Nagar, Lucknow", "limit": 50000, "added_days_ago": 700},
    {"id": "BEN-04", "name": "Ankit Verma", "nickname": "Brother", "account_number": "918020045573311", "ifsc": "DCBL0000731",
     "bank": "Deccan Commercial Bank", "branch": "Koramangala, Bengaluru", "limit": 500000, "added_days_ago": 500},
    {"id": "BEN-05", "name": "Vidya Niketan Inter College", "nickname": "School fees", "account_number": "40022190066", "ifsc": "GGBK0000214",
     "bank": "Ganga Gramin Bank", "branch": "Indira Nagar, Lucknow", "limit": 100000, "added_days_ago": 650},
    # Added an hour ago: still in the 4-hour cooling period.
    {"id": "BEN-06", "name": "Mohit Electricals", "nickname": "Electrician", "account_number": "2201338890", "ifsc": "PUCB0000088",
     "bank": "Purvanchal Urban Co-op Bank", "branch": "Chinhat, Lucknow", "limit": 25000, "added_days_ago": 0.04},
]


def add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    last = [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(day.day, last))


def deposits_for(today: date) -> list[dict[str, Any]]:
    fd_open = add_months(today, -11)
    tax_open = date(today.year - 3, 3, 28)
    rd_open = add_months(today, -22).replace(day=10)
    return [
        {"id": "FD-01", "kind": "fd", "scheme": "Regular fixed deposit", "number": "39871140021", "principal": 300000, "rate": 7.00,
         "opened": fd_open.isoformat(), "tenure_days": 730, "maturity": (fd_open + timedelta(days=730)).isoformat(),
         "payout": "cumulative", "auto_renew": True, "status": "active", "lien": 0},
        {"id": "FD-02", "kind": "tax_saver", "scheme": TAX_SAVER["name"], "number": "39871140022", "principal": 100000, "rate": 6.50,
         "opened": tax_open.isoformat(), "tenure_days": 1826, "maturity": add_months(tax_open, 60).isoformat(),
         "payout": "cumulative", "auto_renew": False, "status": "active", "lien": 0},
        {"id": "RD-01", "kind": "rd", "scheme": "Recurring deposit", "number": "39876541001", "monthly": 3000, "rate": 6.80,
         "opened": rd_open.isoformat(), "months": 36, "maturity": add_months(rd_open, 36).isoformat(),
         "installments_paid": 22, "status": "active"},
    ]


def ppf_for(today: date) -> dict[str, Any]:
    return {"id": "PPF-01", "kind": "ppf", "name": "PPF account", "number": "32019985120", "opened": "2015-04-10",
            "balance": 642318, "maturity": "2031-04-01", "this_fy_deposits": 30000, "status": "active"}


def car_loan_for(today: date) -> dict[str, Any]:
    start = add_months(today, -38).replace(day=10)
    return {"id": "LN-01", "product": "car_loan", "name": "Vasundhara Vahan Car Loan", "number": "40123451290",
            "sanctioned": CAR_LOAN["principal"], "rate": CAR_LOAN["rate"], "tenure_months": CAR_LOAN["months"], "emi": CAR_EMI, "start": start.isoformat(), "emi_day": 10,
            "vehicle": "Maruti Dzire VXi (UP32 KX 4471)", "status": "active", "emis_paid": 38}


# ---------------------------------------------------------------- six months of statement


def _upi_ref(rng: random.Random) -> str:
    return str(rng.randint(400000000000, 699999999999))


def build_history(today: date, *, seed: int = 4512) -> tuple[int, list[dict[str, Any]]]:
    """Statement lines for the savings account over the last HISTORY_DAYS (oldest first, no ids/balances).

    Returns (opening_balance, lines). Narrations look like a PSU bank passbook on purpose: cryptic
    codes the customer has to decode — ``category`` and ``counterparty`` are what they mean.
    """
    rng = random.Random(seed)
    start = today - timedelta(days=HISTORY_DAYS)
    lines: list[dict[str, Any]] = []

    def add(day: date, amount: int, direction: str, narration: str, category: str, counterparty: str, channel: str, ref: str = "") -> None:
        if start <= day < today:
            lines.append({"date": day.isoformat(), "amount": int(amount), "direction": direction, "narration": narration,
                          "category": category, "counterparty": counterparty, "channel": channel,
                          "ref": ref or str(rng.randint(10**9, 10**10 - 1))})

    grocers = [("AWADH SUPERMART", "awadhsupermart@vnb"), ("SHARMA KIRANA STORE", "sharmakirana@okvnb"),
               ("GUPTA GENERAL STORE", "guptagen@ggbk"), ("FRESH SABZI MANDI", "sabzimandi12@okdcb")]
    shops = [("CITY MEDICOS", "citymedicos@vnb", "health"), ("RAJ FUELS IOC", "rajfuels@ggbk", "fuel"),
             ("LUCKNOW BOOK DEPOT", "lkobooks@okvnb", "education"), ("KAPOOR TAILORS", "kapoortailor@okdcb", "shopping"),
             ("MITTAL ELECTRONICS", "mittalelec@vnb", "shopping")]

    cursor = date(start.year, start.month, 1)
    while cursor < today:
        month_tag = cursor.strftime("%b%y").upper()
        add(cursor, 82000, "credit", f"BY TRANSFER-SAL/DIR TREASURY LKO/{month_tag}/EMP 7731042--", "salary", "Salary — Directorate of Treasuries, Lucknow", "salary")
        add(cursor.replace(day=5), 14000, "debit", f"TO TRANSFER-NEFT*GGBK0000214*N{rng.randint(10**8, 10**9)}*RAJESH GUPTA--", "rent", "Rajesh Gupta (house owner)", "neft")
        add(cursor.replace(day=10), CAR_EMI, "debit", "TO TRANSFER-LOAN RECOVERY 40123451290 EMI--", "loan_emi", "Car loan EMI (LN-01)", "auto_debit")
        add(cursor.replace(day=10), 3000, "debit", "TO TRANSFER-RD INSTL 39876541001--", "savings_investment", "Recurring deposit RD-01", "auto_debit")
        add(cursor.replace(day=7), 5000, "debit", "TO TRANSFER-INB KAMLA DEVI 30107715234--", "family", "Kamla Devi (mother)", "intra_bank")
        bill = rng.choice([1840, 2210, 2675, 3120, 1490])
        add(cursor.replace(day=14), bill, "debit", f"TO TRANSFER-BBPS/LKO POWER DIST CO/ACC 4471882301/{month_tag}--", "utilities", "Electricity bill (Lucknow Power Distribution)", "bill_pay")
        add(cursor.replace(day=18), 399, "debit", f"TO TRANSFER-UPI/DR/{_upi_ref(rng)}/TELCO PRE/YBLX/telcoprepaid@ybl/Recharg--", "utilities", "Mobile recharge", "upi")
        add(cursor.replace(day=21), rng.choice([960, 1010, 1105]), "debit", f"TO TRANSFER-BBPS/AWADH GAS LTD/CA 1100478--", "utilities", "Piped gas bill (Awadh Gas)", "bill_pay")
        for _ in range(rng.randint(6, 9)):
            name, vpa = rng.choice(grocers)
            day = cursor + timedelta(days=rng.randint(0, 27))
            add(day, rng.choice([180, 240, 365, 420, 560, 780, 1150, 1640]), "debit",
                f"TO TRANSFER-UPI/DR/{_upi_ref(rng)}/{name[:10]}/{vpa.split('@')[1].upper()[:4]}/{vpa}/Paymen--", "groceries", name.title(), "upi")
        for _ in range(rng.randint(2, 4)):
            name, vpa, cat = rng.choice(shops)
            day = cursor + timedelta(days=rng.randint(0, 27))
            add(day, rng.choice([350, 620, 900, 1400, 2300, 3800]), "debit",
                f"TO TRANSFER-UPI/DR/{_upi_ref(rng)}/{name[:10]}/{vpa.split('@')[1].upper()[:4]}/{vpa}/Paymen--", cat, name.title(), "upi")
        atm_day = cursor + timedelta(days=rng.randint(2, 25))
        add(atm_day, rng.choice([3000, 5000, 10000]), "debit", f"ATM WDL-ATM CASH {rng.randint(1000, 9999)} HAZRATGANJ LKO", "cash", "Cash withdrawal (ATM)", "atm")
        pos_day = cursor + timedelta(days=rng.randint(0, 27))
        add(pos_day, rng.choice([1260, 2480, 3315]), "debit", "POS 607XXXXXX7731 AWADH SUPERMART LKO", "groceries", "Awadh Supermart (debit card)", "pos")
        if cursor.month in (4, 7, 10, 1):
            add(cursor.replace(day=12), 18500, "debit", f"TO TRANSFER-NEFT*GGBK0000214*N{rng.randint(10**8, 10**9)}*VIDYA NIKETAN INT--", "education", "Vidya Niketan Inter College (school fees)", "neft")
        if cursor.month in (3, 6, 9, 12):
            add(cursor.replace(day=28), 6240, "debit", "TO TRANSFER-ACH DR/JEEVAN SURAKSHA INSU/POL 778120034--", "insurance", "Life insurance premium (Jeevan Suraksha, ECS)", "auto_debit")
        if cursor.month in (2, 5, 8, 11):
            add(cursor.replace(day=28), rng.choice([880, 940, 1015]), "credit", "CREDIT INTEREST--", "interest", "Savings interest", "interest")
            add(cursor.replace(day=27), 15, "debit", "SMS ALERT CHGS FOR QTR--", "charges", "SMS alert charges (quarterly, incl. GST)", "charges")
        if cursor.month == 9:
            add(cursor.replace(day=15), 236, "debit", "DEBIT CARD AMC CHGS 6078XX7731 INCL GST--", "charges", "Debit card annual fee (₹200 + 18% GST)", "charges")
        if cursor.month in (4, 10):
            add(cursor.replace(day=20), 10000, "debit", "TO TRANSFER-PPF A/C 32019985120 DEP--", "savings_investment", "PPF deposit (PPF-01)", "intra_bank")
        if rng.random() < 0.5:
            add(cursor + timedelta(days=rng.randint(3, 25)), rng.choice([2000, 3000, 5000]), "debit",
                f"TO TRANSFER-INB SUNITA VERMA 30218846120--", "family", "Sunita Verma (wife)", "intra_bank")
        cursor = add_months(cursor, 1)

    # One-offs worth asking about.
    add(today - timedelta(days=41), 1499, "debit", f"TO TRANSFER-UPI/DR/{_upi_ref(rng)}/MITTAL ELE/VNBA/mittalelec@vnb/Fan--", "shopping", "Mittal Electronics", "upi")
    add(today - timedelta(days=37), 1499, "credit", f"BY TRANSFER-UPI/CR/{_upi_ref(rng)}/MITTAL ELE/VNBA/mittalelec@vnb/Refund--", "refund", "Mittal Electronics (refund)", "upi")
    add(today - timedelta(days=19), 590, "debit", "ATM DECLINED TXN CHGS-OTHER BANK ATM--", "charges", "Charge for a declined transaction at another bank's ATM (₹500 + GST)", "charges")
    add(today - timedelta(days=9), 25000, "debit", f"TO TRANSFER-IMPS/P2A/{_upi_ref(rng)}/ANKIT VERMA/DCBL/Hospital--", "family", "Ankit Verma (brother)", "imps")
    lines.sort(key=lambda r: (r["date"], r["direction"] != "credit"))
    return 96500, lines


# ---------------------------------------------------------------- savings / current account products

ACCOUNT_PRODUCTS: dict[str, dict[str, Any]] = {
    "bsbd": {
        "name": "Jan Bachat Basic Savings (BSBD)", "kind": "savings", "rate": 2.70, "minimum_balance": "Nil",
        "for": "Anyone who wants a no-frills zero-balance account", "holder": ("self",),
        "features": ["Zero balance", "RuPay basic debit card free", "4 free withdrawals a month (ATM + branch)", "No cheque book"],
        "charges": "Nil", "rule": "Can't be held together with any other savings account at VNB (RBI rule)",
    },
    "regular": {
        "name": "Vasundhara Savings Plus", "kind": "savings", "rate": 2.70, "minimum_balance": "Nil (no penalty for low balance)",
        "for": "Individuals; a second account for a goal or for a spouse's household expenses", "holder": ("self",),
        "features": ["Debit card (₹200 + GST a year)", "First 10 cheque leaves a year free", "Sweep into FD above ₹50,000 (optional)"],
        "charges": "SMS alerts ₹15 a quarter",
    },
    "salary": {
        "name": "Vetan Salary Package", "kind": "savings", "rate": 2.70, "minimum_balance": "Nil while salary is credited",
        "for": "Salaried employees whose salary is credited to the account", "holder": ("self",), "converts_existing": True,
        "features": ["₹20 lakh personal accident cover free", "₹30 lakh air accident cover free", "Overdraft up to 2 months' net salary",
                     "Free debit card, no SMS charges", "0.50% off personal loan processing fee"],
        "charges": "Nil",
        "rule": "Converts your main savings account; your employer keeps crediting the same account number",
    },
    "senior": {
        "name": "Varishth Savings (Senior Citizens)", "kind": "savings", "rate": 2.70, "minimum_balance": "Nil", "min_age": 60,
        "for": "Customers aged 60 and above", "holder": ("self",),
        "features": ["Doorstep banking free", "Free cheque book", "Priority at the branch"], "charges": "Nil",
    },
    "minor": {
        "name": "Pehla Kadam (minor, operated by guardian)", "kind": "savings", "rate": 2.70, "minimum_balance": "Nil",
        "for": "Children below 10 — operated by the parent", "holder": ("daughter",), "max_age": 10,
        "features": ["Photo debit card with ₹5,000 daily limit", "Cheque book in the guardian's name", "Pocket-money standing instruction"],
        "charges": "Nil",
    },
    "minor_self": {
        "name": "Pehli Udaan (minor, self-operated)", "kind": "savings", "rate": 2.70, "minimum_balance": "Nil",
        "for": "Children aged 10 to 18 — operated by the child", "holder": ("daughter",), "min_age": 10, "max_age": 18,
        "features": ["Debit card with ₹2,000 daily limit", "Internet banking view + limited payments"], "charges": "Nil",
    },
    "current": {
        "name": "Vyapar Current Account", "kind": "current", "rate": 0.0, "minimum_balance": "₹10,000 average a quarter (₹600 + GST if below)",
        "for": "Businesses, shops and professionals (side business, tuition classes)", "holder": ("self",),
        "features": ["Unlimited transactions", "Free cash deposit up to ₹2 lakh a month", "50 cheque leaves a month free"],
        "charges": "No interest. Shortfall in average balance ₹600 + GST a quarter",
        "rule": "Needs proof of the business (shop registration, GST or Udyam) at the branch within 30 days",
    },
}

# ---------------------------------------------------------------- bills (BBPS)

BILLER_CATEGORIES = {
    "electricity": "Electricity", "gas": "Piped gas", "lpg": "LPG cylinder", "water": "Water", "mobile_postpaid": "Mobile (postpaid)",
    "mobile_prepaid": "Mobile recharge (prepaid)", "broadband": "Broadband / landline", "dth": "DTH", "fastag": "FASTag recharge",
    "insurance": "Insurance premium", "municipal_tax": "Property / municipal tax", "education_fee": "School / college fees",
}
PREPAID_CATEGORIES = ("mobile_prepaid", "dth", "fastag")
BILLER_PROVIDERS = {
    "electricity": ["Lucknow Power Distribution Co", "Purvanchal Vidyut Board"], "gas": ["Awadh Gas Ltd"], "lpg": ["Bharat Gas Agency", "Indane Gas Agency"],
    "water": ["Lucknow Jal Sansthan"], "mobile_postpaid": ["Telco Postpaid"], "mobile_prepaid": ["Telco Prepaid"], "broadband": ["Lucknow Fibernet"],
    "dth": ["SkyView DTH"], "fastag": ["VNB FASTag"], "insurance": ["Jeevan Suraksha Insurance"], "municipal_tax": ["Lucknow Nagar Nigam"],
    "education_fee": ["Vidya Niketan Inter College"],
}
MOBILE_PLANS = [239, 299, 399, 719, 2999]


def billers_for(today: date) -> list[dict[str, Any]]:
    return [
        {"id": "BLR-01", "category": "electricity", "provider": "Lucknow Power Distribution Co", "consumer_number": "4471882301", "nickname": "Ghar ki bijli",
         "bill": {"amount": 2890, "due": (today + timedelta(days=6)).isoformat(), "period": today.strftime("%b %Y")}, "autopay": None},
        {"id": "BLR-02", "category": "gas", "provider": "Awadh Gas Ltd", "consumer_number": "1100478", "nickname": "Gas",
         "bill": {"amount": 1045, "due": (today + timedelta(days=12)).isoformat(), "period": today.strftime("%b %Y")}, "autopay": None},
        {"id": "BLR-03", "category": "mobile_prepaid", "provider": "Telco Prepaid", "consumer_number": "98XXXXX412", "nickname": "My mobile",
         "bill": None, "plan": 399, "validity_till": (today + timedelta(days=4)).isoformat(), "autopay": None},
        {"id": "BLR-04", "category": "broadband", "provider": "Lucknow Fibernet", "consumer_number": "LKF-220193", "nickname": "Wi-Fi",
         "bill": {"amount": 826, "due": (today + timedelta(days=3)).isoformat(), "period": today.strftime("%b %Y")}, "autopay": None},
        {"id": "BLR-05", "category": "fastag", "provider": "VNB FASTag", "consumer_number": "UP32KX4471", "nickname": "Dzire FASTag",
         "bill": None, "balance": 180, "autopay": None},
        {"id": "BLR-06", "category": "water", "provider": "Lucknow Jal Sansthan", "consumer_number": "LJS-11-90432", "nickname": "Water tax",
         "bill": {"amount": 2640, "due": (today + timedelta(days=40)).isoformat(), "period": f"FY {today.year}-{str(today.year + 1)[2:]}",
                  "rebate": "5% rebate if paid 30 days before the due date"}, "autopay": None},
    ]


def standing_for(today: date) -> list[dict[str, Any]]:
    return [
        {"id": "SI-01", "to_kind": "beneficiary", "to": "BEN-02", "to_label": "Kamla Devi (Amma)", "amount": 5000, "day": 7, "from_account": "SB-01",
         "start": add_months(today, -30).replace(day=7).isoformat(), "end": None, "remarks": "Monthly", "status": "active"},
        {"id": "SI-02", "to_kind": "deposit", "to": "RD-01", "to_label": "Recurring deposit RD-01", "amount": 3000, "day": 10, "from_account": "SB-01",
         "start": add_months(today, -22).replace(day=10).isoformat(), "end": None, "remarks": "RD instalment", "status": "active", "system": True},
    ]


# ---------------------------------------------------------------- mutual funds (VNB Mutual Fund — illustrative)

MF_SCHEMES: dict[str, dict[str, Any]] = {
    "liquid": {"name": "VNB Liquid Fund — Direct Growth", "category": "Debt — Liquid", "risk": "Low to moderate", "nav": 3412.57,
               "returns": {"1y": 6.9, "3y": 6.4, "5y": 5.4}, "expense_ratio": 0.18, "exit_load": "Graded, nil after 7 days", "lock_in": None,
               "min_lumpsum": 500, "min_sip": 500, "suits": "Parking money for days to months (better than savings interest)"},
    "gilt": {"name": "VNB Gilt Fund — Direct Growth", "category": "Debt — Gilt", "risk": "Moderate", "nav": 61.08,
             "returns": {"1y": 8.1, "3y": 6.9, "5y": 6.6}, "expense_ratio": 0.46, "exit_load": "Nil", "lock_in": None,
             "min_lumpsum": 1000, "min_sip": 500, "suits": "3+ years, government securities"},
    "balanced": {"name": "VNB Balanced Advantage Fund — Direct Growth", "category": "Hybrid — Dynamic asset allocation", "risk": "Moderately high", "nav": 28.44,
                 "returns": {"1y": 9.8, "3y": 11.2, "5y": 12.1}, "expense_ratio": 0.71, "exit_load": "1% within 1 year", "lock_in": None,
                 "min_lumpsum": 1000, "min_sip": 500, "suits": "3–5 years, first-time equity investors"},
    "nifty50": {"name": "VNB Nifty 50 Index Fund — Direct Growth", "category": "Equity — Index", "risk": "Very high", "nav": 214.36,
                "returns": {"1y": 11.6, "3y": 13.4, "5y": 15.2}, "expense_ratio": 0.18, "exit_load": "Nil", "lock_in": None,
                "min_lumpsum": 500, "min_sip": 500, "suits": "5+ years, low cost"},
    "flexicap": {"name": "VNB Flexi Cap Fund — Direct Growth", "category": "Equity — Flexi cap", "risk": "Very high", "nav": 96.71,
                 "returns": {"1y": 13.9, "3y": 16.0, "5y": 17.3}, "expense_ratio": 0.82, "exit_load": "1% within 1 year", "lock_in": None,
                 "min_lumpsum": 1000, "min_sip": 500, "suits": "7+ years"},
    "elss": {"name": "VNB Tax Saver (ELSS) Fund — Direct Growth", "category": "Equity — ELSS", "risk": "Very high", "nav": 412.90,
             "returns": {"1y": 12.8, "3y": 15.1, "5y": 16.4}, "expense_ratio": 0.97, "exit_load": "Nil", "lock_in": "3 years per instalment",
             "min_lumpsum": 500, "min_sip": 500, "suits": "Saving tax under 80C with the shortest lock-in (3 years)"},
}
MF_DISCLAIMER = "Mutual fund investments are subject to market risks; past returns are not a guarantee. Read the scheme documents. Figures are illustrative."

# ---------------------------------------------------------------- NPS, lockers, tax

NPS = {"min_contribution": 500, "min_opening": 1000, "exit_age": 60, "annuity_share": 40,
       "tax": "80CCD(1B): extra ₹50,000 deduction over the ₹1.5 lakh 80C limit (old regime); 60% tax-free lump sum at 60",
       "choices": {"auto_moderate": "Auto choice — Moderate (equity reduces with age)", "auto_conservative": "Auto choice — Conservative",
                   "active_50": "Active choice — 50% equity, 30% corporate bonds, 20% govt bonds"},
       "illustrative_return": 9.0}
LOCKERS = {"small": {"rent": 2000, "available": 0, "waitlist": 14}, "medium": {"rent": 4000, "available": 2, "waitlist": 0},
           "large": {"rent": 8000, "available": 1, "waitlist": 0}, "extra_large": {"rent": 12000, "available": 0, "waitlist": 6}}
LOCKER_RULE = ("Rent (+18% GST) is paid a year in advance. RBI rules: the bank may ask for a term deposit covering 3 years' rent and "
               "break-open charges; the locker must be operated at least once a year.")
ADVANCE_TAX_DUE = [("06-15", 15), ("09-15", 45), ("12-15", 75), ("03-15", 100)]
