"use client"

import * as React from "react"

import { checkTool } from "@/app/actions"
import { ToolForm } from "@/components/vnb/tool-form"
import { Row } from "@/components/vnb/ui"
import { dmy, inr } from "@/lib/format"

type Quote = { rate: number; maturity_amount: number; interest: number; maturity_date: string; tds_likely?: boolean; per_payout?: number | null; tax_saving_80c?: number; error?: string }

function useQuote(values: Record<string, string>, ready: boolean) {
  const [result, setResult] = React.useState<{ key: string; quote: Quote } | null>(null)
  const key = JSON.stringify(values)
  React.useEffect(() => {
    if (!ready) return
    let live = true
    const id = setTimeout(() => {
      void checkTool<Quote>("quote_deposit", JSON.parse(key)).then((q) => live && setResult({ key, quote: q as Quote }))
    }, 300)
    return () => {
      live = false
      clearTimeout(id)
    }
  }, [key, ready])
  return ready && result?.key === key ? result.quote : null
}

function QuoteLine({ quote }: { quote: Quote | null }) {
  if (!quote) return null
  if (quote.error) return <div className="gv-msg-err">{quote.error}</div>
  return (
    <div className="gv-msg-ok" data-testid="deposit-quote">
      Rate {quote.rate}% p.a. · Maturity value ₹{inr(quote.maturity_amount, false)} on {dmy(quote.maturity_date)} · Interest ₹{inr(quote.interest, false)}
      {quote.per_payout ? ` · Payout ₹${inr(quote.per_payout, false)} each time` : ""}
      {quote.tds_likely ? " · TDS likely" : ""}
      {quote.tax_saving_80c ? ` · 80C tax saving about ₹${inr(quote.tax_saving_80c, false)}` : ""}
    </div>
  )
}

/** Open an e-TDR / e-STDR — named like open_fixed_deposit's parameters, with a live quote. */
export function OpenFdForm() {
  const [values, setValues] = React.useState({ amount: "", scheme: "fd", tenure_months: "", tenure_days: "", payout: "cumulative" })
  const change = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setValues((v) => ({ ...v, [e.target.name]: e.target.value }))
  const ready = Boolean(values.amount) && (values.scheme !== "fd" || Boolean(values.tenure_months || values.tenure_days))
  const quote = useQuote({ kind: values.scheme, amount: values.amount, tenure_months: values.tenure_months, tenure_days: values.tenure_days, payout: values.payout }, ready)
  return (
    <ToolForm
      tool="open_fixed_deposit"
      name="Open fixed deposit"
      submitLabel="Proceed"
      booleans={["auto_renew"]}
      agree="I have read the terms and conditions for term deposits, including the penalty on premature withdrawal, and agree to them."
    >
      <Row label="Debit Account">30214457824821 — Savings Account</Row>
      <Row label="Deposit Scheme" required>
        <select name="scheme" value={values.scheme} onChange={change} className="gv-input">
          <option value="fd">e-TDR / e-STDR (Regular)</option>
          <option value="special">Vasundhara Utsav 444 days</option>
          <option value="tax_saver">VNB Tax Saver (5 years, 80C)</option>
        </select>
      </Row>
      <Row label="Amount (₹)" required hint="Minimum ₹1,000">
        <input name="amount" type="number" min={1000} value={values.amount} onChange={change} className="gv-input w-40" />
      </Row>
      <Row label="Tenure" hint="Give months OR days (7 days to 10 years). Ignored for the 444-day and tax saver schemes.">
        <input name="tenure_months" type="number" min={1} max={120} value={values.tenure_months} onChange={change} className="gv-input w-16" /> months or{" "}
        <input name="tenure_days" type="number" min={7} max={3650} value={values.tenure_days} onChange={change} className="gv-input w-20" /> days
      </Row>
      <Row label="Interest Payout">
        <select name="payout" value={values.payout} onChange={change} className="gv-input">
          <option value="cumulative">On maturity (STDR — cumulative)</option>
          <option value="quarterly">Quarterly (TDR)</option>
          <option value="monthly">Monthly (TDR, discounted)</option>
        </select>
      </Row>
      <Row label="Maturity Instruction">
        <label>
          <input type="checkbox" name="auto_renew" defaultChecked /> Auto-renew principal and interest for the same period
        </label>
      </Row>
      <tr>
        <td colSpan={2}>
          <QuoteLine quote={quote} />
        </td>
      </tr>
    </ToolForm>
  )
}

/** Open an e-RD — named like open_recurring_deposit's parameters. */
export function OpenRdForm() {
  const [values, setValues] = React.useState({ monthly_amount: "", tenure_months: "" })
  const change = (e: React.ChangeEvent<HTMLInputElement>) => setValues((v) => ({ ...v, [e.target.name]: e.target.value }))
  const quote = useQuote({ kind: "rd", monthly_amount: values.monthly_amount, tenure_months: values.tenure_months }, Boolean(values.monthly_amount && values.tenure_months))
  return (
    <ToolForm tool="open_recurring_deposit" name="Open recurring deposit" submitLabel="Proceed" agree="I authorise the bank to debit the monthly instalment from my savings account.">
      <Row label="Monthly Instalment (₹)" required hint="Minimum ₹100">
        <input name="monthly_amount" type="number" min={100} value={values.monthly_amount} onChange={change} className="gv-input w-32" />
      </Row>
      <Row label="Period (months)" required hint="12 to 120 months">
        <input name="tenure_months" type="number" min={12} max={120} value={values.tenure_months} onChange={change} className="gv-input w-20" />
      </Row>
      <tr>
        <td colSpan={2}>
          <QuoteLine quote={quote} />
        </td>
      </tr>
    </ToolForm>
  )
}

type Closure = { can_close: boolean; error?: string; payout?: number; rate_paid?: number; penalty?: number; you_give_up?: number; alternative?: string }

/** Premature closure — shows what is lost before the customer confirms. */
export function CloseFdForm({ deposits }: { deposits: { id: string; label: string }[] }) {
  const [id, setId] = React.useState("")
  const [quote, setQuote] = React.useState<{ id: string; q: Closure } | null>(null)
  React.useEffect(() => {
    if (!id) return
    let live = true
    void checkTool<Closure>("get_fd_closure_quote", { deposit_id: id }).then((q) => live && setQuote({ id, q: q as Closure }))
    return () => {
      live = false
    }
  }, [id])
  const q = quote?.id === id ? quote.q : null
  return (
    <ToolForm tool="close_fixed_deposit" name="Close deposit prematurely" submitLabel="Close Deposit" agree="I understand that interest will be paid at the reduced rate applicable for premature closure.">
      <Row label="Deposit Account" required>
        <select name="deposit_id" value={id} onChange={(e) => setId(e.target.value)} className="gv-input">
          <option value="">-- Select --</option>
          {deposits.map((d) => (
            <option key={d.id} value={d.id}>
              {d.label}
            </option>
          ))}
        </select>
      </Row>
      {q && (
        <tr>
          <td colSpan={2}>
            {q.can_close ? (
              <div className="gv-msg-info">
                Payout ₹{inr(q.payout ?? 0, false)} at {q.rate_paid}% (penalty {q.penalty}%). You give up ₹{inr(q.you_give_up ?? 0, false)} compared to maturity. {q.alternative}
              </div>
            ) : (
              <div className="gv-msg-err">{q.error}</div>
            )}
          </td>
        </tr>
      )}
    </ToolForm>
  )
}
