"use client"

import * as React from "react"
import { CalendarClockIcon } from "lucide-react"

import { payBill, setAutopay, type ActionResult } from "@/app/actions"
import { inputClass, useResult } from "@/components/bank/use-result"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { rupees, shortDate } from "@/lib/format"
import type { Biller } from "@/lib/types"
import { cn } from "@/lib/utils"

export function BillCard({ biller, accounts }: { biller: Biller; accounts: { id: string; label: string }[] }) {
  const [payState, payAction, paying] = React.useActionState<ActionResult | null, FormData>(payBill.bind(null, biller.id), null)
  const [autoState, autoAction, saving] = React.useActionState<ActionResult | null, FormData>(setAutopay.bind(null, biller.id), null)
  useResult(payState, "Bill paid")
  useResult(autoState, "Autopay updated")
  const bill = biller.bill
  return (
    <article className="flex flex-col gap-4 rounded-2xl border bg-card p-5" data-testid={`biller-${biller.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">{biller.nickname}</h2>
          <p className="text-sm text-muted-foreground">
            {biller.name} · {biller.category} · {biller.consumer_number}
          </p>
        </div>
        {bill ? (
          <Badge variant={bill.days_left <= 3 ? "destructive" : "secondary"}>{bill.status === "overdue" ? "Overdue" : bill.days_left === 0 ? "Due today" : `Due in ${bill.days_left}d`}</Badge>
        ) : (
          <Badge variant="outline">Nothing due</Badge>
        )}
      </div>
      {bill ? (
        <p className="text-2xl font-semibold tabular-nums">
          {rupees(bill.amount)} <span className="text-sm font-normal text-muted-foreground">due {shortDate(bill.due_date)}</span>
        </p>
      ) : (
        biller.last_paid && <p className="text-sm text-muted-foreground">Last paid {rupees(biller.last_paid.amount)} on {shortDate(biller.last_paid.date)}</p>
      )}
      {bill?.autopay_skipped && <p className="text-sm text-amber-700">Autopay skipped: {bill.autopay_skipped}.</p>}
      <form action={payAction} className="flex flex-wrap items-end gap-2" data-relay-form={`Pay ${biller.nickname}`} aria-label={`Pay ${biller.nickname}`}>
        <label className="flex flex-col gap-1 text-sm">
          Amount (₹)
          <input name="amount" type="number" min={1} defaultValue={bill?.amount} placeholder={bill ? undefined : "Advance"} className={cn(inputClass, "w-32")} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          From
          <select name="from_account" className={inputClass} defaultValue="ACC-01">
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label}
              </option>
            ))}
          </select>
        </label>
        <Button type="submit" disabled={paying}>
          Pay
        </Button>
      </form>
      <form action={autoAction} className="flex flex-wrap items-center gap-3 border-t pt-4 text-sm" data-relay-form={`Autopay ${biller.nickname}`} aria-label={`Autopay for ${biller.nickname}`}>
        <CalendarClockIcon className="size-4 text-muted-foreground" />
        <label className="flex items-center gap-2">
          <input type="checkbox" name="enabled" defaultChecked={biller.autopay.enabled} className="accent-[var(--primary)]" /> Autopay on the due date
        </label>
        <label className="flex items-center gap-1 whitespace-nowrap">
          up to ₹
          <input name="max_amount" type="number" min={1} defaultValue={biller.autopay.max_amount} className={cn(inputClass, "w-24")} />
        </label>
        <Button type="submit" variant="outline" size="sm" disabled={saving}>
          Save
        </Button>
      </form>
    </article>
  )
}
