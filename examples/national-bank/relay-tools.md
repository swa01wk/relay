# Vasundhara National Bank — Relay inventory and coverage

Built by the workflow in the SDK's `AGENTS.md`: every page, write and entity of the portal mapped to a tool, a screen action, or
an exclusion. Tools: `tools/src/vnb_api/tools.py` (one table → `GET /tools` and the site's `/api/<tool>`).

**Counts:** 20 pages + a CSV download · 35 writes (server action → bank API) · 18 entities → **69 tools** (34 read,
35 side-effecting) · **3 screen actions** + automatic navigation and page forms (at most 6 per page).

## Pages

| Page | What is on it | Assistant reaches it with |
|---|---|---|
| `/` Landing | Login boxes, menu bar with dropdowns, notices, link farm, promotions | `NAVIGATE` |
| `/login` Login | Username, password, captcha, virtual keyboard, instructions (demo: prefilled) | `NAVIGATE` (not a page form: it has a password field) |
| `/home` Account Summary | Messages (KYC overdue, cooling beneficiaries), accounts by type, last 5 transactions | `NAVIGATE` |
| `/statement` Account Statement | Period (range / last N), type, amount, narration filter; passbook table with totals | **`SHOW_STATEMENT`** (the filter form is `data-relay-ignore`) |
| `/transfers` Payments / Transfers | Funds transfer form with live check; own-account transfer; daily limit; beneficiaries (Delete); Add beneficiary | **`START_TRANSFER`**, page forms |
| `/loans` Loans | Rate table for 7 products, my loans and applications, EMI calculator, prepayment, Apply | **`SHOW_LOAN_PRODUCT`**, page forms "EMI calculator", "Loan prepayment", "Apply for loan" |
| `/deposits` Deposits | Rate table, my deposits, Open FD (live quote), Open RD, Premature closure (shows the loss) | `NAVIGATE`, page forms "Open fixed deposit", "Open recurring deposit", "Close deposit prematurely" |
| `/schemes` Government Schemes | Schemes with the customer's eligibility, PMJJBY/PMSBY enrolment, SSY, PPF deposit | `NAVIGATE`, page forms |
| `/services` e-Services | Re-KYC, cheque book, stop cheque, Positive Pay, cheque status, debit card limits and block, interest certificate, request status | `NAVIGATE`, six page forms |
| `/complaints` Requests & Enquiries | Lodge complaint, track status | `NAVIGATE`, page form "Lodge complaint" |
| `/profile` Profile | Personal details, KYC, nominees of every account and deposit, Register / change nominee, family | `NAVIGATE`, page form "Update nominee" |
| `/open-account` Open Account | Account products with the customer's eligibility, Open account, Close an additional account | `NAVIGATE`, page forms |
| `/bills` Bill Payments | Billers with dues, Pay bill / recharge, Auto pay, Register biller | `NAVIGATE`, page forms |
| `/standing-instructions` | Standing instructions, Create, Cancel | `NAVIGATE`, page forms |
| `/tax` e-Tax | Advance-tax check and due dates, Pay challan 280, Form 15G/15H, challans paid | `NAVIGATE`, page forms |
| `/mutual-funds` Mutual Funds | Schemes (risk, returns, costs), holdings, Invest (lumpsum / SIP), Redeem / stop SIP | `NAVIGATE`, page forms |
| `/nps` NPS | NPS account or Open NPS, Contribute | `NAVIGATE`, page forms |
| `/locker` Locker | Sizes, rent, availability / waiting list, Apply | `NAVIGATE`, page form |
| `/change-password` | Change login / profile password (site only) | `NAVIGATE` (not a page form: password fields) |
| `/statement/download` | The filtered statement as CSV | link on the statement page |
| `/info/…` | "Visit your branch" pages behind the decorative links | excluded from navigation |

## Writes (server actions in `frontend/app/actions.ts` → bank API → `logic.py`)

| Where | In the customer's words | Tool (read first) |
|---|---|---|
| Funds transfer | "Send the rent to my house owner" | `transfer_funds` (`get_transfer_quote`) |
| Add / delete beneficiary | "Add my electrician, account …, IFSC …" | `add_beneficiary`, `delete_beneficiary` |
| Apply for loan | "Take ₹1.5 lakh against my FD" | `apply_for_loan` (`recommend_loans`) |
| Loan prepayment | "Pay ₹1 lakh extra on the car loan" | `prepay_loan` (`get_prepayment_quote`) |
| Open FD / RD | "Put ₹1 lakh in the 444-day scheme" | `open_fixed_deposit`, `open_recurring_deposit` (`quote_deposit`) |
| Premature closure | "Break my FD" | `close_fixed_deposit` (`get_fd_closure_quote`) |
| PMJJBY / PMSBY | "Get me the ₹436 insurance" | `enroll_in_scheme` (`list_government_schemes`) |
| SSY / PPF | "Open Sukanya for Ananya", "Put ₹20,000 in PPF" | `open_ssy_account`, `deposit_to_ppf` |
| Cheque book / stop cheque | "Order a cheque book", "Stop cheque 512320" | `request_cheque_book`, `stop_cheque` |
| Debit card | "Turn on international use", "Block my card, it's lost" | `update_debit_card_usage`, `block_debit_card` (`get_debit_card`) |
| Re-KYC | "Do my KYC, nothing changed" | `submit_kyc_declaration` |
| Complaint | "I was charged ₹590 wrongly" | `raise_complaint` (`get_transaction`) |

| Open / close account | "Open an account for my daughter" / "Close the extra account" | `open_account` (`list_account_products`), `close_account` |
| Own account transfer, daily limit | "Move ₹5,000 to Ananya's account", "Lower my limit to ₹50,000" | `transfer_between_own_accounts`, `set_transfer_limit` |
| Pay bill / autopay / register biller | "Pay the electricity bill", "Recharge my phone ₹399", "Autopay the Wi-Fi" | `pay_bill`, `set_bill_autopay`, `add_biller` (`list_billers`) |
| Standing instructions | "Send ₹500 pocket money every 1st" | `create_standing_instruction`, `cancel_standing_instruction` |
| Tax | "Do I need to pay advance tax?", "Pay ₹6,200 self-assessment tax" | `pay_tax` (`get_tax_payment_guide`), `submit_form_15g_15h` |
| Mutual funds, NPS | "Start a ₹5,000 ELSS SIP", "Open NPS" | `invest_in_mutual_fund`, `redeem_mutual_fund`, `open_nps_account`, `contribute_to_nps` |
| Locker, nominee, Positive Pay | "Get me a locker", "Make my daughter the FD nominee", "I issued cheque 512316 for ₹75,000" | `apply_for_locker`, `update_nominee`, `register_positive_pay` |

**Excluded:** login, OTPs, PINs, passwords and full card numbers (the assistant never asks for them; Change Password is
site-only); UPI settings, demat / IPO, sovereign gold bonds (decorative); `/sandbox/reset` and `/health` (operator endpoints).

## Entities and their tools

| Entity | Tools |
|---|---|
| Customer (profile, family, KYC, alerts) | `get_my_context`, `submit_kyc_declaration` |
| Accounts (savings, PPF, SSY) | `get_account_summary`, `get_account_details`, `deposit_to_ppf`, `open_ssy_account` |
| Statement lines | `get_account_statement`, `get_transaction`, `summarize_spending` |
| Beneficiaries and transfers | `list_beneficiaries`, `add_beneficiary`, `delete_beneficiary`, `get_transfer_quote`, `transfer_funds` |
| Loan products and loans | `list_loan_products`, `recommend_loans`, `calculate_emi`, `apply_for_loan`, `list_my_loans`, `get_prepayment_quote`, `prepay_loan` |
| Deposits | `get_deposit_rates`, `quote_deposit`, `list_deposits`, `compare_savings_options`, `open_fixed_deposit`, `open_recurring_deposit`, `get_fd_closure_quote`, `close_fixed_deposit` |
| Government schemes | `list_government_schemes`, `enroll_in_scheme` |
| Debit card | `get_debit_card`, `update_debit_card_usage`, `block_debit_card` |
| Service requests, complaints | `request_cheque_book`, `stop_cheque`, `list_service_requests`, `raise_complaint` |
| Tax | `get_interest_certificate` |
| Account products, extra accounts | `list_account_products`, `open_account`, `close_account`, `transfer_between_own_accounts`, `set_transfer_limit` |
| Billers, standing instructions | `list_billers`, `add_biller`, `pay_bill`, `set_bill_autopay`, `list_standing_instructions`, `create_standing_instruction`, `cancel_standing_instruction` |
| Tax payments | `get_tax_payment_guide`, `pay_tax`, `list_tax_payments`, `submit_form_15g_15h` |
| Mutual funds, NPS | `list_mutual_funds`, `invest_in_mutual_fund`, `list_mf_holdings`, `redeem_mutual_fund`, `get_nps_details`, `open_nps_account`, `contribute_to_nps` |
| Lockers, nominees, cheques | `get_locker_availability`, `apply_for_locker`, `list_nominees`, `update_nominee`, `get_cheque_status`, `register_positive_pay` |
| Rules | `describe_bank_rules` |

## Test questions

1. I need ₹2 lakh for my mother's surgery — which loan is best for me? → loan against FD-01 (8%), personal loan runner-up; asks about gold.
2. I want to buy a car for ₹9.5 lakh, loan of ₹8 lakh → car loan at 9.40%; FD too small.
3. Can I get a home loan of ₹40 lakh for a ₹45 lakh flat? → up to ₹36 lakh (80% LTV), tenure ends by 70.
4. My daughter wants to study engineering, ₹6 lakh → education loan, 0.50% lower for a girl student.
5. Where should I save ₹5,000 a month for 10 years? → SSY for Ananya (before 20 June), then PPF; FD after tax last.
6. Should I prepay my car loan with ₹1 lakh or open an FD? → prepay: 9.2% vs 5.6% after tax.
7. What if I break my FD now? → payout, penalty 0.5%, what is lost; suggests a loan against it instead.
8. What is the ₹590 charge? / What is "ACH DR"? / Why ₹236 in September? → decoded narrations and the rule.
9. Show me all charges this year → `SHOW_STATEMENT` with query "CHGS".
10. How much did I spend on groceries in the last 3 months? → chart from `summarize_spending`.
11. Send ₹14,000 rent to my house owner → `START_TRANSFER` (IMPS) or proposal.
12. Pay Mohit Electricals ₹5,000 → cooling period: from 4 hours after adding.
13. Send ₹2.5 lakh to my brother by RTGS → over the balance.
14. My KYC is overdue — what do I do? → self-declaration, proposed.
15. Which government schemes can I join? → PMJJBY, PMSBY, SSY yes; APY no (age, taxpayer).
16. Enrol me in PMJJBY with my wife as nominee → proposal, ₹436.
17. I lost my debit card → block (permanent, ₹354 for a new card) and complaint advice.
18. Order a cheque book of 25 leaves → ₹71 (10 free).
19. How much tax will I pay on my FD interest this year? / Do I need Form 15G? → interest certificate, no TDS, 15G not applicable.
20. Which FD gives the best return for 1 year? → rate table: 444-day special at 7.25%.
21. I want to open an account for my daughter → minor account (Pehla Kadam), not the self-operated one (she is 9).
22. Should I open a zero-balance account? → not allowed beside his savings account; suggests converting to the salary package (free ₹20 lakh accident cover).
23. Which bills are due? Pay the Wi-Fi and put it on autopay → `list_billers`, pay ₹826, autopay up to a cap.
24. Recharge my mobile → asks for a plan (₹239–₹2,999); FASTag balance is low.
25. Send my mother ₹5,000 every month → already a standing instruction (SI-01).
26. Do I need to pay advance tax? Can I submit Form 15G? → no advance tax (≈ ₹7,000); 15G refused (income taxable).
27. Start a ₹5,000 monthly SIP to save tax → ELSS (3-year lock-in) vs PPF / NPS, with the market-risk note.
28. Is a locker available? → small: waiting list; medium: available at ₹4,720 a year.
29. Who is the nominee on my PPF? → none registered; offers to add one (a minor needs a guardian).
30. I gave cheque 512316 for ₹75,000 to my electrician → Positive Pay.
