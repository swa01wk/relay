/** Shapes the bank API returns (see tools/src/vnb_api/logic.py). Only the fields the site shows. */

export type Kyc = { last_updated: string; due_date: string; overdue: boolean; status: string; restriction_date: string | null; how: string }

export type FamilyMember = { name: string; relation: string; dob: string; age: number }

export type MyContext = {
  bank: string
  today: string
  customer: {
    name: string
    cif: string
    username: string
    dob: string
    mobile: string
    email: string
    address: string
    branch: string
    branch_code: string
    ifsc: string
    occupation: string
    net_monthly_income: number
    cibil_score: number
  }
  age: number
  family: FamilyMember[]
  kyc: Kyc
  savings_balance: number
  deposits_total: number
  ppf_balance: number
  loans_outstanding: number
  monthly_emis: number
  alerts: string[]
}

export type AccountRow = {
  id: string
  type: string
  number: string
  masked: string
  branch?: string
  balance: number
  available?: number
  rate?: number
  maturity?: string
  emi?: number
  next_emi_date?: string
  lien?: number
  status: string
}

export type Txn = {
  id: string
  date: string
  narration: string
  ref: string
  amount: number
  direction: "debit" | "credit"
  balance_after: number
  debit: number | null
  credit: number | null
  category: string
  counterparty: string
}

export type Statement = { from_date: string | null; to_date: string; count: number; total_credits: number; total_debits: number; transactions: Txn[] }

export type Beneficiary = {
  id: string
  name: string
  nickname: string
  bank: string
  branch: string
  ifsc: string
  limit: number
  account_masked: string
  within_vnb: boolean
  status: "active" | "cooling"
  active_from_display: string
}

export type TransferQuote = {
  can_send?: boolean
  error?: string
  problems?: string[]
  mode?: string
  mode_label?: string
  modes_available?: string[]
  arrives?: string
  amount?: number
  balance_after?: number
  daily_limit_left_after?: number
  beneficiary?: { name: string; bank: string; account_masked: string }
}

export type LoanProduct = {
  product: string
  name: string
  for: string[]
  rates_by_cibil: Record<string, number> | null
  your_rate: number | null
  max_tenure_months: number | null
  amount: string
  processing_fee: string
  prepayment: string
  collateral: string
  turnaround: string
  notes: string[]
}

export type Loan = {
  id: string
  name: string
  number: string
  sanctioned: number
  rate: number
  emi: number
  outstanding: number
  next_emi_date: string
  emis_paid: number
  emis_left: number
  ends: string | null
  vehicle?: string | null
  security?: string | null
  status: string
}

export type LoanApplication = { id: string; name: string; amount: number; tenure_months: number; rate: number; emi: number; submitted: string; status: string; documents: string[] }

export type Deposit = {
  id: string
  kind: "fd" | "tax_saver" | "rd"
  scheme: string
  number: string
  principal: number | null
  monthly: number | null
  rate: number
  opened: string
  maturity: string
  payout: string | null
  lien: number | null
  status: string
  current_value: number
  maturity_amount: number
  days_to_maturity: number
}

export type DepositRates = {
  fixed_deposit_slabs: { tenure: string; general: number; senior_citizen: number }[]
  special_scheme: { name: string; days: number; rate: number; senior_citizen: number; valid_till: string }
  tax_saver: { name: string; rate: number; senior_citizen: number; lock_in: string }
  savings_bank: number
  small_savings: Record<string, { name: string; rate: number; tax: string }>
  premature_closure: string
  tds: string
}

export type Scheme = {
  scheme: string
  name: string
  kind: string
  summary: string
  premium_per_year?: number | null
  cover?: number | null
  eligible: boolean
  why_not?: string | null
  enrolled: boolean
}

export type ServiceRequest = { id: string; kind: string; summary: string; raised: string; status: string; expected_by: string | null; charge: number }

export type Complaint = { id: string; category_label: string; description: string; transaction_id: string | null; raised: string; status: string; resolve_by: string; docket: string }

export type Card = {
  id: string
  network: string
  number_masked: string
  status: string
  atm_daily_limit: number
  pos_daily_limit: number
  international: boolean
  expiry: string
  expected_by?: string
}

export type InterestCertificate = {
  financial_year: string
  period: string
  savings_interest: number
  deposit_interest: { deposit: string; scheme: string; interest: number }[]
  deposit_interest_total: number
  tds_deducted_or_due: number
  deduction_80tta: number
  notes: string[]
}

export type AccountProduct = {
  product: string
  name: string
  kind: string
  for: string
  interest_rate: number
  minimum_balance: string
  features: string[]
  charges: string
  rule: string | null
  eligible: boolean
  why_not: string | null
  holder: string
}

export type Bill = { amount: number; due: string; period: string; rebate?: string }

export type Biller = {
  id: string
  category: string
  category_label: string
  provider: string
  consumer_number: string
  nickname: string
  bill: Bill | null
  plan: number | null
  validity_till: string | null
  balance: number | null
  autopay: { max_amount: number; from_account: string } | null
  last_paid: { amount: number; date: string; ref: string } | null
  prepaid: boolean
  days_to_due?: number
}

export type StandingInstruction = {
  id: string
  to_label: string
  amount: number
  day: number
  from_account: string
  start: string
  end: string | null
  remarks: string
  status: string
  system: boolean | null
  next_on: string | null
}

export type TaxGuide = {
  assessment_year: string
  other_income_estimate: number
  tax_on_other_income: number
  advance_tax_needed: boolean
  advice: string
  due_dates: { due: string; cumulative_percent: number }[]
}

export type TaxPayment = { id: string; label: string; assessment_year: string; amount: number; paid_on: string; cin: string; bsr_code: string; minor_head: string }

export type MfScheme = {
  scheme: string
  name: string
  category: string
  risk: string
  nav: number
  returns: Record<string, number>
  expense_ratio: number
  exit_load: string
  lock_in: string | null
  min_lumpsum: number
  min_sip: number
  suits: string
}

export type MfHolding = {
  id: string
  scheme: string
  name: string
  folio: string
  units: number
  nav: number
  value: number
  invested: number
  gain: number
  sip: { amount: number; day: number } | null
  locked_units: number
  redeemable_value: number
}

export type NpsDetails = {
  account: { pran: string; tier: string; choice: string; contributed: number; this_fy: number; opened: string; nominee: string } | null
  rules: { choices: Record<string, string>; tax: string; min_opening: number; min_contribution: number }
  your_age: number
  years_to_60: number
  tax_saving_per_year: number
}

export type LockerInfo = {
  branch: string
  sizes: { size: string; rent_per_year: number; rent_with_gst: number; available: number; waitlist: number }[]
  rule: string
  yours: { id: string; size: string; status: string; locker_number?: string; position?: number; since: string; renews?: string }[]
}

export type NomineeRow = { account_id: string; account: string; nominee: string }
