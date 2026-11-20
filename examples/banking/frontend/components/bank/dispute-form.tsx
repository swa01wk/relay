"use client"

import * as React from "react"

import { raiseDispute, type ActionResult } from "@/app/actions"
import { inputClass, panelClass, useResult } from "@/components/bank/use-result"
import { Button } from "@/components/ui/button"
import { DISPUTE_REASONS } from "@/lib/types"

/** Raise a dispute. Field names match the raise_dispute tool. */
export function DisputeForm({ transactionId, suggested }: { transactionId: string; suggested?: string }) {
  const [state, action, pending] = React.useActionState<ActionResult | null, FormData>(raiseDispute.bind(null, transactionId), null)
  useResult(state, "Dispute raised")
  return (
    <form action={action} className={panelClass} data-relay-form="Raise a dispute" aria-label="Raise a dispute">
      <h2 className="font-semibold">Raise a dispute</h2>
      <label className="flex flex-col gap-1 text-sm">
        Reason
        <select name="reason" defaultValue={suggested ?? ""} required className={inputClass}>
          <option value="" disabled>
            Choose a reason
          </option>
          {Object.entries(DISPUTE_REASONS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        What happened
        <textarea name="details" rows={3} maxLength={1000} aria-invalid={Boolean(state?.fields?.details) || undefined} className="rounded-md border bg-background px-3 py-2 text-sm aria-invalid:border-destructive" />
        {state?.fields?.details && <span className="text-xs text-destructive">{state.fields.details}</span>}
      </label>
      <p className="text-xs text-muted-foreground">We reply within 14 days. A duplicate charge is credited back straight away while we check.</p>
      <Button type="submit" disabled={pending} className="self-start">
        Raise dispute
      </Button>
    </form>
  )
}
