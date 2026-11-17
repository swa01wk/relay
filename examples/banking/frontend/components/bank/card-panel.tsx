"use client"

import * as React from "react"
import { LockIcon, LockOpenIcon } from "lucide-react"
import { toast } from "sonner"

import { lockCard, payCard, reportCard, updateCardControls, type ActionResult } from "@/app/actions"
import { inputClass, panelClass, useResult } from "@/components/bank/use-result"
import { Button } from "@/components/ui/button"
import { rupees } from "@/lib/format"
import { REPORT_REASONS, type Card } from "@/lib/types"
import { cn } from "@/lib/utils"

export function LockButton({ card }: { card: Card }) {
  const [pending, start] = React.useTransition()
  const locked = card.status === "locked"
  if (card.status !== "active" && !locked) return null
  return (
    <Button
      variant={locked ? "default" : "outline"}
      disabled={pending}
      data-testid="lock-card"
      onClick={() =>
        start(async () => {
          const res = await lockCard(card.id, !locked)
          if (res.ok) toast.success(res.message ?? (locked ? "Card unlocked" : "Card locked"))
          else toast.error(res.error)
        })
      }
    >
      {locked ? <LockOpenIcon /> : <LockIcon />}
      {locked ? "Unlock card" : "Lock card"}
    </Button>
  )
}

const LABELS: Record<string, string> = { online: "Online payments", international: "International use", contactless: "Contactless (tap to pay)", atm: "ATM withdrawals" }
const LIMIT_LABELS: Record<string, string> = { atm_daily: "ATM a day", pos_daily: "Shops a day", online_daily: "Online a day" }

/** Controls and limits. Field names match update_card_controls (limits as *_limit). */
export function CardControlsForm({ card }: { card: Card }) {
  const present = Object.keys(card.controls)
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(updateCardControls.bind(null, card.id, present), null)
  useResult(state, "Card controls saved")
  const disabled = card.status === "blocked"
  return (
    <form action={action} className={panelClass} data-relay-form="Card controls" aria-label="Card controls">
      <h2 className="font-semibold">Controls and limits</h2>
      <fieldset className="flex flex-col gap-2" disabled={disabled}>
        {present.map((key) => (
          <label key={key} className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-sm">
            {LABELS[key]}
            <input type="checkbox" name={key} defaultChecked={card.controls[key as keyof Card["controls"]]} className="size-4 accent-[var(--primary)]" />
          </label>
        ))}
      </fieldset>
      <fieldset className="grid grid-cols-2 gap-2 sm:grid-cols-3" disabled={disabled}>
        {Object.entries(card.limits).map(([key, value]) => (
          <label key={key} className="flex flex-col gap-1 text-sm">
            {LIMIT_LABELS[key]} (₹)
            <input
              type="number"
              name={`${key}_limit`}
              min={0}
              max={card.limit_maximums?.[key]}
              defaultValue={value}
              className={inputClass}
              aria-invalid={Boolean(state?.fields?.[`${key}_limit`]) || undefined}
            />
            {card.limit_maximums?.[key] && <span className="text-xs text-muted-foreground">Up to {rupees(card.limit_maximums[key])}</span>}
          </label>
        ))}
      </fieldset>
      <Button type="submit" variant="outline" disabled={pending || disabled} className="self-start">
        Save controls
      </Button>
    </form>
  )
}

export function ReportCardForm({ card }: { card: Card }) {
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(reportCard.bind(null, card.id), null)
  useResult(state, "Card blocked")
  if (card.status === "blocked") return null
  return (
    <form
      action={action}
      className={panelClass}
      data-relay-form="Report card lost"
      aria-label="Report card lost or stolen"
      onSubmit={(e) => {
        if (!window.confirm(`Block ••${card.last4} for good and send a new card?`)) e.preventDefault()
      }}
    >
      <h2 className="font-semibold">Lost, stolen or damaged?</h2>
      <p className="text-sm text-muted-foreground">
        Blocks this card for good and sends a new one in 5 days{card.kind === "debit" ? " (₹236 incl. GST if lost or stolen)" : ""}. If you might find it, lock it instead.
      </p>
      <label className="flex flex-col gap-1 text-sm">
        What happened
        <select name="reason" defaultValue="lost" className={inputClass}>
          {Object.entries(REPORT_REASONS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </label>
      <Button type="submit" variant="destructive" disabled={pending} className="self-start">
        Block and replace
      </Button>
    </form>
  )
}

/** Pay the credit card bill. Field names match pay_credit_card. */
export function PayCardForm({ card, accounts }: { card: Card; accounts: { id: string; label: string; balance: number }[] }) {
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(payCard.bind(null, card.id), null)
  const [choice, setChoice] = React.useState("total_due")
  useResult(state, "Payment made")
  const st = card.statement
  if (!st) return null
  const options = [
    { value: "total_due", label: "Total due", amount: st.total_due_now },
    { value: "minimum_due", label: "Minimum due", amount: st.minimum_due_now },
    { value: "outstanding", label: "Full outstanding (incl. unbilled)", amount: card.outstanding ?? 0 },
  ]
  return (
    <form action={action} className={panelClass} data-relay-form="Pay card bill" aria-label="Pay card bill">
      <h2 className="font-semibold">Pay card bill</h2>
      <div className="flex flex-col gap-2">
        {options.map((o) => (
          <label key={o.value} className="flex cursor-pointer items-center justify-between gap-3 rounded-lg border px-3 py-2 text-sm has-checked:border-primary has-checked:ring-1 has-checked:ring-primary">
            <span className="flex items-center gap-2">
              <input type="radio" name="pay" value={o.value} checked={choice === o.value} onChange={() => setChoice(o.value)} className="accent-[var(--primary)]" />
              {o.label}
            </span>
            <span className="tabular-nums">{rupees(o.amount)}</span>
          </label>
        ))}
        <label className="flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm has-checked:border-primary has-checked:ring-1 has-checked:ring-primary">
          <input type="radio" name="pay" value="custom" checked={choice === "custom"} onChange={() => setChoice("custom")} className="accent-[var(--primary)]" />
          Other amount ₹
          <input name="amount" type="number" min={1} onFocus={() => setChoice("custom")} className={cn(inputClass, "w-32")} />
        </label>
      </div>
      <label className="flex flex-col gap-1 text-sm">
        From
        <select name="from_account" defaultValue="ACC-01" className={inputClass}>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.label} — {rupees(a.balance)}
            </option>
          ))}
        </select>
      </label>
      <Button type="submit" disabled={pending} className="self-start" data-testid="pay-card">
        Pay now
      </Button>
    </form>
  )
}
