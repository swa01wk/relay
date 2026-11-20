"use client"

import * as React from "react"
import { CheckCircle2Icon, Loader2Icon, TriangleAlertIcon } from "lucide-react"

import { quoteTransfer, sendMoney, type ActionResult } from "@/app/actions"
import { inputClass, useResult } from "@/components/bank/use-result"
import { Button } from "@/components/ui/button"
import { rupees, todayIst } from "@/lib/format"
import type { Payee, TransferQuote } from "@/lib/types"

type Initial = Partial<Record<"to" | "amount" | "from_account" | "mode" | "note" | "transfer_date" | "repeat", string>>

/**
 * Send money. Named like the transfer_money tool's fields on purpose: the assistant fills this
 * page form ("send Rohan 1,500 for dinner") and the page checks it live — only the customer presses Send.
 */
export function TransferForm({ payees, accounts, initial }: { payees: Payee[]; accounts: { id: string; label: string; balance: number }[]; initial: Initial }) {
  const formRef = React.useRef<HTMLFormElement>(null)
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(sendMoney, null)
  const [checked, setChecked] = React.useState<{ key: string; quote: TransferQuote } | null>(null)
  const [values, setValues] = React.useState({ to: initial.to ?? "", amount: initial.amount ?? "", from_account: initial.from_account ?? "ACC-01", mode: initial.mode ?? "" })
  const [later, setLater] = React.useState(Boolean(initial.transfer_date) || initial.repeat === "monthly")
  useResult(state, "Money sent", () => {
    formRef.current?.reset()
    setValues((v) => ({ ...v, to: "", amount: "" }))
  })

  // The live check: fetched for the current values; a result for older values is ignored.
  const valuesKey = JSON.stringify(values)
  const quote = values.to && values.amount && checked?.key === valuesKey ? checked.quote : null
  React.useEffect(() => {
    if (!values.to || !values.amount) return
    let live = true
    const id = setTimeout(() => {
      void quoteTransfer({ ...values, mode: values.mode || undefined }).then((q) => live && setChecked({ key: JSON.stringify(values), quote: q }))
    }, 300)
    return () => {
      live = false
      clearTimeout(id)
    }
  }, [values])

  const change = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setValues((v) => ({ ...v, [e.target.name]: e.target.value }))
  const err = (name: string) => state?.fields?.[name]
  const own = accounts.filter((a) => a.id !== values.from_account)
  const isBankPayee = payees.find((p) => p.id === values.to)?.kind === "bank"

  return (
    <form ref={formRef} action={action} className="flex flex-col gap-5 rounded-2xl border bg-card p-5" data-relay-form="Send money" aria-label="Send money">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm">
          From
          <select name="from_account" value={values.from_account} onChange={change} className={inputClass}>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label} — {rupees(a.balance)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          To
          <select name="to" value={values.to} onChange={change} required aria-invalid={Boolean(err("to")) || undefined} className={inputClass}>
            <option value="">Choose a payee or account</option>
            <optgroup label="Payees">
              {payees.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                  {p.nickname ? ` (${p.nickname})` : ""} — {p.kind === "upi" ? p.upi_id : `${p.bank} ${p.account_masked}`}
                </option>
              ))}
            </optgroup>
            <optgroup label="My accounts">
              {own.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label}
                </option>
              ))}
            </optgroup>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Amount (₹)
          <input name="amount" type="number" min={1} step={1} inputMode="numeric" value={values.amount} onChange={change} required aria-invalid={Boolean(err("amount")) || undefined} className={inputClass} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Send by
          <select name="mode" value={values.mode} onChange={change} className={inputClass} disabled={!isBankPayee}>
            <option value="">Automatic</option>
            <option value="imps">IMPS — instant</option>
            <option value="neft">NEFT — within 30 minutes</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm sm:col-span-2">
          Note
          <input name="note" maxLength={60} defaultValue={initial.note} placeholder="Shows on your statement, like “Rent”" className={inputClass} />
        </label>
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={later} onChange={(e) => setLater(e.target.checked)} className="accent-[var(--primary)]" /> Schedule for later or repeat monthly
      </label>
      {later && (
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm">
            Date
            <input type="date" name="transfer_date" min={todayIst()} defaultValue={initial.transfer_date ?? todayIst()} className={inputClass} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Repeat
            <select name="repeat" defaultValue={initial.repeat ?? "once"} className={inputClass}>
              <option value="once">Once</option>
              <option value="monthly">Every month</option>
            </select>
          </label>
        </div>
      )}

      {quote && (
        <div className={quote.can_send ? "rounded-xl bg-muted/60 p-3 text-sm" : "rounded-xl bg-destructive/10 p-3 text-sm text-destructive"} aria-live="polite" data-testid="transfer-check">
          {quote.can_send ? (
            <div className="flex flex-col gap-1">
              <span className="flex items-center gap-1.5 font-medium">
                <CheckCircle2Icon className="size-4 text-emerald-600" /> {rupees(quote.amount ?? 0)} to {quote.to_label} by {quote.mode_label}, arrives {quote.arrives}
              </span>
              <span className="text-muted-foreground">
                Balance after: {rupees(quote.balance_after ?? 0)}
                {quote.daily_limit_left_after !== undefined && ` · ${rupees(quote.daily_limit_left_after)} of today's transfer limit left`}
              </span>
              {quote.warnings?.map((w) => (
                <span key={w} className="flex items-center gap-1.5 text-amber-700">
                  <TriangleAlertIcon className="size-4" /> {w}
                </span>
              ))}
            </div>
          ) : (
            <span className="flex items-center gap-1.5">
              <TriangleAlertIcon className="size-4" /> {quote.error}
            </span>
          )}
        </div>
      )}
      {state?.error && (
        <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
          {state.error}
        </p>
      )}
      <Button type="submit" size="lg" disabled={pending || (quote !== null && !quote.can_send && !later)} data-testid="send-money" className="self-start">
        {pending && <Loader2Icon className="animate-spin" />}
        {later ? "Schedule transfer" : "Send money"}
      </Button>
    </form>
  )
}
