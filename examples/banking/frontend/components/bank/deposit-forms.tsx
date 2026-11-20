"use client"

import * as React from "react"
import { toast } from "sonner"

import { closeDeposit, openDeposit, quoteDeposit, type ActionResult } from "@/app/actions"
import { inputClass, panelClass, useResult } from "@/components/bank/use-result"
import { Button } from "@/components/ui/button"
import { longDate, rupees } from "@/lib/format"
import type { FdQuote } from "@/lib/types"

const TENURES = [3, 6, 12, 15, 24, 36, 60]

/** Open a fixed deposit with a live maturity quote. Field names match open_fixed_deposit. */
export function OpenDepositForm({ accounts }: { accounts: { id: string; label: string; balance: number }[] }) {
  const formRef = React.useRef<HTMLFormElement>(null)
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(openDeposit, null)
  const [values, setValues] = React.useState({ amount: "", tenure_months: "12", payout: "cumulative" })
  const [checked, setChecked] = React.useState<{ key: string; quote: FdQuote | null; error: string | null } | null>(null)
  useResult(state, "Deposit opened", () => {
    formRef.current?.reset()
    setValues({ amount: "", tenure_months: "12", payout: "cumulative" })
  })
  // Live quote for the current values; a result for older values is ignored.
  const current = values.amount && values.tenure_months && checked?.key === JSON.stringify(values) ? checked : null
  const quote = current?.quote ?? null
  const quoteError = current?.error ?? null
  React.useEffect(() => {
    if (!values.amount || !values.tenure_months) return
    let live = true
    const id = setTimeout(() => {
      void quoteDeposit(values).then((r) => {
        if (live) setChecked({ key: JSON.stringify(values), quote: r.ok ? r.quote : null, error: r.ok ? null : r.error })
      })
    }, 300)
    return () => {
      live = false
      clearTimeout(id)
    }
  }, [values])
  const change = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setValues((v) => ({ ...v, [e.target.name]: e.target.value }))

  return (
    <form ref={formRef} action={action} className={panelClass} data-relay-form="Open a fixed deposit" aria-label="Open a fixed deposit">
      <h2 className="font-semibold">Open a fixed deposit</h2>
      <div className="grid grid-cols-2 gap-3">
        <label className="col-span-2 flex flex-col gap-1 text-sm">
          Amount (₹)
          <input name="amount" type="number" min={10000} step={1000} value={values.amount} onChange={change} required className={inputClass} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Tenure (months)
          <input name="tenure_months" type="number" min={1} max={120} list="fd-tenures" value={values.tenure_months} onChange={change} required className={inputClass} />
          <datalist id="fd-tenures">
            {TENURES.map((t) => (
              <option key={t} value={t} />
            ))}
          </datalist>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Interest
          <select name="payout" value={values.payout} onChange={change} className={inputClass}>
            <option value="cumulative">At maturity</option>
            <option value="quarterly">Paid quarterly</option>
          </select>
        </label>
        <label className="col-span-2 flex flex-col gap-1 text-sm">
          From
          <select name="from_account" defaultValue="ACC-01" className={inputClass}>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label} — {rupees(a.balance)}
              </option>
            ))}
          </select>
        </label>
        <label className="col-span-2 flex items-center gap-2 text-sm">
          <input type="checkbox" name="auto_renew" className="accent-[var(--primary)]" /> Renew automatically at maturity
        </label>
      </div>
      {quote && (
        <p className="rounded-xl bg-muted/60 p-3 text-sm" aria-live="polite">
          {quote.rate}% a year · matures {longDate(quote.maturity_date)}
          <br />
          {quote.payout === "quarterly" ? (
            <>
              <span className="font-medium">{rupees(quote.quarterly_interest ?? 0)}</span> every quarter, {rupees(quote.principal)} back at maturity
            </>
          ) : (
            <>
              You get <span className="font-medium">{rupees(quote.maturity_amount)}</span> ({rupees(quote.total_interest)} interest)
            </>
          )}
        </p>
      )}
      {quoteError && <p className="text-sm text-destructive">{quoteError}</p>}
      <Button type="submit" disabled={pending} className="self-start">
        Open deposit
      </Button>
    </form>
  )
}

export function CloseDepositButton({ id, payout }: { id: string; payout: number }) {
  const [pending, start] = React.useTransition()
  return (
    <Button
      variant="outline"
      size="sm"
      disabled={pending}
      onClick={() => {
        if (!window.confirm(`Close ${id} early? You'll get ${rupees(payout)} now, with a 1% lower rate.`)) return
        start(async () => {
          const res = await closeDeposit(id)
          if (res.ok) toast.success(res.message ?? "Deposit closed")
          else toast.error(res.error)
        })
      }}
    >
      Close early
    </Button>
  )
}
