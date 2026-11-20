/** Shapes returned by the bank API (examples/banking/tools/src/bank_api/logic.py). */

export const CATEGORIES = {
  income: "Income",
  rent: "Rent",
  groceries: "Groceries",
  dining: "Food & dining",
  shopping: "Shopping",
  transport: "Transport",
  fuel: "Fuel",
  utilities: "Bills & utilities",
  subscriptions: "Subscriptions",
  health: "Health",
  entertainment: "Entertainment",
  travel: "Travel",
  education: "Education",
  family: "Family",
  investments: "Investments",
  cash: "Cash",
  transfers: "Transfers",
  card_payment: "Card payment",
  interest: "Interest",
  fees: "Fees & charges",
  refunds: "Refunds",
} as const

export const CHANNELS = {
  upi: "UPI",
  imps: "IMPS",
  neft: "NEFT",
  own: "Own account transfer",
  card: "Card",
  atm: "ATM",
  bill_pay: "Bill payment",
  auto_debit: "Auto debit",
  interest: "Interest",
  fd: "Fixed deposit",
  card_payment: "Card bill payment",
  fee: "Fee",
  refund: "Refund",
} as const

export const DISPUTE_REASONS = {
  unauthorized: "I didn't make this transaction",
  charged_twice: "Charged twice",
  wrong_amount: "Charged the wrong amount",
  not_received: "Paid but didn't get the goods or service",
  refund_not_received: "Refund promised but not received",
  other: "Something else",
} as const

export const REPORT_REASONS = { lost: "Lost", stolen: "Stolen", damaged: "Damaged" } as const

export type Direction = "debit" | "credit"

export type Account = {
  id: string
  name: string
  type: string
  number_masked: string
  label: string
  balance: number
  holders: string[]
  min_balance: number
  money_in_this_month: number
  money_out_this_month: number
}

export type AccountDetail = Account & {
  account_number: string
  ifsc: string
  branch: string
  interest_rate: number
  nominee: string | null
  opened: string
  below_min_balance: boolean
  cards: { id: string; name: string; last4: string; status: string }[]
  scheduled_transfers: Scheduled[]
  recent_transactions: Txn[]
}

export type Txn = {
  id: string
  account_id: string
  account: string
  posted_at: string
  direction: Direction
  amount: number
  description: string
  category: keyof typeof CATEGORIES
  category_label: string
  channel: keyof typeof CHANNELS
  reference: string
  merchant: string | null
  balance_after?: number
  possible_duplicate?: boolean
  payee_id?: string
  biller_id?: string
  deposit_id?: string
  dispute_id?: string
  note?: string
}

export type TxnDetail = Txn & {
  payee?: Payee | null
  dispute: Dispute | null
  can_dispute: boolean
  dispute_note: string
  possible_duplicate_of?: string[]
}

export type TxnList = { transactions: Txn[]; total: number; money_in: number; money_out: number }

export type Payee = {
  id: string
  name: string
  nickname: string | null
  kind: "bank" | "upi"
  label: string
  added_at: string
  upi_id?: string
  account_masked?: string
  ifsc?: string
  bank?: string
  cooling_until?: string
  last_paid?: { amount: number; date: string } | null
}

export type Scheduled = {
  id: string
  from_account: string
  from_label: string
  to: string
  to_label: string
  amount: number
  note: string | null
  repeat: "once" | "monthly"
  next_date: string | null
  status: "active" | "completed" | "failed" | "cancelled"
  last_runs: { date: string; ok: boolean; error?: string }[]
}

export type Biller = {
  id: string
  name: string
  category: string
  nickname: string
  consumer_number: string
  autopay: { enabled: boolean; from_account: string; max_amount: number }
  last_paid: { amount: number; date: string } | null
  bill: { amount: number; due_date: string; bill_date: string; days_left: number; status: "due" | "overdue"; autopay_skipped?: string } | null
}

export type CardStatement = {
  statement_date: string
  statement_balance: number
  minimum_due: number
  due_date: string
  total_due_now: number
  minimum_due_now: number
  status: "paid" | "due" | "minimum_paid" | "overdue"
}

export type Card = {
  id: string
  kind: "debit" | "credit"
  name: string
  network: string
  last4: string
  expires: string
  status: "active" | "locked" | "blocked" | "on_the_way"
  label: string
  controls: { online: boolean; international: boolean; contactless: boolean; atm?: boolean }
  limits: { atm_daily?: number; pos_daily: number; online_daily: number }
  arrives_on?: string
  replaced_by?: string
  replaces?: string
  blocked_reason?: string
  account_id?: string
  account_label?: string
  account_balance?: number
  credit_limit?: number
  outstanding?: number
  available_credit?: number
  reward_points?: number
  statement?: CardStatement
  unbilled?: number
  unbilled_transactions?: Txn[]
  recent_transactions?: Txn[]
  limit_maximums?: Record<string, number>
}

export type FullStatement = CardStatement & {
  period_from: string
  period_to: string
  opening_balance: number
  purchases: number
  payments_and_refunds: number
  paid_since_statement: number
  transactions: Txn[]
}

export type Deposit = {
  id: string
  principal: number
  rate: number
  opened: string
  tenure_months: number
  maturity_date: string
  payout: "cumulative" | "quarterly"
  auto_renew: boolean
  account_id: string
  status: "active" | "matured" | "closed"
  interest_paid: number
  maturity_amount: number
  total_interest: number
  quarterly_interest?: number
  days_to_maturity?: number
  closed_on?: string
  paid_out?: number
  renewed_as?: string
}

export type FdRates = { rates: { from_days: number; to_days: number; rate: number }[]; minimum: number; premature_penalty: string }

export type FdQuote = { principal: number; rate: number; tenure_months: number; maturity_date: string; payout: string; maturity_amount: number; total_interest: number; quarterly_interest?: number }

export type Dispute = {
  id: string
  transaction_id: string
  reason: keyof typeof DISPUTE_REASONS
  details: string | null
  amount: number
  merchant: string
  status: "under_review" | "resolved" | "rejected"
  raised_at: string
  expected_by: string
  provisional_credit: number
}

export type AttentionItem = { kind: string; ref: string; href: string; text: string }

export type MyContext = {
  customer: { name: string; email: string; phone: string; city: string; customer_number: string; branch: string; customer_since: string; relationship_manager: string }
  accounts: { id: string; name: string; label: string; balance: number }[]
  total_balance: number
  cards: { id: string; kind: string; label: string; status: string }[]
  payees: number
  next_scheduled_transfer: Scheduled | null
  today: string
}

export type MonthSummary = {
  month: string
  income: number
  spending: number
  invested: number
  saved: number
  savings_rate_pct: number | null
  spending_last_month: number
  change_vs_last_month_pct: number | null
  top_categories: { category: string; amount: number }[]
  top_merchants: { merchant: string; amount: number }[]
  biggest_expense: Txn | null
  partial_month: boolean
}

export type CashFlow = { months: { month: string; income: number; spending: number; invested: number; net: number }[] }

export type Aggregate = { groups: { group: string; value: number; count: number }[]; total: number }

export type TransferQuote = {
  can_send: boolean
  error?: string
  fields?: Record<string, string>
  mode?: string
  mode_label?: string
  arrives?: string
  to_label?: string
  from_label?: string
  amount?: number
  balance_after?: number
  daily_limit_left_after?: number
  warnings?: string[]
}
